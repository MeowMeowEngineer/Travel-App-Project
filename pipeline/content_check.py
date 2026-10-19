"""Checks on the sentences this site writes (place summary · FAQ · '자세히', guide and course text, event summary)
against the source texts a record keeps. The city-neutral checks of the sample city's writing tools, for any region;
tools/content_check.py runs them over a data folder, and pipeline/validate.py runs the copy check on every built page.

- copy (CLAUDE.md 3절 3항): a written sentence shares COPY_LIMIT (15) or more consecutive characters with a stored
  source text — a place's TourAPI overview (`tourapi.overview`, kept to check facts, never shown) or its original
  (`original.text`), a guide's or course's places' texts — once the names and fact values in that stretch are taken
  out (a name or a value may be written as the source writes it).
- wording (3절 5항): source commentary ('원문은 …', '~라고 합니다'), a '확인 필요' answer (the page prints that itself),
  evaluative modifiers with no source.
- numbers: every number in a summary, an FAQ answer or a '자세히' paragraph appears in the record's facts, the other
  sources' values, its names, category, address or source texts.
- FAQ (3절 6항): the question is 존댓말 ('~나요?/~인가요?'), its source is one of the record's own sources, and the
  same question is not on another place page.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .textutil import josa, squash_ws, web_url

COPY_LIMIT = 15
TOURAPI = "한국관광공사 TourAPI"
BANNED = [
    (r"원문[은는이에서의]", "출처 해설체('원문은…')"),
    (r"(소개|설명|안내)(합니다|한다|하고 있|되어 있)", "출처 해설체('~를 소개합니다')"),
    (r"라고\s*(합니다|한다|전합니다|알려져)", "전언체('~라고 합니다')"),
    (r"(자료|정보)(에|가)\s*(없|나와 있지|기재되어 있지)", "'자료에 없음' 답변"),
    (r"확인(이)?\s*필요", "'확인 필요' 문구(화면이 블록마다 한 번 자동 표시)"),
    (r"최고|최상|꼭\s|필수|인기|아름다운|아름답|멋진|환상|완벽|강추|유명한|손꼽|명소 중|대표적인 명소|낭만|감성 가득|힐링",
     "근거 없는 수식어"),
]
JONDAE = re.compile(r"(나요|까요|습니까|가요|인가요|세요|되나요|있나요|하나요|던가요|을까요|일까요)\?$")


def longest_copy(text: str, source: str, allowed: list[str] | tuple[str, ...] = ()) -> str:
    """The longest stretch `text` shares with `source` when it is COPY_LIMIT characters or more and is not made of
    allowed words (names, fact values) — else ''."""
    a, b = squash_ws(text), squash_ws(source)
    if not a or not b:
        return ""
    m = SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    if m.size < COPY_LIMIT:
        return ""
    span = rest = a[m.a:m.a + m.size]
    for word in sorted((squash_ws(w) for w in allowed if squash_ws(w)), key=len, reverse=True):
        rest = rest.replace(word, "")
    return span if len(re.sub(r"[\s.,·()]", "", rest)) >= COPY_LIMIT - 3 else ""


def wording(text: str, names: tuple[str, ...] = ()) -> list[str]:
    """The banned expressions in `text` (names taken out first: a place may be called '…명소')."""
    for name in sorted((n for n in names if n), key=len, reverse=True):
        text = (text or "").replace(name, " ")
    return [f"{label}: …{m.group(0)}…" for pat, label in BANNED for m in [re.search(pat, text or "")] if m]


def numbers(text: str) -> set[str]:
    return {x.lstrip("0") or "0" for x in re.findall(r"\d+", text or "")}


def names_of(e: dict) -> list[str]:
    return [n for n in dict.fromkeys([squash_ws(e.get("name")), *(squash_ws(x) for x in e.get("alternate_names") or []),
                                      squash_ws((e.get("tourapi") or {}).get("title"))]) if n]


def source_texts(e: dict) -> list[tuple[str, str]]:
    """(label, text) of every source text the record keeps: TourAPI's overview, the original."""
    out = []
    if squash_ws((e.get("tourapi") or {}).get("overview")):
        out.append((f"{TOURAPI} overview", e["tourapi"]["overview"]))
    if squash_ws(e.get("overview")):
        out.append((f"{e.get('source_name') or TOURAPI} overview", e["overview"]))
    orig = e.get("original") or {}
    if squash_ws(orig.get("text")):
        out.append((f"{orig.get('source_name') or '원문'} 원문", orig["text"]))
    return out


