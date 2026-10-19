"""Places that belong together (operator decision 2026-10-16): a feature inside another place, or two pages for one
building or business.

A child record in places.json carries

    "part_of": {"id": <parent id>, "rel": "inside" | "same_building", "basis": [codes], "checked_at": "YYYY-MM-DD"}

- inside: a separate feature located within the parent (a temple's main hall, a pier on an island, a bridge in a
  park). Both keep their own page. The child page names its parent in one line with a link (속한 곳: ○○사); the
  parent page lists its parts (○○사 안에 있는 곳). JSON-LD: containedInPlace [parent, city] / containsPlace.
- same_building: two pages for the same building or business (an old bank building / the museum in it). Both pages say
  so the same way (같은 건물: …) and list each other under '같은 건물의 다른 이름'; no part/whole in JSON-LD.

basis says why, in codes that evidence() recomputes from the two records — pipeline.validate fails a stated code that
does not reproduce, so a relation cannot be invented:
  contentid     the same TourAPI contentid
  address       the same address with a building or lot number (province and the bracketed 동 left out); a bare
                리/동 ('○○면 △△도리', shared by every place on that island) is no evidence
  geo           coordinates within GEO_M metres
  homepage      one's homepage is the other's own source page (a page, not a site's front page)
  alt_name      one's name or another name is the other's other name
  text          one summary names the other place as a word (its own names taken out first; '△△도리에' does not
                name △△도, '○○호수공원에' names ○○호수공원)
  address_name  the child's road address is named after the parent ('△△도1길 10', '○○사길 16'); a 리 name with a
                lot number does not count (a 리 can cover more than the island it is named after)

The family of a page (never listed as its nearby or similar-name places — it has its own lines): its parent, its
children and the same_building partners of the page, of its parent and of its children. An alias is a same_building
child: a list that holds its parent never holds it too. Nothing here changes the index criteria or the counts of
list pages (they count pages).
"""
from __future__ import annotations

import re
from collections import defaultdict

from .enrich import haversine_m
from .schema import FACT_LABELS
from .textutil import josa, normalize_name, squash_ws, url_key

RELS = ("inside", "same_building")
BASIS = ("contentid", "address", "geo", "homepage", "alt_name", "text", "address_name")
GEO_M = 50
MAX_DEPTH = 3
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# a province before the city, in any of its forms ('전라북도', '전북특별자치도', '전북', '경기도', '인천광역시' …): two
# spellings of one address compare equal without it
_PROVINCE = re.compile(r"^(?:[가-힣]{2,}?\s*(?:특별자치도|특별자치시|특별시|광역시|도)(?![가-힣])|"
                       r"(?:전북|전남|경북|경남|충북|충남|강원|제주)(?=\s|$))\s*")
_CITY_WORD = re.compile(r"^[가-힣]+?(?:시|군|구)(?=[가-힣])")
_PAREN = re.compile(r"\([^()]*\)|（[^（）]*）")
# what may follow a place name for it to read as the name itself: nothing Korean, or a particle
PARTICLES = ("으로", "에서", "까지", "부터", "처럼", "보다", "이나", "이며", "이고", "이자", "에는", "에도", "와의", "과의",
             "은", "는", "이", "가", "을", "를", "에", "의", "와", "과", "도", "로", "만", "나")
HANGUL = re.compile(r"[가-힣]")


# ---------------------------------------------------------------- evidence
def norm_address(raw) -> str:
    """'전라북도 ○○시 ○○1길 21 (○○동)' and '전북특별자치도 ○○시 ○○1길 21(○○동)' -> '○○시○○1길21'."""
    s = _PAREN.sub(" ", squash_ws(str(raw or "")))
    s = _PROVINCE.sub("", s)
    return re.sub(r"\s+", "", s)


def numbered(addr: str) -> bool:
    """A building or lot number (a bare 리/동/면 names an area, not a place)."""
    return bool(re.search(r"\d", _CITY_WORD.sub("", addr)))


def _names(e: dict) -> list[str]:
    return [squash_ws(n) for n in [e.get("name"), *(e.get("alternate_names") or [])] if squash_ws(n)]


def _source_keys(e: dict) -> set[str]:
    """The record's own source page(s) — a page path, never a site's front page ('example.go.kr/tour')."""
    out = set()
    for u in ((e.get("original") or {}).get("source_url"), (e.get("official") or {}).get("source_url")):
        k = re.sub(r"\?.*$", "", url_key(u))
        if k.count("/") >= 2:
            out.add(k)
    return out


