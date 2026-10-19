"""공개 전 점검표 — production을 임시 폴더에 빌드·검증하고, 사람이 할 일을 docs/handover/launch_checklist.md로 쓴다.

    python tools/launch_check.py                                   # 점검표를 쓴다(이 파일 말고는 아무것도 바꾸지 않음)
    python tools/launch_check.py --stdout                          # 쓰지 않고 출력만
    python tools/launch_check.py --data data/gunsan --md docs/handover/launch_checklist.md

- production 빌드·검증은 임시 폴더에서 한다: `python -m pipeline.build --mode production` →
  `python -m pipeline.validate --mode production --report <임시>`. data/·public/·reports/·site.json은 건드리지 않는다.
- 리허설: 데이터의 임시 사본에서 모든 장소·가이드·코스·행사를 published·검수일 있음으로, site_url·ga4_id·
  operator.contact는 임시 값으로 두고 한 번 더 빌드·검증한다. 검수를 마치고 공개하면 나올 오류를 미리 보여 준다.
- 색인 준비도는 pipeline.schema.index_status를 쓰되 '검수일 없음' 사유는 빼고 본다(검수는 사람의 단계).
- 같은 데이터·설정이면 같은 파일이 나온다(날짜·시각·임시 경로를 넣지 않는다).
- 공개·설정 값·status·reviewed_at은 사람이 정한다(CLAUDE.md 3절 5항·9절). 이 도구는 할 일만 적는다.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import jsonld
from pipeline.build import SEARCH_BOTS, TRAINING_BOTS, State, guide_has_content
from pipeline.schema import (INDEX_GROUP_LABELS, INDEX_KIND_GROUPS, INDEX_MIN_GROUPS, INDEX_REASONS, KIND_LABELS,
                             index_groups, index_status, node_types)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MD = ROOT / "docs" / "handover" / "launch_checklist.md"
DEFAULT_QUESTIONS = ROOT / "measurement" / "questions.csv"
REHEARSAL_SITE = {"site_url": "https://launch-rehearsal.invalid", "ga4_id": "G-REHEARSAL", "contact": "rehearsal"}
REHEARSAL_DATE = "2000-01-01"   # placeholder reviewed_at in the temporary copy only (never printed)
UNREVIEWED = INDEX_REASONS["unreviewed"]
EXTRA_TRAINING = ("Google-Extended", "Applebot-Extended")
CLIENT_STAYS = ()   # 고객사 숙소(CLAUDE.md 9절). 운영자 확인 2026-10-14: 스테이,머뭄은 고객사 아님 — 관계 표시 없이 공개
SITE_WIDE = ("site.json", "URL", "robots.txt", "sitemap.xml", "llms.txt")

# validate ERROR (message pattern) -> what a person does about it
ACTIONS = (
    (r"^site_url", "`site.json`의 `site_url`에 최종 https 주소를 넣는다. 도메인 또는 서브도메인으로 정한다"
                   "(네이버는 하위 폴더를 등록하지 않음). 공개 후에는 바꾸지 않는다."),
    (r"^ga4_id", "GA4 속성을 만들고 측정 ID(G-…)를 `ga4_id`에 넣는다. 맞춤 측정기준 place_id·link_provider·"
                 "page_kind를 등록하고 실시간 보고서에서 페이지뷰를 확인한다."),
    (r"^operator\.contact", "정정 요청을 받을 연락처(이메일 등)를 `operator.contact`에 넣는다. 회사 소개 주소가 있으면 "
                            "`operator.url`도 넣는다(Organization 구조화 데이터는 이 값만 쓴다)."),
    (r"절대 주소 \d+건이 site_url", "따로 고칠 것 없음: `site_url`을 넣고 production을 다시 빌드하면 canonical·og·sitemap·"
                                  "robots·llms·JSON-LD 주소가 모두 그 도메인으로 바뀐다. 다시 빌드한 뒤에도 남으면 개발 쪽에 넘긴다."),
    (r"reviewed_at", "검수 시트(`python tools/make_review_sheet.py`)에 OK를 적고 `python tools/apply_review.py --sheet … "
                     "--apply`로 검수일을 기록한다. published 전환은 그다음 사람이 한다."),
    (r"실용 정보 없음", "이 장소는 published로 바꾸지 않는다. 공개하려면 TourAPI·공식 페이지에서 주소 외 방문 정보"
                       "(이용시간·쉬는 날·요금·주차·문의)를 하나 이상 채운다."),
    (r"블록 내용 부족|필수 블록 없음", "해당 장소의 요약·방문 정보·FAQ 등 빈 블록을 채운 뒤 공개한다."),
    (r"자리표시 문구", "화면에 남은 자리표시 문구(예: [샘플], TODO)를 실제 값으로 바꾼다."),
    (r"색인 기준|sitemap\.xml에|llms", "빌드 결과와 데이터의 색인 판정이 어긋남: 다시 빌드한다. 남으면 개발 쪽에 넘긴다."),
    (r"전체 차단|Sitemap 줄", "robots.txt 생성 규칙과 `crawler_policy`를 확인한다(production은 검색 크롤러를 허용해야 함)."),
    (r"구조화 데이터", "구조화 데이터와 화면 값이 어긋남: 개발 쪽에 넘긴다(데이터 값을 고치지 말 것)."),
    (r"내부 링크 깨짐", "링크된 페이지가 공개 대상에 없음: 대상도 함께 공개하거나 링크를 뺀다."),
)
FALLBACK_ACTION = "오류 문구의 페이지·항목을 고친 뒤 다시 검증한다(개발 쪽)."


# ---------------------------------------------------------------- build + validate (subprocess)
def _python(args: list[str]) -> subprocess.CompletedProcess:
    """Run `python <args>` from the repository root (tests replace this). The child writes UTF-8 to the pipes on every
    platform (Windows would use the locale code page, e.g. cp949, which cannot encode every character we print)."""
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, encoding="utf-8",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def parse_qa_report(path: Path) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(where, message) pairs of the ERROR and WARN lists in a pipeline.validate report."""
    found: dict[str, list] = {"## 오류": [], "## 경고": []}
    section = None
    text = path.read_text("utf-8") if path.exists() else ""
    for line in text.splitlines():
        if line in found:
            section = line
            continue
        if section and line.startswith("- ["):
            pair = _split_where(line[2:])
            if pair:
                found[section].append(pair)
    return found["## 오류"], found["## 경고"]


