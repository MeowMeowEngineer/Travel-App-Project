"""The home's centre question card (owner 2026-10-13, after the explorer card of Mention Atlas): ask the site
assistant (chat.js, CLAUDE.md 3.10) from the middle of the home page.

templates/_ask.html.j2 draws the card; this module gives it its starter questions from data/<region>/ask.json:
  {"starters": [{"q": {"ko": "○○섬 가는 법", "en": "How do I get to ○○ Island?"}, "guide": "guide-08"},
                {"q": {"ko": "이번 달 행사·축제", "en": "Events this month"}, "page": "events"}, …]}
A starter is a question the assistant answers when JS runs and, as a plain link, the page that answers it — a guide
(by id) or a list (PAGES) — so the card does something without JS and every starter is a real page of the build.
A starter whose page this build (or this language) does not have is left out. The file also turns the card on: no
file, no card (pipeline/build.State.ask is None and the homes render as before); a file without starters gives the
card without its starter row. The questions are kept in every language the site has (ko, en, ja, zh-Hans, zh-Hant,
de, fr, es, ru); a language shows its chips only where its pages exist.
"""
from __future__ import annotations

import json
from pathlib import Path

PAGES = ("events",)
MAX_Q = 40   # a starter is a chip: one short question


def load(data_dir: Path) -> list[dict]:
    p = Path(data_dir) / "ask.json"
    if not p.exists():
        return []
    return [x for x in json.loads(p.read_text("utf-8")).get("starters") or [] if isinstance(x, dict)]


def starters(items: list[dict], lang: str, guide_paths: dict[str, str], pages: dict[str, str]) -> list[dict]:
    """[{q, href}] in one language. guide_paths: {guide id: its path in that language}; pages: {PAGES key: path} for
    the lists the build has in that language."""
    out = []
    for it in items:
        q = " ".join(str((it.get("q") or {}).get(lang) or "").split())
        href = guide_paths.get(it["guide"]) if it.get("guide") else pages.get(it.get("page") or "")
        if q and href:
            out.append({"q": q, "href": href})
    return out


def data_problems(data_dir: Path, guide_ids: set[str]) -> list[str]:
    errs = []
    for i, it in enumerate(load(data_dir)):
        where = f"starters[{i}]"
        q = it.get("q") if isinstance(it.get("q"), dict) else {}
        if not str(q.get("ko") or "").strip():
            errs.append(f"{where}: q.ko(한국어 질문)가 없습니다")
        for lang, text in q.items():
            if len(str(text)) > MAX_Q:
                errs.append(f"{where}: q.{lang}가 {MAX_Q}자를 넘습니다 — 칩에 들어갈 짧은 질문으로")
        if bool(it.get("guide")) == bool(it.get("page")):
            errs.append(f"{where}: guide(가이드 id)와 page({', '.join(PAGES)}) 중 하나만 둡니다")
        elif it.get("guide") and it["guide"] not in guide_ids:
            errs.append(f"{where}: 없는 가이드 {it['guide']}")
        elif it.get("page") and it["page"] not in PAGES:
            errs.append(f"{where}: page는 {', '.join(PAGES)} 중 하나입니다")
    return errs