def _homepage_key(e: dict) -> str:
    k = re.sub(r"\?.*$", "", url_key((e.get("facts") or {}).get("homepage") or (e.get("official") or {}).get("homepage")))
    return k if k.count("/") >= 2 else ""


def _name_pattern(name: str) -> re.Pattern:
    """The name with any spacing between its letters ('○○근대건축관' finds '○○ 근대건축관')."""
    chars = [re.escape(c) for c in re.sub(r"\s+", "", name)]
    return re.compile(r"\s*".join(chars))


def names_in(text: str, name: str) -> bool:
    """text names `name` as a word: not inside a longer word ('△△도리', '△△도1길' do not name △△도)."""
    if len(re.sub(r"\s+", "", name)) < 2:
        return False
    for m in _name_pattern(name).finditer(text):
        before = text[m.start() - 1] if m.start() else " "
        after = text[m.end():]
        if before.isalnum():
            continue
        if not after or not after[0].isalnum() or (HANGUL.match(after[0]) and after.startswith(PARTICLES)):
            return True
    return False


def _without(text: str, names: list[str]) -> str:
    for n in sorted(names, key=len, reverse=True):
        text = _name_pattern(n).sub(" ", text)
    return text


def evidence(child: dict, parent: dict) -> set[str]:
    """The basis codes the two records support (module docstring)."""
    out = set()
    cid = lambda e: str((e.get("tourapi") or {}).get("contentid") or "").strip()  # noqa: E731
    if cid(child) and cid(child) == cid(parent):
        out.add("contentid")
    fa, fb = (child.get("facts") or {}).get("address"), (parent.get("facts") or {}).get("address")
    a, b = norm_address(fa), norm_address(fb)
    if a and a == b and numbered(a):
        out.add("address")
    ga, gb = child.get("geo") or {}, parent.get("geo") or {}
    if None not in (ga.get("lat"), ga.get("lng"), gb.get("lat"), gb.get("lng")):
        if haversine_m(float(ga["lat"]), float(ga["lng"]), float(gb["lat"]), float(gb["lng"])) <= GEO_M:
            out.add("geo")
    if (_homepage_key(child) and _homepage_key(child) in _source_keys(parent)) or (
            _homepage_key(parent) and _homepage_key(parent) in _source_keys(child)):
        out.add("homepage")
    na, nb = {normalize_name(n) for n in _names(child)}, {normalize_name(n) for n in _names(parent)}
    alt_a = {normalize_name(n) for n in child.get("alternate_names") or []}
    alt_b = {normalize_name(n) for n in parent.get("alternate_names") or []}
    if (alt_a & nb) or (alt_b & na):
        out.add("alt_name")
    sa = _without(squash_ws(child.get("summary")), _names(child))
    sb = _without(squash_ws(parent.get("summary")), _names(parent))
    if any(names_in(sa, n) for n in _names(parent)) or any(names_in(sb, n) for n in _names(child)):
        out.add("text")
    pn = re.sub(r"\s+", "", squash_ws(parent.get("name")))
    spaced = _PROVINCE.sub("", squash_ws(_PAREN.sub(" ", squash_ws(str(fa or "")))))
    if len(pn) >= 2 and re.search(rf"(?:^|\s){re.escape(pn)}\d*(?:길|로)\s*\d", spaced):
        out.add("address_name")
    return out


# ---------------------------------------------------------------- the relations of a build
def part_of(e: dict) -> dict:
    p = e.get("part_of")
    return p if isinstance(p, dict) else {}