def fact_values(e: dict) -> list[str]:
    vals = [squash_ws(v) for v in (e.get("facts") or {}).values()]
    vals += [squash_ws(a.get("value")) for alts in (e.get("fact_alternatives") or {}).values() for a in alts or []]
    return [v for v in vals if v]


def record_sources(e: dict) -> set[str]:
    """What an FAQ answer may name as its source: the record's source pages and the providers of its values."""
    orig, official = e.get("original") or {}, e.get("official") or {}
    out = {orig.get("source_url"), official.get("source_url"), official.get("visitkorea_url"),
           web_url(official.get("homepage") or "") or None, web_url((e.get("facts") or {}).get("homepage") or "") or None}
    for src in [e.get("facts_source") or {}, *(e.get("fact_sources") or {}).values(),
                *(a for alts in (e.get("fact_alternatives") or {}).values() for a in alts or [])]:
        if isinstance(src, dict):
            out |= {src.get("provider"), src.get("url"), web_url(src.get("url") or "") or None}
    if (e.get("tourapi") or {}).get("contentid"):
        out.add(TOURAPI)
    return {squash_ws(x) for x in out if squash_ws(x)}


def _texts(e: dict) -> list[tuple[str, str]]:
    """(where, text) of what we wrote for one place."""
    out = [("summary", squash_ws(e.get("summary")))]
    for i, f in enumerate(e.get("faq") or []):
        out += [(f"faq[{i}].q", squash_ws(f.get("q"))), (f"faq[{i}].a", squash_ws(f.get("a")))]
    out += [(f"details[{i}]", squash_ws(d.get("text"))) for i, d in enumerate(e.get("details") or [])]
    return [(w, t) for w, t in out if t]


def copy_issues(e: dict, extra_sources: list[tuple[str, str]] = (), allowed: list[str] = ()) -> list[str]:
    """Copy findings for one place (or any record with summary / faq / details)."""
    allowed = [*names_of(e), *(w for n in names_of(e) for w in n.split()), *fact_values(e), *allowed]
    issues = []
    for where, text in _texts(e):
        for label, src in [*source_texts(e), *extra_sources]:
            span = longest_copy(text, src, allowed)
            if span:
                issues.append(f"{where} {josa(label, '과/와')} {len(span)}자 연속 일치: '{span}'")
    return issues


def place_issues(e: dict, seen_q: dict[str, str] | None = None) -> list[str]:
    """Every finding for one place's written text (copy, wording, numbers, FAQ)."""
    names = names_of(e)
    issues = copy_issues(e)
    known = numbers(" ".join([*names, *fact_values(e), squash_ws(e.get("category")), squash_ws(e.get("district")),
                              *(t for _, t in source_texts(e))]))
    sources = record_sources(e)
    for where, text in _texts(e):
        issues += [f"{where} {w}" for w in wording(text, tuple(names))]
        unknown = sorted(numbers(text) - known, key=int)
        if unknown and not where.endswith(".q"):
            issues.append(f"{where} 사실·출처 글에 없는 숫자 {unknown}")
    for i, f in enumerate(e.get("faq") or []):
        q = squash_ws(f.get("q"))
        if not JONDAE.search(q):
            issues.append(f"faq[{i}].q 존댓말 의문형('~나요?/~인가요?')이 아님: {q}")
        if squash_ws(f.get("source")) not in sources:
            issues.append(f"faq[{i}].source가 이 장소의 출처({', '.join(sorted(sources)) or '없음'})가 아님: {f.get('source')}")
        if seen_q is not None:
            if q in seen_q and seen_q[q] != e.get("id"):
                issues.append(f"faq[{i}].q 같은 질문이 {seen_q[q]}에도 있음: {q}")
            seen_q.setdefault(q, e.get("id"))
    return issues


