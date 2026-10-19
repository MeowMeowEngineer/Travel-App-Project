"""The scenario QA of 2026-10-19, second round, place items in a real browser (Playwright + Chromium; skipped without
them): QA-67 the course card's hours of the trip day, QA-74 44px hit areas over a place's name and on '외 ↓', QA-75 an
event's time never broken inside, QA-77 a list card's values under their column heads. The build of
tests/test_qa2_place.py (made-up places on the Incheon configuration); the course is the planner's own code with a
scripted model (node, no network, no key)."""
import datetime as dt
import json
import mimetypes
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from test_qa2_place import site  # noqa: F401 — the module's build fixture

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
HOST = "http://site.test"


def _browser(p):
    try:
        return p.chromium.launch()
    except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
        pytest.skip(f"Chromium 없음: {ex}")


def _serve(out):
    def serve(route):
        url = route.request.url
        if not url.startswith(HOST + "/"):
            return route.abort()
        f = out / unquote(urlsplit(url).path).strip("/")
        if f.is_dir():
            f = f / "index.html"
        if not f.is_file():
            return route.fulfill(status=404, body="")
        return route.fulfill(status=200, body=f.read_bytes(),
                             content_type=mimetypes.guess_type(str(f))[0] or "application/octet-stream")
    return serve


def _page(b, out, w, h=900, init=None):
    phone = w < 768
    ctx = b.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if phone else 1, is_mobile=phone,
                        has_touch=phone, locale="ko-KR", timezone_id="Asia/Seoul")
    ctx.route("**/*", _serve(out))
    if init:
        ctx.add_init_script(init)
    return ctx.new_page()


# the hit area around an element's centre: how far every point on each axis still lands on it (its own box or an
# invisible layer it draws), as a tap or a click would
HIT = """(sel) => [...document.querySelectorAll(sel)].map((el) => {
  el.scrollIntoView({block: 'center'});
  const r = el.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const on = (dx, dy) => { const t = document.elementFromPoint(cx + dx, cy + dy); return !!t && (t === el || el.contains(t)); };
  const span = (f) => { let a = 0, b = 0; while (a < 40 && f(-(a + 1))) a++; while (b < 40 && f(b + 1)) b++; return a + b + 1; };
  return {t: el.textContent.trim(), w: span((d) => on(d, 0)), h: span((d) => on(0, d))};
})"""


def test_the_kind_links_and_the_more_link_have_44px_to_tap(site):
    """QA-74: '외 ↓' 28×28 and the kind links over the name 32px high at 1440 (at 390 a layer already gave 44)."""
    with sync_api.sync_playwright() as p:
        b = _browser(p)
        for w in (1440, 390):
            page = _page(b, site["out"], w)
            page.goto(f"{HOST}/places/test-kids-m/")
            more = page.evaluate(HIT, ".pl-head a.kf-more")
            assert more and all(x["w"] >= 44 and x["h"] >= 44 for x in more), (w, more)
            kinds = page.evaluate(HIT, ".pl-head .kicker a")
            assert kinds and all(x["h"] >= 44 for x in kinds), (w, kinds)
            page.context.close()
        b.close()


def test_an_event_time_is_never_split(site):
    """QA-75: at 360·390 the tile read '…(17:' / '00입장마감)'; every time stays on one line, the bracket whole."""
    ev = next((site["out"] / "events").glob("*/index.html")).parent.name
    lines_js = """() => { const el = document.querySelector('.kf-ev .kf-playtime .kf-main'), out = {};
      const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      for (let n = walk.nextNode(); n; n = walk.nextNode()) for (let i = 0; i < n.length; i++) {
        const c = document.createRange(); c.setStart(n, i); c.setEnd(n, i + 1); const r = c.getBoundingClientRect();
        if (r.width) { const k = Math.round(r.top); out[k] = (out[k] || '') + n.data[i]; } }
      return Object.keys(out).sort((a, b) => a - b).map((k) => out[k]); }"""
    with sync_api.sync_playwright() as p:
        b = _browser(p)
        for w in (360, 390, 1440):
            page = _page(b, site["out"], w)
            page.goto(f"{HOST}/events/{ev}/")
            lines = page.evaluate(lines_js)
            assert "".join(lines) == "10:00–18:00(17:00입장마감)", lines
            assert any("10:00–18:00" in x for x in lines) and any("(17:00입장마감)" in x for x in lines), (w, lines)
            page.context.close()
        b.close()


