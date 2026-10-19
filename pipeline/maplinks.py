"""Map / navigation links built from a place name, address, coordinates and optional IDs.

Precision matters: a link that opens the exact place is better than one that only opens a
search box. Every link carries `precise: True/False`; imprecise links are labelled "(검색)".

Documented URL patterns used:
- Google Maps URLs (developers.google.com/maps/documentation/urls):
    search : https://www.google.com/maps/search/?api=1&query=...&query_place_id=...
    route  : https://www.google.com/maps/dir/?api=1&destination=...&destination_place_id=...
- Kakao (the map provider since the owner's decision of 2026-10-14). With a Kakao place ID
  (map_ids.kakao_place_id, matched by tools/kakao_places.py from the Kakao Local keyword API) the links open the
  place itself — its own Kakao place page with reviews — instead of a pin at an address:
    https://place.map.kakao.com/{kakao_place_id}        (the place page; label '카카오맵', precise)
    https://map.kakao.com/link/to/{kakao_place_id}      (route to the place: '길찾기 바로가기 /link/to/장소ID',
                                                         apis.map.kakao.com/web/guide '지도 URL')
  Without an ID, the coordinate links of the same guide:
    https://map.kakao.com/link/map/{name},{lat},{lng}   (pin at coordinates)
    https://map.kakao.com/link/to/{name},{lat},{lng}    (route to coordinates)
    https://map.kakao.com/link/search/{query}
  kakao_place_url / kakao_route_url are the single builders; pipeline/present.py (a course's first stop) and
  pipeline/en_site.py (through build_links) use them, so every page of a place opens the same Kakao place.
- Naver Map web:
    https://map.naver.com/p/entry/place/{naver_place_id}  (exact place, if the ID is known)
    https://map.naver.com/p/search/{query}                 (search)
- TMAP: mobile app scheme only. The pattern lives in site.json (tmap_scheme) and MUST be
  tested on a real phone before launch.
"""
from __future__ import annotations

from urllib.parse import quote, urlencode

DEFAULT_TMAP_SCHEME = "tmap://route?goalname={name}&goalx={lng}&goaly={lat}"


def _q(s: str) -> str:
    return quote(s, safe="")


def kakao_place_url(kakao_place_id) -> str:
    """The Kakao place page of a matched place ('' without an ID)."""
    kid = str(kakao_place_id or "").strip()
    return f"https://place.map.kakao.com/{_q(kid)}" if kid else ""


def kakao_route_url(name: str, lat: float | None = None, lng: float | None = None, kakao_place_id="") -> str:
    """Kakao route: to the place ID when known, else to the coordinates ('' when neither)."""
    kid = str(kakao_place_id or "").strip()
    if kid:
        return f"https://map.kakao.com/link/to/{_q(kid)}"
    if lat is not None and lng is not None:
        return f"https://map.kakao.com/link/to/{_q(name)},{lat},{lng}"
    return ""


def kakao_transit_url(a_name: str, a_lat, a_lng, b_name: str, b_lat, b_lng) -> str:
    """Kakao public-transport directions between two coordinates ('/link/by/traffic/이름,위도,경도/이름,위도,경도',
    apis.map.kakao.com/web/guide 길찾기 바로가기; the transit mode takes no via points and no place IDs here): the map
    computes the route and its times — the site states none (course pages, QA 2026-10-15 F09)."""
    return f"https://map.kakao.com/link/by/traffic/{_q(a_name)},{a_lat},{a_lng}/{_q(b_name)},{b_lat},{b_lng}"


def google_transit_url(a_lat, a_lng, b_lat, b_lng) -> str:
    """Google Maps transit directions between two coordinates (Maps URLs: dir, travelmode=transit)."""
    return "https://www.google.com/maps/dir/?" + urlencode(
        {"api": "1", "origin": f"{a_lat},{a_lng}", "destination": f"{b_lat},{b_lng}", "travelmode": "transit"})


def _with_region(name: str, region: str | None) -> str:
    if region and region not in name:
        return f"{region} {name}"
    return name


def build_links(
    name: str,
    lat: float | None = None,
    lng: float | None = None,
    region: str = "",
    address: str = "",
    naver_place_id: str = "",
    google_place_id: str = "",
    tmap_scheme: str | None = DEFAULT_TMAP_SCHEME,
    kakao_place_id: str = "",
) -> list[dict]:
    """Return a list of {key, label, url, precise, role, app?} dicts."""
    has_geo = lat is not None and lng is not None
    search_q = _with_region(name, region)
    # A name + address query is closer to the exact place than the name alone.
    google_q = f"{name} {address}".strip() if address else search_q
    links: list[dict] = []

    # Naver
    if naver_place_id:
        links.append({"key": "naver", "label": "네이버 지도", "precise": True, "role": "map",
                      "url": f"https://map.naver.com/p/entry/place/{_q(str(naver_place_id))}"})
    else:
        links.append({"key": "naver", "label": "네이버 지도(검색)", "precise": False, "role": "map",
                      "url": f"https://map.naver.com/p/search/{_q(search_q)}"})

    # Kakao: the place's own page when its ID is known, else a pin at the coordinates, else a search
    if kakao_place_id:
        links.append({"key": "kakao", "label": "카카오맵", "precise": True, "role": "map",
                      "url": kakao_place_url(kakao_place_id)})
    elif has_geo:
        links.append({"key": "kakao", "label": "카카오맵", "precise": True, "role": "map",
                      "url": f"https://map.kakao.com/link/map/{_q(name)},{lat},{lng}"})
    else:
        links.append({"key": "kakao", "label": "카카오맵(검색)", "precise": False, "role": "map",
                      "url": f"https://map.kakao.com/link/search/{_q(search_q)}"})

    # Google
    g = {"api": "1", "query": google_q}
    if google_place_id:
        g["query_place_id"] = google_place_id
    links.append({"key": "google", "label": "구글 지도" if google_place_id else "구글 지도(검색)",
                  "precise": bool(google_place_id), "role": "map",
                  "url": "https://www.google.com/maps/search/?" + urlencode(g)})

    # Routes (Kakao's from the place ID alone too; the others need coordinates)
    route = kakao_route_url(name, lat, lng, kakao_place_id)
    if route:
        links.append({"key": "kakao_route", "label": "카카오맵 길찾기", "precise": True, "role": "route", "url": route})
    if has_geo:
        d = {"api": "1", "destination": f"{lat},{lng}"}
        if google_place_id:
            d = {"api": "1", "destination": google_q, "destination_place_id": google_place_id}
        links.append({"key": "google_route", "label": "구글 길찾기", "precise": True, "role": "route",
                      "url": "https://www.google.com/maps/dir/?" + urlencode(d)})
        if tmap_scheme:
            links.append({"key": "tmap", "label": "티맵(앱)", "precise": True, "role": "route", "app": True,
                          "url": tmap_scheme.format(name=_q(name), lat=lat, lng=lng)})
    return links


def search_link(name: str, region: str = "") -> str:
    """Single fallback link for things we do not have a page for (e.g. a nearby restaurant)."""
    return f"https://map.naver.com/p/search/{_q(_with_region(name, region))}"


def precision_summary(links: list[dict]) -> str:
    maps = [l for l in links if l["role"] == "map"]
    if not maps:
        return "none"
    n = sum(1 for l in maps if l["precise"])
    return "all" if n == len(maps) else ("some" if n else "none")
