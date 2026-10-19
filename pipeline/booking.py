"""예약하기, step 1 (2026-10-16): the official booking pages a page links as buttons.

Only addresses the data already holds become buttons, so nothing here is guessed (CLAUDE.md 3.1):
- the registry data/<region>/booking.json (build.State.booking): public or official booking services (intercity buses,
  rail, island ferries, the national forests, and the city's own — a city tour, a campground, flights), each with the
  basis in our data that it is where the booking is made and the date it was checked; the places each one belongs to.
  A service's name in each version is the registry's own (services.<key>.names {code: name}), else the national
  services' names (locales.BOOK_WORDS svc);
- a place's own facts.reservationurl (TourAPI) when its host is not an OTA, Naver, a blog or a social network
  (exclude_hosts — those stay plain fact rows: step 2 is the operator's decision), the sources do not disagree on it
  (CLAUDE.md 3.2: never pick one) and dead_links.json does not list it.
A version's page opens the service's page in that language when the registry has one (pages), else the Simplified
Chinese one for zh-hant, else the English one — labelled with that language's name — else the Korean page with the
version's '(in Korean)'. A facility's own address is shown by its domain, with no language claimed.
Templates: _ui.html.j2 book() (data-block="booking", data-track="booking_click", data-provider = the service key or
'reservationurl'); pipeline.validate booking_problems checks every page against view(); the chat knows them
(pipeline/chat_index.py '예약하기' lines and docs.json 'book').
"""
from __future__ import annotations

from urllib.parse import urlsplit

from . import locales as LC
from .textutil import dead_reason, link_url, squash_ws, url_key, web_text

# A cited booking site's own page in a reader's language (QA 2026-10-15 SRC-05b), next to the cited page (the source of
# record stays the page this site read): {host: {locale code: URL}}, each opened on 2026-10-15 — Bustago in English,
# Japanese and Simplified Chinese, the KSA ferry booking in English (its ?lang=jp still shows Korean). A version with no
# page of its own gets the Simplified Chinese one (zh-hant), else the English one; labelled with that language's name.
# (Moved from en_site.py; booking.json's 'pages' of these services hold the same addresses — tests/test_booking.py.)
OFFICIAL_ENTRY = {
    "www.bustago.or.kr": {"en": "https://www.bustago.or.kr/newweb/en/index.do",
                          "ja": "https://www.bustago.or.kr/newweb/jp/index.do",
                          "zh-hans": "https://www.bustago.or.kr/newweb/cn/index.do"},
    "island.theksa.co.kr": {"en": "https://island.theksa.co.kr/page/booking?lang=en"},
}
PLACE_MAX = 2      # buttons on a place page (its registry services, then its own booking address)
OWN = "reservationurl"


def official_entry(url: str, code: str) -> tuple[str, str] | None:
    """(the locale code of the page, its URL) of OFFICIAL_ENTRY for a cited URL in this version, else None."""
    pages = OFFICIAL_ENTRY.get(urlsplit(url or "").hostname or "")
    if not pages:
        return None
    key = page_lang(pages, code)
    return (key, pages[key]) if key else None


def page_lang(pages: dict, code: str) -> str:
    """The locale code of the page a reader of `code` gets from {code: URL}: their own, Simplified Chinese for
    Traditional, else English; '' when none of these exists."""
    if code in pages:
        return code
    if code == "zh-hant" and "zh-hans" in pages:
        return "zh-hans"
    return "en" if "en" in pages else ""


def registry(S) -> dict:
    return getattr(S, "booking", None) or {}


def _host(url: str) -> str:
    return (urlsplit(url or "").hostname or "").lower().removeprefix("www.")


def excluded(url: str, reg: dict) -> bool:
    """The address is on a host booking.json keeps from buttons (OTA, Naver, blogs, social networks), subdomains too."""
    host = _host(url)
    for h in reg.get("exclude_hosts") or []:
        h = h.lower().removeprefix("www.")
        if host == h or host.endswith("." + h):
            return True
    return False


def _svc(reg: dict, key: str) -> dict | None:
    s = (reg.get("services") or {}).get(key)
    return ({"key": key, "url": s["url"], "pages": dict(s.get("pages") or {}), "names": dict(s.get("names") or {})}
            if s and s.get("url") else None)


def _order(reg: dict, keys) -> list[dict]:
    """Services in the registry's order (booking.json 'services' is the button order)."""
    keys = set(keys)
    return [t for t in (_svc(reg, k) for k in (reg.get("services") or {}) if k in keys) if t]


def place_targets(S, e: dict | None, services_only: bool = False) -> list[dict]:
    """A place's booking targets: its registry services, then its own facts.reservationurl (see the module notes);
    deduplicated by address, at most PLACE_MAX. services_only: the registry's (a course box lists no hotel)."""
    reg = registry(S)
    if not reg or not e or e.get("id") in (reg.get("exclude_places") or {}):
        return []
    out = [t for t in (_svc(reg, k) for k in (reg.get("places") or {}).get(e.get("id"), [])) if t]
    if not services_only:
        url = link_url((e.get("facts") or {}).get(OWN))
        from .present import contested
        if url and not excluded(url, reg) and not contested(e, OWN) \
                and not dead_reason(url, getattr(S, "dead_links", None)):
            out.append({"key": OWN, "url": url, "pages": {}})
    seen, uniq = set(), []
    for t in out:
        if url_key(t["url"]) not in seen:
            seen.add(url_key(t["url"]))
            uniq.append(t)
    return uniq[:PLACE_MAX]