def test_a_card_with_a_gap_keeps_its_values_under_their_heads(site):
    """QA-77 at 1440: the empty cells are left out (one '확인 필요' line instead); each value stays in its column."""
    with sync_api.sync_playwright() as p:
        b = _browser(p)
        page = _page(b, site["out"], 1440)
        page.goto(f"{HOST}/shopping/")
        heads = dict(page.evaluate("""() => [...document.querySelectorAll('.lg-head span')].map((s) =>
          [s.textContent.trim(), Math.round(s.getBoundingClientRect().left)])"""))
        card = page.locator("li.rec", has_text="[테스트] 가상 상점 G")
        cells = card.evaluate("""(li) => [...li.querySelectorAll('.rec-cells > div')].map((d) =>
          [d.querySelector('dt').textContent, Math.round(d.getBoundingClientRect().left)])""")
        assert [c[0] for c in cells] == ["영업시간", "주차"]
        for label, left in cells:
            assert abs(heads[label] - left) <= 2, (label, left, heads)
        need = card.locator(".rec-need")
        assert need.inner_text() == "확인 필요: 쉬는 날·전화"
        assert need.bounding_box()["y"] > card.locator(".rec-cells > div").first.bounding_box()["y"]
        b.close()


def _next(weekday: int) -> str:
    """The next date (after today) on that weekday (Monday 0 … Sunday 6)."""
    t = dt.date.today() + dt.timedelta(days=1)
    return (t + dt.timedelta(days=(weekday - t.weekday()) % 7)).isoformat()


def _plan(out, date, stops):
    """A course from the planner's own code (checks, repair, finish) on this build's knowledge, the model scripted."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    js = f"""
const {{ loadKnowledge }} = await import({json.dumps((ROOT / 'chatbot/knowledge.js').as_uri())});
const {{ makePlan, validConditions }} = await import({json.dumps((ROOT / 'chatbot/planner.js').as_uri())});
const {{ useSite }} = await import({json.dumps((ROOT / 'chatbot/plan_prompt.js').as_uri())});
const {{ loadSite }} = await import({json.dumps((ROOT / 'chatbot/site.js').as_uri())});
const {{ fakeClient, toolRound }} = await import({json.dumps((ROOT / 'tests/js/fake_model.js').as_uri())});
useSite(loadSite({json.dumps(str(out / 'chat'))}));
const kb = await loadKnowledge({json.dumps(str(out / 'chat'))});
const days = [{{ date: {json.dumps(date)}, stops: {json.dumps(stops, ensure_ascii=False)} }}];
const c = validConditions({{ date: {json.dumps(date)}, days: 1, start: "12:00", end: "17:00", move: "car", with: "couple",
  adults: 2, kids: [], prefs: [], needs: [], budget: null, note: "" }}, new Date());
const out = [];
await makePlan({{ client: fakeClient([0, 1, 2, 3].map(() => toolRound([["submit_plan", {{ title: "시험", summary: "", notes: [], days }}]]))),
  kb, conditions: c, send: (e) => out.push(e), now: new Date() }});
process.stdout.write(JSON.stringify({{ conditions: c, plan: out.at(-1).plan }}));
"""
    r = subprocess.run([node, "--input-type=module", "-e", js], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout)


def test_a_course_card_shows_the_hours_of_its_day(site):
    """QA-67: on a Saturday the card read '시간 평일 11:30–23:00 · 금요일 12:00–24:00'; now that weekday's group under
    '그날 운영', and a value not given by weekday is labelled '이용시간', never as that day's."""
    stops = [{"page": "/places/test-diner-j/", "start": "12:30", "end": "13:30", "role": "meal", "why": ""},
             {"page": "/places/test-kids-m/", "start": "14:00", "end": "15:00", "role": "visit", "why": ""}]
    with sync_api.sync_playwright() as p:
        b = _browser(p)
        for weekday, want in ((5, "토요일 12:00–24:00 · 마지막 주문 23:30"), (6, "일요일 11:30–23:00")):
            state = _plan(site["out"], _next(weekday), stops)
            assert [s["day"] for s in state["plan"]["days"][0]["stops"]] == ["open", "open"]
            init = f"sessionStorage.setItem('gs-plan', {json.dumps(json.dumps(state, ensure_ascii=False))});"
            page = _page(b, site["out"], 390, 844, init)
            page.goto(f"{HOST}/plan/")
            page.wait_for_selector(".trp-stop")
            rows = page.evaluate("""() => [...document.querySelectorAll('.trp-stop')].map((s) =>
              [...s.querySelectorAll('.trp-facts li')].map((li) => [...li.children].map((x) => x.textContent)))""")
            assert ["시간", want] in rows[0], rows[0]
            assert ["이용시간", "10:00–18:00"] in rows[1], rows[1]
            page.context.close()
        b.close()
