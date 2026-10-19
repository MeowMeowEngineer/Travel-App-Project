"""schema.org graphs.

Every value here comes from the same data the page renders, so structured data always
matches the visible text (Google: "make sure your structured data matches the visible text";
pipeline.validate.jsonld_visibility enforces it on every page).
Typed properties are emitted only when the source string maps to them exactly:
- isAccessibleForFree only when the fee is exactly "무료" (no conflicting source),
- openingHoursSpecification only for a plain "HH:MM~HH:MM" (or the exact two-season form) with
  "연중무휴" / "매주 X요일" and no conflicting source; otherwise the values stay in additionalProperty,
- amenityFeature / petsAllowed only from Y/N-type source values,
- award only from the official designations the page shows (schema.designations: source link and 확인일 on the page).
Nothing is inferred: no eventStatus, no ratings, no reviews, no priceRange.
"""
from __future__ import annotations

import json
import re

from . import city
from .schema import FACT_LABELS, designations, node_types, schema_type, serves_cuisine
from .textutil import display_address, display_value, extract_phones, phone_intl, squash_ws

PROP_KEYS = ("usetime", "restdate", "usefee", "parking", "spendtime", "menu", "babycarriage", "pet")
# `award` (schema.org Organization / LocalBusiness): the official designations a restaurant or lodging page shows
# (schema.designations) as their visible labels, e.g. '모범음식점(○○시 지정)' — never on a plain Place type
AWARD_TYPES = {"Restaurant", "LodgingBusiness", "Hotel", "Motel"}
_TIME = re.compile(r"^\d{1,2}:\d{2}$")
# Image licence pages (both checked to open on 2026-10-08)
LICENSE_URLS = {"KOGL-1": "https://www.kogl.or.kr/info/licenseType1.do",
                "KOGL-3": "https://www.kogl.or.kr/info/licenseType3.do"}
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
KO_DAYS = "월화수목금토일"
_HOURS = re.compile(r"^(\d{1,2}):(\d{2})\s*~\s*(\d{1,2}):(\d{2})$")
_SEASONS = re.compile(r"^(\d{1,2})~(\d{1,2})월 (\d{1,2}:\d{2})~(\d{1,2}:\d{2}) / (\d{1,2})~(\d{1,2})월 (\d{1,2}:\d{2})~(\d{1,2}:\d{2})$")
_REST = re.compile(r"^(?:연중무휴|매주 ([월화수목금토일])요일)$")
_MONTH_END = {1: 31, 2: 29, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
# Y/N-type source values -> boolean (anything else is not typed)
AMENITY_VALUES = {
    "parking": {"가능": True, "불가": False, "불가능": False},
    "babycarriage": {"가능": True, "있음": True, "없음": False, "불가": False},
    "pet": {"가능": True, "불가": False},
}


def dumps(obj: dict) -> str:
    """JSON for a <script type="application/ld+json"> block (safe against '</script>')."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def org_ref(site_url: str) -> dict:
    return {"@id": f"{site_url}/#publisher"}


def organization(site: dict, site_url: str, record: bool = True, lang: str = "ko") -> dict:
    """Publisher node. url / sameAs only from site.operator values the owner fills — never invented. record: the
    company's official record as the page's footer shows it (validate checks every value against the page): the Korean
    head office on Korean pages, the English one the other versions print (lang != 'ko')."""
    op = site.get("operator") or {}
    node = {"@type": "Organization", "@id": f"{site_url}/#publisher", "name": op.get("name", "")}
    if op.get("name_en"):
        node["alternateName"] = op["name_en"]
    if op.get("logo"):
        node["logo"] = {"@type": "ImageObject", "url": f"{site_url}{op['logo']}"}
    if op.get("url"):
        node["url"] = op["url"]
    same = [u for u in (op.get("sameAs") or op.get("same_as") or []) if u]
    if same:
        node["sameAs"] = same
    # the company's official record (operator 2026-10-17: the CEO's mail asked for it on the site): the registered
    # name, the business registration number, the head office, the main line and the mailbox — the values the footer
    # prints (the founding date is printed as words, so it stays off the node), each
    # only when the owner filled it (site.json operator.sources names the documents)
    if not record:
        return node
    if op.get("legal_name"):
        node["legalName"] = op["legal_name"]
    if op.get("business_no"):
        node["taxID"] = op["business_no"]
    office = op.get("head_office") if lang == "ko" else op.get("head_office_en")
    if office:
        node["address"] = {"@type": "PostalAddress", "streetAddress": office, "addressCountry": "KR",
                           **({"postalCode": op["head_office_postal"]} if op.get("head_office_postal") else {})}
    if op.get("tel"):
        node["telephone"] = "+82-" + op["tel"].lstrip("0")
    if op.get("email"):
        node["email"] = op["email"]
    return node


def author_node(site: dict | None, site_url: str, lang: str = "ko") -> dict:
    """The editor in charge named by the owner (site.json editor) as a Person working for the publisher; the
    publisher itself when no editor is set. The name and role are shown in every page footer (base)."""
    ed = (site or {}).get("editor") or {}
    if not ed.get("name"):
        return org_ref(site_url)
    node = {"@type": "Person", "name": ed["name"], "worksFor": org_ref(site_url)}
    role = ed.get("role_en") if lang == "en" else ed.get("role")
    if role:
        node["jobTitle"] = role
    return node


CITY_ID = "#city"   # the one city node's fragment on the home page (city-neutral: every city site uses it)


def city_ref(site: dict, site_url: str) -> dict:
    """The one city node (defined on the home page) that places point to."""
    return {"@id": f"{site_url}/{CITY_ID}", "@type": "City", "name": site.get("locality", "")}


def place_ref(page_url: str, e: dict) -> dict:
    """Reference to the entity node defined on its own page."""
    return {"@id": f"{page_url}#place", "@type": schema_type(e), "name": e["name"]}


def website(site: dict, site_url: str) -> dict:
    return {"@type": "WebSite", "@id": f"{site_url}/#website", "url": f"{site_url}/",
            "name": site["site_name"], "inLanguage": "ko-KR", "publisher": org_ref(site_url)}


def breadcrumb(items: list[tuple[str, str]]) -> dict:
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": n, "item": u} for i, (n, u) in enumerate(items, 1)]}


def item_list(urls: list[str], page_url: str) -> dict:
    """One ItemList of the visible cards' absolute URLs, in display order."""
    return {"@type": "ItemList", "@id": f"{page_url}#list", "numberOfItems": len(urls), "itemListElement": [
        {"@type": "ListItem", "position": i, "url": u} for i, u in enumerate(urls, 1)]}


def faq_page(faqs: list[dict], page_url: str) -> dict:
    return {"@type": "FAQPage", "@id": f"{page_url}#faq", "mainEntity": [
        {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
        for f in faqs if f.get("q") and f.get("a")]}


def webpage(page_url: str, title: str, site_url: str, about_id: str | None = None,
            date_modified: str | None = None, based_on: list[str] | None = None,
            last_reviewed: str | None = None) -> dict:
    node = {"@type": "WebPage", "@id": page_url, "url": page_url, "name": title, "inLanguage": "ko-KR",
            "isPartOf": {"@id": f"{site_url}/#website"}, "publisher": org_ref(site_url)}
    if about_id:
        node["about"] = {"@id": about_id}
    if date_modified:
        node["dateModified"] = date_modified
    if last_reviewed:
        node["lastReviewed"] = last_reviewed
    based_on = [u for u in (based_on or []) if u]
    if based_on:
        node["isBasedOn"] = based_on if len(based_on) > 1 else based_on[0]
    return node


def alternate_names(e: dict) -> list[str]:
    """Other official names (e.g. the TourAPI title), without the page name and duplicates.
    The place page shows exactly this list under the h1, so alternateName always matches visible text."""
    seen = {"".join(squash_ws(e.get("name")).split())}
    out = []
    for raw in e.get("alternate_names") or []:
        name = squash_ws(raw if isinstance(raw, str) else "")
        key = "".join(name.split())
        if key and key not in seen:
            seen.add(key)
            out.append(name)
    return out


def postal_address(raw: str | None, site: dict) -> dict | None:
    """PostalAddress from the displayed address. Region and locality are split off only when the visible
    string starts with them (a province and its 시, or a 광역시 and its 구·군: pipeline/city.py postal_parts);
    streetAddress is the visible remainder (or the whole string)."""
    addr = display_address(raw)
    if not addr:
        return None
    node = {"@type": "PostalAddress"}
    region, locality, rest = city.current().postal_parts(addr)
    if region:
        node["addressRegion"] = region
    if locality:
        node["addressLocality"] = locality
    node["streetAddress"] = rest or addr
    node["addressCountry"] = "KR"
    return node


def conflicted(e: dict, key: str) -> bool:
    """Another source gives a different value for this fact (relation 'also' adds, it does not contradict)."""
    primary = squash_ws(str((e.get("facts") or {}).get(key) or ""))
    return any(alt.get("relation") != "also" and squash_ws(str(alt.get("value") or ""))
               and squash_ws(str(alt.get("value") or "")) != primary
               for alt in (e.get("fact_alternatives") or {}).get(key) or [])


def _hhmm(h: str, m: str) -> str:
    """'9', '00' -> '09:00'; "" for a value that is not a clock time (e.g. '24:00' in '00:00~24:00', which is
    not a valid schema.org Time — such hours stay in additionalProperty as the source wrote them)."""
    return f"{int(h):02d}:{m}" if int(h) <= 23 and int(m) <= 59 else ""


def _days_open(restdate: str) -> list[str] | None:
    m = _REST.match(squash_ws(restdate))
    if not m:
        return None
    if not m.group(1):
        return list(DAYS)
    return [d for d, k in zip(DAYS, KO_DAYS) if k != m.group(1)]


def opening_hours(usetime: str | None, restdate: str | None) -> list[dict]:
    """openingHoursSpecification from strictly formatted values only; [] for anything else."""
    days = _days_open(restdate or "")
    text = squash_ws(usetime)
    if not days or not text:
        return []
    m = _HOURS.match(text)
    if m:
        opens, closes = _hhmm(m.group(1), m.group(2)), _hhmm(m.group(3), m.group(4))
        if not opens or not closes or closes <= opens:  # past midnight, 24:00 or malformed: not typed
            return []
        return [{"@type": "OpeningHoursSpecification", "dayOfWeek": days, "opens": opens, "closes": closes}]
    m = _SEASONS.match(text)
    if not m:
        return []
    out = []
    for first, last, span in ((m.group(1), m.group(2), (m.group(3), m.group(4))),
                              (m.group(5), m.group(6), (m.group(7), m.group(8)))):
        a, b = int(first), int(last)
        if not (1 <= a <= 12 and 1 <= b <= 12):
            return []
        opens, closes = (_hhmm(*t.split(":")) for t in span)
        if not opens or not closes or closes <= opens:
            return []
        out.append({"@type": "OpeningHoursSpecification", "dayOfWeek": days, "opens": opens, "closes": closes,
                    "validFrom": f"--{a:02d}-01", "validThrough": f"--{b:02d}-{_MONTH_END[b]:02d}"})
    return out


def amenity_value(key: str, value: str | None) -> bool | None:
    """Y/N for a value as the page shows it (display_value: '주차장이 구비' and '주차가능' read '가능')."""
    return AMENITY_VALUES.get(key, {}).get(squash_ws(display_value(key, value)))


def shown_value(key: str, raw) -> str:
    """A stored value exactly as the page prints it (squashed), so markup equals visible text (P0-3)."""
    return squash_ws(display_value(key, raw))


def image_objects(images: list[dict]) -> list[dict]:
    """Licensed photos as ImageObject with the visible credit and the licence page. Google's image metadata report
    also asks for `creator` (the credited provider, the same visible text) and `acquireLicensePage` (where the
    terms of use are: the KOGL type page, as for `license`)."""
    out = []
    for im in images:
        node = {"@type": "ImageObject", "contentUrl": im["url"]}
        credit = squash_ws(im.get("credit"))
        if credit:
            node["creditText"] = credit
            node["copyrightNotice"] = credit
            node["creator"] = {"@type": "Organization", "name": credit}
        if LICENSE_URLS.get(im.get("license")):
            node["license"] = LICENSE_URLS[im["license"]]
            node["acquireLicensePage"] = LICENSE_URLS[im["license"]]
        out.append(node)
    return out


def entity_node(e: dict, site: dict, site_url: str, page_url: str, images: list[dict], same_as: list[str],
                has_map: str = "", parent: dict | None = None, parts=()) -> dict:
    """The place node. parent: the place this one is inside (pipeline/relations.py 'inside'; containedInPlace is then
    [the parent, the city]); parts: the places inside this one (containsPlace). Two pages for one building
    ('same_building') get neither: no part/whole between them."""
    kind = e.get("kind", "attraction")
    facts = e.get("facts") or {}
    node = {"@type": schema_type(e), "@id": f"{page_url}#place", "name": e["name"], "url": page_url}
    alt = alternate_names(e)
    if alt:
        node["alternateName"] = alt if len(alt) > 1 else alt[0]
    if e.get("summary"):
        node["description"] = e["summary"]
    address = postal_address(facts.get("address"), site)
    if address:
        node["address"] = address
    geo = e.get("geo") or {}
    if geo.get("lat") is not None and geo.get("lng") is not None:
        node["geo"] = {"@type": "GeoCoordinates", "latitude": geo["lat"], "longitude": geo["lng"]}
    if has_map:
        node["hasMap"] = has_map
    phones = [phone_intl(p) for p in extract_phones(facts.get("infocenter"))]
    # a second official number (e.g. the city's hygiene-office list) is shown next to the first, so both go here too
    for alt in (e.get("fact_alternatives") or {}).get("infocenter") or []:
        for ph in extract_phones(alt.get("value") if isinstance(alt, dict) else alt):
            if phone_intl(ph) not in phones:
                phones.append(phone_intl(ph))
    if phones:
        node["telephone"] = phones if len(phones) > 1 else phones[0]
    cuisine = serves_cuisine(e)
    if cuisine:
        node["servesCuisine"] = cuisine
    awards = [d["label"] for d in designations(e)]
    if awards and AWARD_TYPES & set(node_types(node)):
        node["award"] = awards if len(awards) > 1 else awards[0]
    if kind == "stay":
        for key, prop in (("checkin", "checkinTime"), ("checkout", "checkoutTime")):
            if _TIME.match(facts.get(key, "")):
                node[prop] = facts[key]
        pets = amenity_value("pet", facts.get("pet"))
        if pets is not None and not conflicted(e, "pet"):
            node["petsAllowed"] = pets
    if squash_ws(facts.get("usefee")) == "무료" and not conflicted(e, "usefee"):
        node["isAccessibleForFree"] = True
    hours = []
    if not (conflicted(e, "usetime") or conflicted(e, "restdate")):
        hours = opening_hours(facts.get("usetime"), facts.get("restdate"))
    if hours:
        node["openingHoursSpecification"] = hours
    typed = {"usetime", "restdate"} if hours else set()
    props = [{"@type": "PropertyValue", "name": FACT_LABELS[k], "value": shown_value(k, facts[k])}
             for k in PROP_KEYS if facts.get(k) and k not in typed]
    if props:
        node["additionalProperty"] = props
    features = []
    for key in ("parking", "babycarriage", "pet"):
        value = amenity_value(key, facts.get(key))
        if value is not None and not conflicted(e, key):
            features.append({"@type": "LocationFeatureSpecification", "name": FACT_LABELS[key], "value": value})
    if features:
        node["amenityFeature"] = features
    if images:
        node["image"] = image_objects(images)
    same_as = list(dict.fromkeys(u for u in same_as if u))
    if same_as:
        node["sameAs"] = same_as
    if site.get("locality"):
        node["containedInPlace"] = city_ref(site, site_url)
    if parent is not None:
        node["containedInPlace"] = [place_ref(parent["_url"], parent)] + (
            [city_ref(site, site_url)] if site.get("locality") else [])
    if parts:
        node["containsPlace"] = [place_ref(c["_url"], c) for c in parts]
    return node


def place_graph(e, site, site_url, page_url, title, crumbs, images, same_as, based_on, faqs,
                date_modified: str = "", last_reviewed: str = "", has_map: str = "", parent: dict | None = None,
                parts=()) -> dict:
    graph = [
        webpage(page_url, title, site_url, f"{page_url}#place", date_modified or None, based_on,
                last_reviewed or None),
        entity_node(e, site, site_url, page_url, images, same_as, has_map, parent, parts),
        breadcrumb(crumbs),
    ]
    if faqs:
        graph.append(faq_page(faqs, page_url))
    return {"@context": "https://schema.org", "@graph": graph}


def guide_graph(g, site_url, page_url, crumbs, about: list[dict], item_urls: list[str],
                date_modified: str = "", site: dict | None = None) -> dict:
    art = {"@type": "Article", "@id": f"{page_url}#article", "headline": g["title"][:110],
           "mainEntityOfPage": page_url, "inLanguage": "ko-KR",
           "author": author_node(site, site_url), "publisher": org_ref(site_url)}
    if g.get("summary"):
        art["description"] = g["summary"]
    if g.get("published_at"):
        art["datePublished"] = g["published_at"]
    if date_modified:
        art["dateModified"] = date_modified
    if about:
        art["about"] = about
    srcs = [s["url"] for s in g.get("sources") or [] if s.get("url")]
    if srcs:
        art["isBasedOn"] = srcs
    graph = [art, breadcrumb(crumbs)]
    if item_urls:
        graph.append(item_list(item_urls, page_url))
    if g.get("faq"):
        graph.append(faq_page(g["faq"], page_url))
    return {"@context": "https://schema.org", "@graph": graph}


def course_graph(c, page_url, crumbs, stops: list[dict], based_on: str = "", description: str | None = None) -> dict:
    """stops: a place_ref() dict for a stop linked to a place page, else {"@type": "Place", "name": …}.
    The name is the course name as shown (display_value: no separator pipe). description: the text the page
    shows as the course lede (build passes the computed lede for a summary_auto course); default the summary."""
    trip = {"@type": "TouristTrip", "@id": f"{page_url}#trip", "name": display_value("course_name", c["name"]),
            "url": page_url}
    text = squash_ws(description if description is not None else c.get("summary"))
    if text:
        trip["description"] = text
    if based_on:
        trip["isBasedOn"] = based_on
    items = [{"@type": "ListItem", "position": i, "item": item} for i, item in enumerate(stops, 1)]
    if items:
        trip["itinerary"] = {"@type": "ItemList", "itemListElement": items}
    return {"@context": "https://schema.org", "@graph": [trip, breadcrumb(crumbs)]}


def event_graph(ev: dict, page_url: str, crumbs, site: dict) -> dict:
    """The newest dated edition of a series, on its own leaf page. Only values shown on the page."""
    node = {"@type": "Event", "@id": f"{page_url}#event", "name": ev["_title"], "url": page_url,
            "startDate": ev["start_date"]}
    if ev.get("end_date"):
        node["endDate"] = ev["end_date"]
    # The place is named only from the data's place name or address; with neither, no location (the event's
    # own title is not a place name).
    loc_name = squash_ws(ev.get("place_name")) or display_address(ev.get("address"))
    if loc_name:
        loc = {"@type": "Place", "name": loc_name}
        address = postal_address(ev.get("address"), site)
        if address:
            loc["address"] = address
        geo = ev.get("geo") or {}
        if geo.get("lat") is not None and geo.get("lng") is not None:
            loc["geo"] = {"@type": "GeoCoordinates", "latitude": geo["lat"], "longitude": geo["lng"]}
        node["location"] = loc
    if squash_ws(ev.get("summary")):
        node["description"] = ev["summary"]
    if squash_ws(ev.get("sponsor")):
        node["organizer"] = {"@type": "Organization", "name": squash_ws(ev["sponsor"])}
    if squash_ws(ev.get("fee")) == "무료":
        node["isAccessibleForFree"] = True
    if ev.get("_homepage"):
        node["sameAs"] = ev["_homepage"]
    return {"@context": "https://schema.org", "@graph": [node, breadcrumb(crumbs)]}


def home_graph(site, site_url, featured: list[dict], site_faq: list[dict]) -> dict:
    """WebSite, publisher and the one city node (City + TouristDestination). The site description is not
    put on the city node: it describes the website, not the city, and is not shown as such."""
    dest = {"@type": ["City", "TouristDestination"], "@id": f"{site_url}/{CITY_ID}", "name": site.get("locality", "")}
    if featured:
        dest["includesAttraction"] = featured
    graph = [website(site, site_url), organization(site, site_url), dest]
    if site_faq:
        graph.append(faq_page(site_faq, f"{site_url}/"))
    return {"@context": "https://schema.org", "@graph": graph}


def simple_page_graph(site_url: str, page_url: str, title: str, crumbs, item_urls: list[str] | None = None) -> dict:
    graph = [webpage(page_url, title, site_url), breadcrumb(crumbs)]
    if item_urls:
        graph.append(item_list(item_urls, page_url))
    return {"@context": "https://schema.org", "@graph": graph}