def guide_text(g: dict) -> str:
    return "\n".join([squash_ws(g.get("summary"))] + [squash_ws(b.get("text")) for b in g.get("body") or []])


def guide_targets(S, g: dict | None) -> list[dict]:
    """The services a guide cites as a source (url or match, compared by url_key) or names by host in its summary or
    body (present.web_rx: the hosts the text links), in the registry's order."""
    reg = registry(S)
    if not reg or not g:
        return []
    from .present import web_rx
    srcs = {url_key(s.get("url")) for s in g.get("sources") or [] if s.get("url")}
    hosts = {m.group(1) for m in web_rx().finditer(guide_text(g))}
    keys = []
    for key, s in (reg.get("services") or {}).items():
        own = {url_key(u) for u in [s.get("url"), *(s.get("match") or [])] if u}
        if own & srcs or set(s.get("hosts") or []) & hosts:
            keys.append(key)
    return _order(reg, keys)


def course_targets(S, c: dict | None) -> list[dict]:
    """The services of a course's stop guides ('guide-32#h-b5') and stop places (registry services only)."""
    reg = registry(S)
    if not reg or not c:
        return []
    guides = getattr(S, "guide_by_id", None) or {}
    keys = []
    for s in c.get("stops") or []:
        g = guides.get(str(s.get("guide") or "").split("#")[0])
        keys += [t["key"] for t in guide_targets(S, g)]
        keys += [t["key"] for t in place_targets(S, S.ent_by_slug.get(s.get("place_slug") or ""), services_only=True)]
    return _order(reg, keys)


def service_name(t: dict, code: str) -> str:
    """A service's name in version `code`: the registry's own (names), else the national one (locales.BOOK_WORDS)."""
    return squash_ws((t.get("names") or {}).get(code)) or squash_ws((LC.BOOK_WORDS[code].get("svc") or {}).get(t["key"]))


def view(targets: list[dict], code: str, in_korean=None) -> list[dict]:
    """What a page of version `code` prints for each target: {key, url, hreflang, name, note, note_lang} (see the
    module notes). in_korean(name): the version's '{name} (in Korean)' (en_site UIText chrome.in_korean_paren)."""
    out = []
    for t in targets:
        row = {"key": t["key"], "url": t["url"], "hreflang": "", "name": "", "note": "", "note_lang": ""}
        if t["key"] == OWN:
            row["name"] = web_text(t["url"])   # the facility's own site: its domain, no language claimed
        elif code == "ko":
            row["name"] = service_name(t, "ko")
        else:
            k = page_lang(t["pages"], code)
            name = service_name(t, code)
            if k:
                loc = LC.get(k)
                row.update(url=t["pages"][k], hreflang=loc.html, name=name)
                if k != code:
                    row.update(note=loc.label, note_lang=loc.html)
            else:
                row.update(hreflang="ko", name=in_korean(name) if in_korean else name)
        out.append(row)
    return out


def data_problems(S) -> list[str]:
    """booking.json itself (pipeline.validate): every service has its address, the basis that it is where the booking
    is made, the date that was checked and a name in Korean and every version (its names, else locales.BOOK_WORDS); no
    address of a
    service is on an excluded host; its pages are versions this site has; every place id is a place of the data and
    names known services."""
    reg = registry(S)
    if not reg:
        return []
    out = []
    services = reg.get("services") or {}
    for key, s in services.items():
        if not link_url(s.get("url")):
            out.append(f"services.{key}: url 없음")
        for k in ("basis", "checked_at"):
            if not squash_ws(s.get(k)):
                out.append(f"services.{key}: {k} 없음")
        for code in LC.BOOK_WORDS:
            if not service_name({"key": key, "names": s.get("names")}, code):
                out.append(f"services.{key}: {code} 이름(booking.json names 또는 locales.BOOK_WORDS svc) 없음")
        for lang in s.get("pages") or {}:
            if lang not in LC.LOCALES:
                out.append(f"services.{key}: pages에 이 사이트에 없는 언어 {lang}")
        for u in [s.get("url"), *(s.get("pages") or {}).values(), *(s.get("match") or [])]:
            if u and excluded(u, reg):
                out.append(f"services.{key}: 버튼에서 빼는 호스트의 주소 {u}")
    known = {e.get("id") for e in getattr(S, "entities_all", None) or []}
    for pid, keys in (reg.get("places") or {}).items():
        if pid not in known:
            out.append(f"places.{pid}: places.json에 없는 장소")
        out += [f"places.{pid}: 없는 서비스 {k}" for k in keys if k not in services]
    return out


def allowed_urls(S) -> set[str]:
    """Every address a booking button may open: the registry's pages and the published places' own booking addresses
    (url_key form)."""
    reg = registry(S)
    out = set()
    for s in (reg.get("services") or {}).values():
        out |= {url_key(u) for u in [s.get("url"), *(s.get("pages") or {}).values()] if u}
    for e in getattr(S, "entities", None) or []:
        for t in place_targets(S, e):
            out.add(url_key(t["url"]))
    return out