def _split_where(item: str) -> tuple[str, str] | None:
    """'[where] message' -> (where, message). The where part may hold brackets of its own
    ('gunsan-1 [백년가게]쌍용반점'), so the closing bracket is the one that balances the first."""
    depth = 0
    for i, ch in enumerate(item):
        depth += {"[": 1, "]": -1}.get(ch, 0)
        if depth == 0:
            return (item[1:i], item[i + 1:].strip()) if i and item[i + 1:i + 2] == " " else None
    return None


def build_and_validate(data: Path, work: Path, name: str) -> dict:
    out, report = work / f"{name}-dist", work / f"{name}-qa.md"
    b = _python(["-m", "pipeline.build", "--data", str(data), "--out", str(out), "--mode", "production"])
    if b.returncode != 0:
        tail = (b.stderr or b.stdout or "").strip().splitlines()[-1:] or ["(출력 없음)"]
        return {"built": False, "errors": [("build", f"production 빌드 실패: {tail[0]}")], "warnings": [], "stats": {}}
    v = _python(["-m", "pipeline.validate", "--data", str(data), "--out", str(out), "--mode", "production",
                 "--report", str(report)])
    stats = {}
    for line in (v.stdout or "").splitlines():
        if line.startswith("{"):
            try:
                stats = json.loads(line)
            except json.JSONDecodeError:
                pass
            break
    errors, warnings = parse_qa_report(report)
    if v.returncode != 0 and not errors:
        tail = (v.stderr or v.stdout or "").strip().splitlines()[-1:] or ["(출력 없음)"]
        errors = [("validate", f"검증 실행 실패: {tail[0]}")]
    return {"built": True, "errors": errors, "warnings": warnings, "stats": stats}