def guide_issues(g: dict, places_by_slug: dict[str, dict], copy_only: bool = False) -> list[str]:
    """A guide's or course's written text against its own original and the source texts of the places it points to
    (copy_only: the copy check alone, as validate runs it)."""
    linked = [places_by_slug[s] for s in dict.fromkeys(x.get("place_slug") for x in [*(g.get("items") or []),
                                                                                    *(g.get("stops") or [])])
              if s in places_by_slug]
    allowed = [n for p in linked for n in names_of(p)] + [v for p in linked for v in fact_values(p)]
    allowed += [squash_ws(s.get("name")) for s in g.get("stops") or []]
    sources = [*source_texts(g), *(s for p in linked for s in source_texts(p))]
    texts = [("summary", squash_ws(g.get("summary")))]
    texts += [(f"body[{i}]", squash_ws(b.get("text"))) for i, b in enumerate(g.get("body") or [])]
    texts += [(f"items[{i}].reason", squash_ws(it.get("reason"))) for i, it in enumerate(g.get("items") or [])]
    issues = []
    for i, f in enumerate(g.get("faq") or []):
        q = squash_ws(f.get("q"))
        texts += [(f"faq[{i}].q", q), (f"faq[{i}].a", squash_ws(f.get("a")))]
        if not JONDAE.search(q) and not copy_only:
            issues.append(f"faq[{i}].q 존댓말 의문형('~나요?/~인가요?')이 아님: {q}")
    for where, text in texts:
        if not text:
            continue
        if copy_only:
            issues += [f"{where} {josa(label, '과/와')} {len(s)}자 연속 일치: '{s}'" for label, src in sources
                       for s in [longest_copy(text, src, allowed)] if s]
            continue
        # a guide's body may say '확인 필요' (it is not a fact block); its FAQ answers may not
        issues += [f"{where} {w}" for w in wording(text, tuple(allowed)) if "확인 필요" not in w or where.startswith("faq")]
        for label, src in sources:
            span = longest_copy(text, src, allowed)
            if span:
                issues.append(f"{where} {josa(label, '과/와')} {len(span)}자 연속 일치: '{span}'")
    return issues


def data_issues(places: list[dict], guides: list[dict] = (), courses: list[dict] = (),
                events: list[dict] = ()) -> dict[str, list[str]]:
    """{record id: findings} for every live record with written text (duplicates and excluded records skipped)."""
    live = [p for p in places if not p.get("duplicate_of") and not p.get("exclude")]
    by_slug = {p.get("slug"): p for p in live}
    seen_q: dict[str, str] = {}
    out: dict[str, list[str]] = {}
    for p in live:
        found = place_issues(p, seen_q)
        if found:
            out[p.get("id") or p.get("slug")] = found
    for g in [*guides, *courses]:
        if g.get("exclude") or g.get("duplicate_of"):
            continue
        found = guide_issues(g, by_slug)
        if found:
            out[g.get("id") or g.get("slug")] = found
    for ev in events:
        if ev.get("exclude") or ev.get("duplicate_of"):
            continue
        text = squash_ws(ev.get("summary"))
        found = [f"summary {w}" for w in wording(text, tuple(names_of(ev)))] if text else []
        found += [f"summary {josa(label, '과/와')} {len(s)}자 연속 일치: '{s}'" for label, src in source_texts(ev)
                  for s in [longest_copy(text, src, [*names_of(ev), squash_ws(ev.get("place_name"))])] if s]
        if found:
            out[ev.get("id") or ev.get("slug")] = found
    return out