def resolve(entities_all: list[dict], built: list[dict]) -> list[str]:
    """Set on every built place: _parent (the built parent or None), _rel ('inside' | 'same_building' | ''),
    _parts (built inside-children, by name), _same (built same_building partners: the parent of a same_building
    child, the same_building children), _alias_of (a same_building child: its parent), _family (ids, module
    docstring). A relation whose parent is not built is left out, with a warning (validate makes it an error)."""
    by_id = {e["id"]: e for e in built}
    known = {e["id"] for e in entities_all}
    warns = []
    for e in built:
        e["_parent"], e["_rel"], e["_parts"], e["_same"], e["_alias_of"] = None, "", [], [], None
    for e in built:
        p = part_of(e)
        if not p:
            continue
        parent = by_id.get(p.get("id"))
        if parent is None or parent is e or p.get("rel") not in RELS:
            warns.append(f"관계 생략: {e['id']} {e['name']} → {p.get('id')}"
                         + ("(공개 빌드에 없는 장소)" if p.get("id") in known else "(없는 장소)"))
            continue
        e["_parent"], e["_rel"] = parent, p["rel"]
        if p["rel"] == "inside":
            parent["_parts"].append(e)
        else:
            parent["_same"].append(e)
            e["_same"].append(parent)
            e["_alias_of"] = parent
    for e in built:
        e["_parts"].sort(key=lambda x: x["name"])
    group = lambda x: [x, *x["_same"]] if x else []  # noqa: E731
    for e in built:
        fam = {x["id"] for x in group(e)} | {x["id"] for x in group(e["_parent"])}
        for c in e["_parts"]:
            fam |= {x["id"] for x in group(c)}
        fam.discard(e["id"])
        e["_family"] = fam
    return warns


def family(e: dict) -> set[str]:
    return e.get("_family") or set()


def keep_rows(e: dict, rows: list, target) -> list:
    """Rows of a list on e's page (nearby entries, related places) without e's family, without an alias whose parent
    is in the list too, each place once. target(row) -> its built place or None (a place without a page stays)."""
    fam, seen, out = family(e), set(), []
    ids = {t["id"] for t in (target(r) for r in rows) if t}
    for r in rows:
        t = target(r)
        if t is not None:
            if t is e or t["id"] in fam or t["id"] in seen:
                continue
            alias = t.get("_alias_of")
            if alias is not None and alias["id"] in ids:
                continue
            seen.add(t["id"])
        out.append(r)
    return out


def one_per_building(places: list[dict]) -> list[dict]:
    """Each same_building pair once (the parent kept when both are there, else the one there is)."""
    ids = {x["id"] for x in places}
    return [x for x in places if not (x.get("_alias_of") is not None and x["_alias_of"]["id"] in ids)]


# ---------------------------------------------------------------- raw records (tools: nearby without the API)
def raw_family(places: list[dict]) -> tuple[dict[str, set[str]], dict[str, str]]:
    """({id: family ids}, {alias id: parent id}) from the records' part_of, every record counted (tools/tourapi_bulk
    computes nearby over drafts too)."""
    by_id = {p["id"]: p for p in places}
    parent: dict[str, str] = {}
    rel: dict[str, str] = {}
    for p in places:
        po = part_of(p)
        if po.get("id") in by_id and po.get("id") != p["id"] and po.get("rel") in RELS:
            parent[p["id"]], rel[p["id"]] = po["id"], po["rel"]
    same: dict[str, set[str]] = defaultdict(set)
    parts: dict[str, set[str]] = defaultdict(set)
    for c, pid in parent.items():
        if rel[c] == "same_building":
            same[c].add(pid)
            same[pid].add(c)
        else:
            parts[pid].add(c)
    group = lambda i: {i, *same.get(i, ())} if i else set()  # noqa: E731
    fam = {}
    for p in places:
        i = p["id"]
        f = group(i) | group(parent.get(i, ""))
        for c in parts.get(i, ()):
            f |= group(c)
        f.discard(i)
        fam[i] = f
    alias = {c: pid for c, pid in parent.items() if rel[c] == "same_building"}
    return fam, alias