def stage_rehearsal(data: Path, staged: Path) -> None:
    """Temporary copy where every record is published and reviewed and the owner's site values are placeholders."""
    staged.mkdir(parents=True)
    for f in sorted(data.glob("*.json")):
        shutil.copyfile(f, staged / f.name)
    for name in ("places", "guides", "courses", "events"):
        path = staged / f"{name}.json"
        if not path.exists():
            continue
        records = json.loads(path.read_text("utf-8"))
        for r in records:
            r["status"] = "published"
            r["reviewed_at"] = r.get("reviewed_at") or REHEARSAL_DATE
        path.write_text(json.dumps(records, ensure_ascii=False), "utf-8")
    site = json.loads((staged / "site.json").read_text("utf-8"))
    if not str(site.get("site_url") or "").startswith("https://"):
        site["site_url"] = REHEARSAL_SITE["site_url"]
    site["ga4_id"] = site.get("ga4_id") or REHEARSAL_SITE["ga4_id"]
    site["operator"] = {**(site.get("operator") or {})}
    site["operator"]["contact"] = site["operator"].get("contact") or REHEARSAL_SITE["contact"]
    (staged / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")


# ---------------------------------------------------------------- analysis (in-process, read-only)
def action_for(message: str) -> str:
    for pattern, action in ACTIONS:
        if re.search(pattern, message):
            return action
    return FALLBACK_ACTION


def group_errors(errors: list[tuple[str, str]]) -> list[dict]:
    """One row per distinct message (site-wide errors) or message kind (page errors): site-wide settings first,
    then page errors, each in first-seen order."""
    rows: dict[str, dict] = {}
    for where, msg in errors:
        shown = msg.split(" (예:")[0].rstrip(": ").strip()
        key = shown if where in SITE_WIDE else re.sub(r"\d+", "N", shown)
        row = rows.setdefault(key, {"where": where, "message": shown, "count": 0, "examples": [],
                                    "action": action_for(msg)})
        row["count"] += 1
        if where not in SITE_WIDE:
            row["examples"].append(where)
    return sorted(rows.values(), key=lambda r: r["where"] not in SITE_WIDE)


def error_table(groups: list[dict], R: dict) -> list[str]:
    """Markdown rows: error, count, question targets among the pages, examples, the person's action."""
    if not groups:
        return ["- 오류 없음"]
    names = {e["id"]: " ".join(e["name"].split()) for e in R["places"]}
    qids = {e["id"]: sorted(e.get("question_ids") or []) for e in R["places"]}
    label = lambda w: names.get(w.split(" ", 1)[0], w)
    out = ["| # | 검증 오류 | 건수 | 질문 대상 | 예 | 사람이 할 일 |", "|---|---|---|---|---|---|"]
    for i, g in enumerate(groups, 1):
        ids = [w.split(" ", 1)[0] for w in g["examples"]]
        qs = sorted(dict.fromkeys(f"{names[x]}({','.join(qids[x])})" for x in ids if qids.get(x)))
        ex = ", ".join(label(w) for w in g["examples"][:6]) + (f" 외 {len(g['examples']) - 6}" if len(g["examples"]) > 6 else "")
        text = f"[{g['where']}] {g['message']}" if g["where"] in SITE_WIDE else g["message"]
        out.append(f"| {i} | {_cell(text)} | {g['count']} | {_cell(', '.join(qs) or '-')} | {_cell(ex or '-')} | "
                   f"{_cell(g['action'])} |")
    for i, g in enumerate(groups, 1):   # the whole list, folded, when the table shows only the first six
        if len(g["examples"]) > 6:
            out += ["", f"<details><summary>{i}번 전체 {len(g['examples'])}건</summary>", "",
                    ", ".join(label(w) for w in g["examples"]), "", "</details>"]
    return out


def content_status(e: dict) -> tuple[bool, list[str]]:
    """index_status without the 'reviewed_at' reason: would the page be indexed once a person reviews it?"""
    _, reasons = index_status(e)
    reasons = [r for r in reasons if r != UNREVIEWED]
    return not reasons, reasons


def load_questions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [r for r in csv.DictReader(fh) if (r.get("id") or "").strip()]


def readiness(data: Path) -> dict:
    S = State(data, "preview")   # every status, duplicates and excluded records left out (as the builder does)
    places = S.entities
    short = defaultdict(list)            # reason -> places
    missing = defaultdict(Counter)       # kind -> group label -> count (places short of practical groups)
    short_by_kind = Counter()
    ready = 0
    for e in places:
        ok, reasons = content_status(e)
        ready += ok
        for r in reasons:
            short[r].append(e)
        if INDEX_REASONS["groups"] in reasons:
            short_by_kind[e.get("kind")] += 1
            have = set(index_groups(e))
            for g in INDEX_KIND_GROUPS.get(e.get("kind"), ()):
                if g not in have:
                    missing[e.get("kind")][INDEX_GROUP_LABELS[g]] += 1
    live = lambda xs: [x for x in xs if not x.get("duplicate_of") and not x.get("exclude")]
    guides, courses = live(S.guides_all), live(S.courses_all)
    reasons = sorted(short.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:5]
    return {"S": S, "places": places, "ready": ready, "reasons": reasons, "missing": missing,
            "short_by_kind": short_by_kind, "guides": guides, "guides_ready": [g for g in guides if guide_has_content(g)],
            "courses": courses, "series": S.series,
            "published": {name: sum(1 for x in xs if x.get("status") == "published")
                          for name, xs in (("장소", S.entities_all), ("가이드", S.guides_all),
                                           ("코스", S.courses_all), ("행사", S.events_all))}}


def question_targets(R: dict, rehearsal_errors: list[tuple[str, str]]) -> list[dict]:
    """Every page that a question_ids field points at, with its verdict once reviewed."""
    S = R["S"]
    page_errors = defaultdict(set)   # validate 'where' (entity id, guide title or HTML path) -> messages
    for where, msg in rehearsal_errors:
        for key in {where, where.split(" ", 1)[0]}:
            page_errors[key].add(msg.split(" — ")[0])

    def errs(path: str, *keys: str) -> list[str]:
        found = set().union(*(page_errors.get(k, set()) for k in (*keys, path + "index.html")))
        return [f"공개 시 검증 오류: {x}" for x in sorted(found)]

    rows = []
    for e in R["places"]:
        for q in e.get("question_ids") or []:
            ok, reasons = content_status(e)
            bad = errs(e["_path"], e["id"])
            rows.append({"q": q, "path": e["_path"], "kind": "장소", "pass": ok and not bad, "why": reasons + bad})
    ready_guides = {g.get("id") for g in R["guides_ready"]}
    for g in R["guides"]:
        for q in g.get("question_ids") or []:
            path = f"/guides/{g['slug']}/"
            bad = errs(path, g.get("title", ""))
            ok = g.get("id") in ready_guides
            rows.append({"q": q, "path": path, "kind": "가이드", "pass": ok and not bad,
                         "why": ([] if ok else ["본문·항목·FAQ 없음(가이드 페이지가 만들어지지 않음)"]) + bad})
    for c in R["courses"]:
        for q in c.get("question_ids") or []:
            path, stops = f"/courses/{c['slug']}/", c.get("stops") or []
            linked = sum(1 for s in stops if s.get("place_slug") in S.ent_by_slug)
            bad = errs(path, c.get("name", ""))
            rows.append({"q": q, "path": path, "kind": "코스", "pass": not bad,
                         "why": [f"경유지 {len(stops)}곳 중 장소 연결 {linked}곳"] + bad})
    for sr in R["series"]:
        for q in sr.get("question_ids") or []:
            bad = errs(sr["_path"])
            rows.append({"q": q, "path": sr["_path"], "kind": "행사", "pass": not bad, "why": bad})
    seen = {e.get("id") for e in S.events}
    for ev in S.events_all:   # an undated record has no page of its own
        if ev.get("id") in seen and not ev.get("start_date"):
            for q in ev.get("question_ids") or []:
                rows.append({"q": q, "path": "/events/", "kind": "행사", "pass": False,
                             "why": ["날짜 없는 행사 — 개별 페이지 없음"]})
    order = lambda q: (q[0], int(re.sub(r"\D", "", q) or 0))
    return sorted(rows, key=lambda r: (order(r["q"]), r["kind"], r["path"]))


def owner_state(data: Path, R: dict) -> dict:
    site = json.loads((data / "site.json").read_text("utf-8"))
    places = R["places"]
    type3_only = [e["name"] for e in sorted(places, key=lambda e: (not e.get("question_ids"), e["name"]))
                  if e["_images"] and not any(i.get("license") == "KOGL-1" for i in e["_images"])]
    clients = sorted(x["name"] for x in R["S"].entities_all if any(c in x.get("name", "") for c in CLIENT_STAYS))
    overview = sum(1 for e in places if str((e.get("tourapi") or {}).get("overview") or "").strip())
    # the map module (map.js since the redesign; site.js before it) names the provider: Kakao Maps since the owner's
    # decision of 2026-10-14 (the SDK URL comes from site.json kakao_js_key, see pipeline/build.kakao_sdk_url)
    js = "".join(p.read_text("utf-8") for p in (ROOT / "templates" / "assets" / n for n in ("site.js", "map.js"))
                 if p.exists())
    provider = ("Leaflet + OpenStreetMap 타일" if "tile.openstreetmap.org" in js else
                "카카오맵" if "kakao" in js.lower() else "확인 안 됨")
    assets = ROOT / "templates" / "assets"
    fonts = sorted(p for p in assets.rglob("*") if p.is_file() and "maruburi" in str(p.relative_to(assets)).lower()
                   and p.suffix.lower() in (".woff2", ".woff", ".ttf", ".otf"))
    licences = sorted({p.parent for p in fonts if any(x.is_file() and re.match(r"(?i)(ofl|licen[cs]e)", x.name)
                                                      for x in p.parent.iterdir())})
    if not fonts:
        font = "아직 글꼴 파일 없음(리디자인에서 도입 예정)"
    elif len(licences) == len({p.parent for p in fonts}):
        font = f"글꼴 {len(fonts)}개 · 같은 폴더에 라이선스 파일 있음"
    else:
        font = f"글꼴 {len(fonts)}개 · 라이선스 파일 없음"
    home = jsonld.home_graph(site, "https://x.invalid", [], [])
    city = next((n for n in home["@graph"] if "City" in node_types(n)), {})
    vercel = ROOT / "vercel.json"
    headers = json.loads(vercel.read_text("utf-8")).get("headers", []) if vercel.exists() else []
    noindex_rules = [h for h in headers if any(x.get("key", "").lower() == "x-robots-tag" for x in h.get("headers", []))]
    return {"site": site, "type3_only": type3_only, "overview": overview, "map": provider, "font": font,
            "clients": clients,
            "same_as": bool(city.get("sameAs")), "noindex_rules": noindex_rules,
            "host_conditioned": any(h.get("has") for h in noindex_rules)}


# ---------------------------------------------------------------- markdown
def _cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _filled(value) -> str:
    return "있음" if str(value or "").strip() else "비어 있음"


def render(data: Path, prod: dict, reh: dict, R: dict, targets: list[dict], questions: list[dict], O: dict) -> str:
    site = O["site"]
    sv = site.get("search_verification") or {}
    groups = group_errors(prod["errors"])
    reh_groups = group_errors(reh["errors"])
    settings = [
        ("search_verification.google", _filled(sv.get("google")),
         "Search Console에서 HTML 태그 방식 소유 확인 토큰(content 값)을 넣는다. production 빌드에만 메타 태그가 나간다."),
        ("search_verification.naver", _filled(sv.get("naver")), "네이버 서치어드바이저 사이트 소유 확인 토큰을 넣는다."),
        ("search_verification.bing", _filled(sv.get("bing")), "Bing 웹마스터 도구 msvalidate.01 토큰을 넣는다(GSC 가져오기로 대신해도 됨)."),
        ("indexnow_key", _filled(site.get("indexnow_key")),
         "8~128자 영문·숫자·'-' 키를 넣는다(예: `python -c \"import secrets; print(secrets.token_hex(16))\"`). 배포 후 "
         "`python tools/indexnow.py --out <prod> --send`."),
        ("operator.url", _filled((site.get("operator") or {}).get("url")), "운영사 소개 주소(있으면). Organization 노드의 url이 된다."),
    ]
    missing_settings = [s for s in settings if s[1] == "비어 있음"]
    pub = R["published"]
    q_pass = sum(1 for t in targets if t["pass"])
    q_fail = sorted({f"{t['path'].strip('/').split('/')[-1]}({','.join(sorted(x['q'] for x in targets if x['path'] == t['path']))})"
                     for t in targets if not t["pass"]})
    pending = owner_rows(O)
    L = ["# 공개 전 점검표", "",
         "> `python tools/launch_check.py`가 만든 파일이다. 직접 고치지 말고 다시 실행한다. 같은 데이터·설정이면 같은 내용이 나온다.",
         "> 근거: `docs/handover/aeo_geo_spec.md` 5절, `docs/03_prelaunch_checklist.md`. 공개·설정 값·status·reviewed_at은 사람이 정한다"
         "(CLAUDE.md 3절 5항·9절).", "",
         "## 요약", "",
         f"- production 검증 오류 {len(prod['errors'])}건 → 사람이 할 일 {len(groups)}가지(1절), 검증에는 안 걸리지만 비어 있는 공개 설정 "
         f"{len(missing_settings)}개",
         f"- 지금 공개 대상(status=published): " + " · ".join(f"{k} {v}" for k, v in pub.items())
         + (" — production 빌드에 실릴 페이지가 홈·소개 말고는 없다" if not any(pub.values()) else ""),
         f"- 검수 후 색인 가능(검수일 사유 제외): 장소 {R['ready']}/{len(R['places'])} · 가이드 {len(R['guides_ready'])}/{len(R['guides'])}"
         f" · 코스 {len(R['courses'])}/{len(R['courses'])} · 행사 페이지 {len(R['series'])}",
         f"- 질문 대상(question_ids) 질문·페이지 연결 {len(targets)}개(페이지 {len({t['path'] for t in targets})}곳) 중 통과 {q_pass}"
         f" · 미달 {len(targets) - q_pass}" + (f": {', '.join(q_fail)}" if q_fail else ""),
         f"- 리허설(전부 공개 가정) production 검증 오류 {len(reh['errors'])}건"
         + (f", sitemap URL {reh['stats'].get('sitemap_urls')}개" if reh["stats"].get("sitemap_urls") is not None else ""),
         f"- 사람이 정할 것 {len(pending)}건(4절)", ""]

    L += ["## 1. production 검증 오류 → 사람이 할 일", "",
          "임시 폴더에서 `python -m pipeline.build --data <data> --out <임시> --mode production` → "
          "`python -m pipeline.validate … --mode production`을 돌린 결과다.", ""]
    L += error_table(groups, R)
    L += ["", "### 검증에는 안 걸리지만 공개 전에 넣을 값", "", "| 항목 | 지금 | 할 일 |", "|---|---|---|"]
    L += [f"| `{k}` | {v} | {_cell(a)} |" for k, v, a in settings]
    L.append(f"| 공개 대상 | " + " · ".join(f"{k} {v}" for k, v in pub.items()) + " | 검수 시트(`python tools/make_review_sheet.py`) → "
             "OK 판정 → `python tools/apply_review.py --sheet … --apply`(status=reviewed·검수일) → 사람이 질문 대상부터 "
             "status=published로 바꾼다. |")
    L += ["", "### 리허설: 검수를 마치고 전부 공개하면 나올 오류", "",
          "데이터의 임시 사본에서 모든 장소·가이드·코스·행사를 published·검수일 있음으로, `site_url`·`ga4_id`·`operator.contact`는 "
          "임시 값으로 두고 다시 빌드·검증했다. 원본은 바꾸지 않았다.", ""]
    L += error_table(reh_groups, R)

    L += ["", "## 2. 색인 준비도 (검수 후 기준, `pipeline.schema.index_status`에서 검수일 사유 제외)", "",
          "| 구분 | 색인 가능 | 전체 | 판정 |", "|---|---|---|---|",
          f"| 장소 | {R['ready']} | {len(R['places'])} | 유형별 실용 정보 {INDEX_MIN_GROUPS}묶음 이상 + 요약 규칙(상투구·출처 해설체 아님) |",
          f"| 가이드 | {len(R['guides_ready'])} | {len(R['guides'])} | 본문·항목·FAQ 중 하나라도 있으면 페이지가 생기고 색인된다 |",
          f"| 코스 | {len(R['courses'])} | {len(R['courses'])} | production은 공개된 코스를 모두 색인한다 |",
          f"| 행사 페이지 | {len(R['series'])} | {len(R['series'])} | 날짜 있는 행사 묶음마다 한 페이지, 공개하면 모두 색인 |", "",
          "### 장소가 기준에 못 미치는 이유 상위 5", ""]
    if R["reasons"]:
        kinds = list(KIND_LABELS)
        L += ["| # | 이유 | 장소 수 | " + " | ".join(KIND_LABELS[k] for k in kinds) + " |",
              "|---|---|---|" + "---|" * len(kinds)]
        for i, (reason, es) in enumerate(R["reasons"], 1):
            per = Counter(e.get("kind") for e in es)
            L.append(f"| {i} | {_cell(reason)} | {len(es)} | " + " | ".join(str(per.get(k, 0)) for k in kinds) + " |")
        if R["missing"]:
            L += ["", "실용 정보 묶음이 모자란 장소에서 비어 있는 항목(장소 수):", ""]
            for k in KIND_LABELS:
                if R["missing"].get(k):
                    items = sorted(R["missing"][k].items(), key=lambda kv: (-kv[1], kv[0]))
                    L.append(f"- {KIND_LABELS[k]} {R['short_by_kind'][k]}곳: " + " · ".join(f"{g} {n}" for g, n in items))
    else:
        L.append("- 없음: 모든 장소가 기준을 충족한다")

    L += ["", "### 질문 대상 페이지(question_ids)", "",
          "통과 = 검수만 하면 색인되고, 리허설 production 검증에서도 오류가 없다.", "",
          "| 질문 | 페이지 | 구분 | 통과 | 사유·참고 |", "|---|---|---|---|---|"]
    for t in targets:
        L.append(f"| {t['q']} | `{t['path']}` | {t['kind']} | {'통과' if t['pass'] else '미달'} | {_cell(' · '.join(t['why']) or '-')} |")
    covered = {t["q"] for t in targets}
    none = [q for q in questions if q["id"].strip() not in covered]
    if none:
        L += ["", "question_ids로 가리키는 페이지가 없는 질문(`measurement/questions.csv`의 related_pages로만 연결 — "
                  "도메인을 정한 뒤 절대 URL을 적는다):", ""]
        L += [f"- {q['id'].strip()}: {_cell((q.get('related_pages') or '').strip() or '-')}" for q in none]

    L += ["", "## 3. 공개할 때 사람이 할 일 (aeo_geo_spec 5절)", ""] + launch_items(O, R, reh)
    L += ["", "## 4. 사람이 정할 것 (결정 대기)", "", "| 항목 | 지금 | 선택지 · 권장 |", "|---|---|---|"]
    L += [f"| {_cell(a)} | {_cell(b)} | {_cell(c)} |" for a, b, c in pending]
    return "\n".join(L) + "\n"


def launch_items(O: dict, R: dict, reh: dict) -> list[str]:
    site = O["site"]
    sv = site.get("search_verification") or {}
    pol = site.get("crawler_policy") or {}
    search = list(pol.get("allow_search_bots", SEARCH_BOTS))
    training = [] if pol.get("allow_training_bots") else list(pol.get("training_bots", TRAINING_BOTS))
    unlisted = [b for b in EXTRA_TRAINING if b not in training]
    rules = O["noindex_rules"]
    vercel_now = ("`vercel.json`에 X-Robots-Tag noindex 규칙 없음" if not rules else
                  "`vercel.json`의 X-Robots-Tag noindex가 " + ("호스트 조건으로 나뉘어 있음" if O["host_conditioned"]
                                                            else "모든 호스트·경로(`/(.*)`)에 걸려 있음"))
    pub_total = sum(R["published"].values())
    return [
        f"- [ ] **site_url**: 최종 https 도메인을 정해 `site.json`에 넣는다(지금: {'`' + site['site_url'] + '`' if site.get('site_url') else '비어 있음'}). "
        "네이버는 하위 폴더를 등록하지 않으므로 도메인 또는 서브도메인. 모든 절대 주소가 이 값으로 만들어진다.",
        f"- [ ] **noindex 해제는 공개 호스트에서만**: 지금 {vercel_now}. production 빌드 자체는 전체 noindex를 내지 않는다. "
        "공개 도메인에서만 헤더를 빼고(`has: [{type: \"host\", …}]` 조건), `*.vercel.app`·미리보기 호스트는 noindex를 유지하거나 "
        "공개 도메인으로 301. `noarchive`는 Copilot 답변에서도 빠지게 하므로 공개 호스트에 남기지 않는다.",
        f"- [ ] **robots.txt·크롤러 정책(사람 결정)**: production robots는 검색·답변 크롤러 {len(search)}종"
        f"({', '.join(search)})을 허용하고, 학습 전용 {', '.join(training) or '없음'}을 막는다"
        f"(`allow_training_bots={str(bool(pol.get('allow_training_bots'))).lower()}`). "
        + (f"{', '.join(unlisted)}는 목록에 없어 `User-agent: *` 허용을 따른다 — '학습 금지'가 뜻이면 추가 여부를 정한다"
           "(Google-Extended는 AI Overviews·AI Mode 노출과 무관)." if unlisted else ""),
        "- [ ] **호스팅 방화벽**: Vercel Firewall의 AI 봇 관리 규칙은 Allow 또는 Log(Deny 금지), 봇 챌린지 없음. 배포 후 "
        "`bash tools/check_access.sh https://<도메인> --mode production --path /places/<slug>/`를 봇 UA별로 돌려 모두 200인지 본다. "
        "봇 방문 기록이 남도록 로그 드레인을 연결한다.",
        f"- [ ] **Google Search Console**: 소유 확인(`search_verification.google` {_filled(sv.get('google'))}) → `sitemap.xml` 제출 → "
        "설정 > 검색 생성형 AI = 포함(기본값) 확인 → 질문 대상 URL마다 URL 검사.",
        f"- [ ] **네이버 서치어드바이저**: 소유 확인(`search_verification.naver` {_filled(sv.get('naver'))}) → 사이트맵 제출 → 질문 대상 URL "
        "수집 요청 → robots·OG·중복 제목 보고서 확인(가이드·행사 전문 RSS는 선택).",
        f"- [ ] **Bing 웹마스터 도구**: 소유 확인(`search_verification.bing` {_filled(sv.get('bing'))}) → 사이트맵 제출 → AI Performance "
        "보고서에서 질문 대상 URL부터 확인.",
        f"- [ ] **IndexNow(배포 후마다)**: `indexnow_key` {_filled(site.get('indexnow_key'))}. production을 빌드·배포하고 "
        "`https://<도메인>/<키>.txt`가 열리는지 본 뒤 `python tools/indexnow.py --out <prod> --send`. 응답 코드를 측정 기록에 남긴다"
        "(빙·네이버·얀덱스 등에 전달, 구글은 아님).",
        f"- [ ] **검수 → 공개 전환**: 지금 published {pub_total}건. `python tools/make_review_sheet.py --data data/gunsan --out "
        "docs/handover/review_round3.csv` → 판정 칸에 OK/수정 → `python tools/apply_review.py --sheet docs/handover/review_round3.csv "
        "--apply`(status=reviewed·reviewed_at) → 질문 대상 페이지부터 사람이 status=published. 2절의 '미달' 페이지는 내용을 채운 뒤에.",
        "- [ ] **주 1회 갱신**: `python tools/refresh.py`(TourAPI 캐시 우선 → 공식 확인값 → `public/` → `reports/quality_latest.md`, "
        "push·배포 없음). 행사 월별 묶음과 색인 판정이 빌드 시점 기준이므로 측정 기간에는 매주, 행사·사실이 바뀔 때마다 다시 빌드하고 "
        "배포 후 IndexNow를 보낸다. 응답을 새로 받으려면 `--fresh`.",
        "- [ ] **공개 당일 기록**(`measurement/`): robots.txt, 장소 페이지 응답 헤더(`curl -sI`), check_access 결과, sitemap URL 수, "
        "production QA 리포트, 방화벽 봇 설정, 질문별 대상 URL·`page_live_date`.",
    ]


def owner_rows(O: dict) -> list[tuple[str, str, str]]:
    site = O["site"]
    op = site.get("operator") or {}
    t3 = O["type3_only"]
    return [
        ("브랜드 표기", f"`brand`={site.get('brand', '')} · `site_name`={site.get('site_name', '')}",
         "WebforAI / Web4AI 중 하나. 회사가 앞으로 쓸 표기로 정하고 `brand`·`site_name`을 함께 맞춘다."),
        ("운영 주체 표시", f"`operator.name`={op.get('name', '')} · url {_filled(op.get('url'))} · contact {_filled(op.get('contact'))}",
         "정정 요청 연락처는 공개 전 필수(1절). url·sameAs는 회사 공식 채널이 있을 때만."),
        ("TourAPI 텍스트(overview) 게재", f"{O['overview']}곳에 사실 확인용으로만 저장, 화면에 싣지 않음(`docs/rights.md`)",
         "싣지 않음 / 이용허락범위 확인 후 싣기. 권장: 싣지 않음 — 답변 인용은 출처를 단 우리 문장과 사실표로 충분하다(aeo_geo_spec 5절 10)."),
        ("3유형(KOGL-3) 사진을 og:image로", f"1유형 사진이 없어 3유형이 대표 이미지가 되는 장소 {len(t3)}곳"
         + (f"(예: {', '.join(t3[:5])})" if t3 else ""),
         "허용(지금 동작, 플랫폼이 미리보기를 자를 수 있음) / 3유형만 있으면 og:image 없음. 변경 금지 조건 때문에 정하기 전까지 1유형 우선."),
        ("지도 제공자", f"{O['map']}" + (f" · JavaScript 키 `kakao_js_key` {_filled(site.get('kakao_js_key'))}"
                                         if O["map"] == "카카오맵" else ""),
         "결정됨(운영자 2026-10-14): 카카오맵. 카카오 개발자 콘솔에 등록한 웹 도메인에서만 지도가 뜬다 — 공개 주소"
         "(`site_url`)가 바뀌면 그 주소를 콘솔의 웹 도메인에 더한다."),
        ("MaruBuri 글꼴 라이선스", O["font"],
         "도입하면 OFL 라이선스 파일(OFL.txt)을 글꼴 파일과 같은 폴더에 둔다(Pretendard처럼). 출처 페이지 표기도 사람이 확인."),
        ("군산 위키백과·위키데이터 sameAs", "넣음" if O["same_as"] else "없음(`jsonld.home_graph`의 `#gunsan` 노드)",
         "사람이 한국어 위키백과 「군산시」와 위키데이터 항목을 직접 열어 확인한 URL만 넣는다(추측 금지). 넣지 않아도 공개에는 지장 없음."),
        ("군산시 원문·사진 이용 협의", "원문은 링크만, 사진은 TourAPI 1·3유형만",
         "협의 요청 / 지금처럼 링크만. 요청 메일 초안: `docs/handover/gunsan_rights_request_draft.md`."),
        ("고객사 숙소 노출과 관계 표시",
         f"장소 데이터에 있음: {', '.join(O['clients'])}" if O["clients"] else "장소 데이터에 없음(노출하려면 기록을 새로 만든다)",
         "노출하지 않음 / 노출하고 운영사와의 관계를 페이지에 밝힘(CLAUDE.md 9절)."),
    ]


# ---------------------------------------------------------------- main
def run(data: Path, md: Path | None, questions: Path) -> str:
    data = data.resolve()
    with tempfile.TemporaryDirectory(prefix="launch-check-") as tmp:
        work = Path(tmp)
        prod = build_and_validate(data, work, "prod")
        staged = work / "rehearsal-data"
        stage_rehearsal(data, staged)
        reh = build_and_validate(staged, work, "rehearsal")
    R = readiness(data)
    targets = question_targets(R, reh["errors"])
    text = render(data, prod, reh, R, targets, load_questions(questions), owner_state(data, R))
    if md is not None:
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(text, "utf-8")
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "gunsan")
    ap.add_argument("--md", type=Path, default=DEFAULT_MD)
    ap.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    ap.add_argument("--stdout", action="store_true", help="파일을 쓰지 않고 출력만")
    a = ap.parse_args(argv)
    text = run(a.data, None if a.stdout else a.md, a.questions)
    if a.stdout:
        print(text, end="")
    else:
        summary = text.split("## 1.", 1)[0].split("## 요약", 1)[-1].strip()
        print(f"{a.md}\n{summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
