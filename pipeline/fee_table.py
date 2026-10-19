"""A place's admission fee value read as a table — review 2026-10-17 (AI 코스 만들기 집중 평가 CE01·CE03).

The course planner priced a plan from what the model wrote: a combined ticket counted twice, a paid museum left out,
any unit price taken as 'the page's value'. The planner now prices every visit itself (chatbot/plan_fees.js) from
the place's own fee value, read here into numbers once at build time and carried in docs.json (f.fee):

    {"free": True, "note"?: "단, 여객선 비용 별도"}                         the value says entry is free
    {"tab": {"성인": 2000, "청소년·군인": 1000, "어린이": 500},            the table a visitor from outside the city
     "tl": "개별권", "aw"?: "일반",                                     pays one by one, its heading, the adult price's word
     "fr": [{"w": "6세 이하 유아", "max": 6}, {"w": "65세 이상 경로", "min": 65}, {"w": "장애인"},
            {"w": "매주 수요일 문화가 있는 날", "wd": 3}],              who enters free as the value says it
     "ag": {"어린이": [7, 12]}}                                         a category's ages, when the value gives them
    {} — a value that names no table this reader can be priced from (rooms, months, ferries): the planner says 확인 필요

Only what the value writes: a category the table has no ages for stays a name (the planner never maps an age to it),
a resident's price (○○시민·거주자) and a group's (단체) are not the visitor's, a combined ticket's table is the
ticket's (data/<region>/tickets.json), not the place's.
"""
from __future__ import annotations

import re

WEEK = "일월화수목금토"
# the categories a table may name, as the value writes them → one name per category
CATS = (("성인", "성인"), ("어른", "성인"), ("일반", "성인"), ("대인", "성인"),
        ("청소년·군인", "청소년·군인"), ("청소년,군인", "청소년·군인"), ("청소년, 군인", "청소년·군인"),
        ("청소년/군인", "청소년·군인"), ("청소년 / 군인", "청소년·군인"), ("청소년", "청소년"),
        ("어린이", "어린이"), ("소인", "소인"))
NOT_VISITOR = re.compile(r"통합권|단체|거주자|시민")   # 시민: any city's residents (○○시민)
PREFERRED = ("개별권", "타지역", "개인")
PRICE = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\s*원")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _sections(text: str) -> list[tuple[str, str]]:
    """[(heading, body)] split at '[heading]'; text before the first heading has heading ''."""
    parts = re.split(r"\[([^\]]{1,40})\]", text)
    out = [("", parts[0])]
    for i in range(1, len(parts) - 1, 2):
        out.append((_flat(parts[i]), parts[i + 1]))
    return [(h, b) for h, b in out if _flat(b)]


def _prices(body: str, words: dict | None = None) -> dict[str, int]:
    """{category: price} for '- 성인 2,000원' lines (the first price after the category name; a price in brackets
    right after it — the resident's — is not read). words, when given, gets each category's word as the table
    writes it ('일반' for 성인)."""
    out: dict[str, int] = {}
    flat = _flat(body.split("※")[0])
    for raw, cat in CATS:
        if cat in out:
            continue
        # '성인 2,000원', '성인 : 500원', '성인(○○시거주자) 1,000원(500원)' — the bracket after the name says whose
        # price the bracket after the amount is; the first amount is the visitor's
        m = re.search(re.escape(raw) + r"\s*(?:\([^)]{0,12}\))?\s*[:：]?\s*" + PRICE.pattern, flat)
        if m:
            out[cat] = int(m.group(1).replace(",", ""))
            if words is not None:
                words[cat] = raw
    # '청소년' alone when '청소년·군인' was read is the same price written again
    if "청소년" in out and "청소년·군인" in out and out["청소년"] == out["청소년·군인"]:
        del out["청소년"]
    return out


def _free_rules(text: str) -> list[dict]:
    """Who enters free, as the value lists it after '무료' ('※ 무료 : 6세 이하 유아 / 65세 이상 경로대상자 / 매주 수요일
    문화가 있는 날 무료 관람', '무료입장 6세이하 유아, 65세이상 어른, 장애인, 유공자', '※ 무료 : 만 36개월 미만')."""
    out = []
    m = re.search(r"무료\s*(?:입장|관람)?\s*[:：]?\s*(.+?)(?:※|$)", _flat(text))
    if not m:
        return out
    for part in re.split(r"\s*[/,·]\s*", m.group(1)):
        part = _flat(part)
        if not part:
            continue
        rule: dict = {"w": part}
        if (a := re.search(r"만\s*(\d+)\s*개월\s*미만", part)):
            rule["max"] = (int(a.group(1)) - 1) // 12
        elif (a := re.search(r"(\d+)\s*세\s*이하", part)):
            rule["max"] = int(a.group(1))
        elif (a := re.search(r"(\d+)\s*세\s*이상", part)):
            rule["min"] = int(a.group(1))
        elif (a := re.search(r"매주\s*([월화수목금토일])요일", part)):
            rule["wd"] = WEEK.index(a.group(1))
        elif not re.search(r"장애인|유공자", part):
            continue   # words the planner cannot apply ('문화가 있는 날' alone, a list's leftovers)
        out.append(rule)
    return out


def parse(text: str) -> dict:
    """The visitor's fee table of one fee value (see the module doc)."""
    flat = _flat(text)
    if not flat:
        return {}
    if re.match(r"^무료(?:\s|$|\()", flat) and not PRICE.search(flat):
        note = re.search(r"\(\s*※?\s*(단[,.]?\s*[^)]+)\)", flat)
        return {"free": True, **({"note": _flat(note.group(1))} if note else {})}
    out: dict = {}
    sections = _sections(text)
    chosen = None
    for want in PREFERRED:
        chosen = next(((h, b) for h, b in sections if want in h and not NOT_VISITOR.search(h)), None)
        if chosen:
            break
    if chosen is None:
        plain = [(h, b) for h, b in sections if not h]
        if len(sections) == 1 and plain:
            chosen = plain[0]
    if chosen is not None:
        words: dict = {}
        tab = _prices(chosen[1], words)
        if "성인" in tab:   # a table without an adult price is not one this reader can be priced from
            out["tab"] = tab
            if words.get("성인", "성인") != "성인":   # the table's own word ('일반'): the planner quotes it
                out["aw"] = words["성인"]
            if chosen[0]:
                out["tl"] = chosen[0]
    ages = {}
    for raw, cat in CATS:
        if (m := re.search(re.escape(raw) + r"\s*\(\s*(\d+)\s*[~～-]\s*(\d+)\s*세\s*\)", flat)):
            ages[cat] = [int(m.group(1)), int(m.group(2))]
    if ages and out.get("tab"):
        out["ag"] = ages
    fr = _free_rules(text)
    if fr and out.get("tab"):
        out["fr"] = fr
    return out