# ---------------------------------------------------------------- problems (validate)
def problems(entities_all: list[dict], built: list[dict]) -> list[tuple[str, str]]:
    """(where, message) for every relation that is malformed, points at a place that is not built (or does not
    exist), loops, runs deeper than MAX_DEPTH, or states a basis code evidence() does not reproduce; and every two
    built places that share a TourAPI contentid with no relation between them."""
    by_all = {e["id"]: e for e in entities_all}
    built_ids = {e["id"] for e in built}
    out = []
    for e in entities_all:
        if "part_of" not in e:
            continue
        where = f"{e['id']} {e.get('name', '')}"
        p = e.get("part_of")
        if not isinstance(p, dict):
            out.append((where, "part_of는 {id, rel, basis, checked_at} 객체여야 함"))
            continue
        extra = set(p) - {"id", "rel", "basis", "checked_at"}
        if extra:
            out.append((where, f"part_of에 모르는 키: {sorted(extra)}"))
        if p.get("rel") not in RELS:
            out.append((where, f"part_of.rel 값 오류: {p.get('rel')!r} (허용: {', '.join(RELS)})"))
        if not ISO.match(str(p.get("checked_at") or "")):
            out.append((where, f"part_of.checked_at이 YYYY-MM-DD가 아님: {p.get('checked_at')!r}"))
        basis = p.get("basis")
        if not isinstance(basis, list) or not basis:
            out.append((where, "part_of.basis가 비었음 — 근거 코드가 하나 이상 있어야 함"))
            basis = []
        bad = [b for b in basis if b not in BASIS]
        if bad:
            out.append((where, f"part_of.basis 코드 오류: {bad} (허용: {', '.join(BASIS)})"))
        parent = by_all.get(p.get("id"))
        if parent is None:
            out.append((where, f"part_of.id가 없는 장소: {p.get('id')}"))
            continue
        if parent is e:
            out.append((where, "part_of가 자기 자신을 가리킴"))
            continue
        if e["id"] in built_ids and parent["id"] not in built_ids:
            out.append((where, f"부모 장소가 이 빌드에 없음(비공개·중복·제외): {parent['id']} {parent.get('name', '')}"))
        if parent.get("duplicate_of"):
            out.append((where, f"부모 장소가 다른 장소의 중복(duplicate_of): {parent['id']}"))
        got = evidence(e, parent)
        for b in [b for b in basis if b in BASIS and b not in got]:
            out.append((where, f"part_of.basis '{b}'가 데이터에서 재현되지 않음({parent.get('name', '')}) — "
                               f"재현되는 근거: {', '.join(sorted(got)) or '없음'}"))
        # the chain upwards: no loop, at most MAX_DEPTH levels
        seen, cur, depth = {e["id"]}, parent, 1
        while cur is not None:
            if cur["id"] in seen:
                out.append((where, "part_of가 순환함"))
                break
            seen.add(cur["id"])
            nxt = part_of(cur).get("id")
            cur = by_all.get(nxt) if nxt else None
            depth += cur is not None
            if depth > MAX_DEPTH:
                out.append((where, f"part_of가 {MAX_DEPTH}단계보다 깊음"))
                break
    # two built pages for one TourAPI content must say how they relate
    by_cid: dict[str, list[dict]] = defaultdict(list)
    for e in built:
        cid = str((e.get("tourapi") or {}).get("contentid") or "").strip()
        if cid:
            by_cid[cid].append(e)
    for cid, xs in by_cid.items():
        for i, a in enumerate(xs):
            for b in xs[i + 1:]:
                if part_of(a).get("id") != b["id"] and part_of(b).get("id") != a["id"]:
                    out.append((f"{a['id']} {a['name']}", f"TourAPI contentid {cid}를 {b['id']} {josa(b['name'], '과/와')} 같이 쓰는데 "
                                                          "관계(part_of)가 없음"))
    return out


def fact_differences(built: list[dict]) -> list[tuple[str, str]]:
    """same_building partners whose shared fact keys hold different values while a page does not list the other's
    value beside its own (CLAUDE.md 3.2: both values shown) — a warning for a person to look at."""
    out = []
    for e in built:
        parent = e.get("_alias_of")
        if parent is None:
            continue
        fa, fb = e.get("facts") or {}, parent.get("facts") or {}
        for k in sorted(set(fa) & set(fb)):
            va, vb = squash_ws(str(fa.get(k) or "")), squash_ws(str(fb.get(k) or ""))
            if not va or not vb or va == vb or (k == "address" and norm_address(va) == norm_address(vb)):
                continue
            alts_a = {squash_ws(str(x.get("value") or "")) for x in (e.get("fact_alternatives") or {}).get(k) or []}
            alts_b = {squash_ws(str(x.get("value") or "")) for x in (parent.get("fact_alternatives") or {}).get(k) or []}
            if vb not in alts_a or va not in alts_b:
                side = "두 페이지 모두" if vb not in alts_a and va not in alts_b else (
                    f"{e['name']} 페이지" if vb not in alts_a else f"{parent['name']} 페이지")
                out.append((f"{e['id']} {e['name']}",
                            f"같은 건물 {josa(parent['name'], '과/와')} {FACT_LABELS.get(k, k)}({k}) 값이 다른데 {side}에 다른 쪽 값이 "
                            f"함께 보이지 않음: '{va[:30]}' / '{vb[:30]}' — fact_alternatives로 둘 다 보일지 확인"))
    return out
