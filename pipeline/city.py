"""The city a build is about: every value that differs from one city to the next, read from data/<city>/site.json.

The engine is city-neutral. Names, address prefixes, the official tourism site, the travel regions (권역) and their
rule, distance anchors, the home's story and photo picks, designation lists, guide answer copy, the other language
versions' city names — all of it lives in site.json (top-level region keys and the "city" block) and is read here.
data/sample/site.json carries the test fixture's values (a sample city); data/incheon/site.json the
Incheon site's.

One city is active per process: build.State, validate and the tools call activate(site) with the site.json they
load, and every helper below reads current(). Without an activation the city is neutral (empty names, no 권역,
no anchors), so nothing city-specific is ever assumed.

site.json keys read here
  region          short name ('인천')                    locality      the city as addresses write it ('인천광역시')
  region_admin    province before it ('' for 광역시)     region_full   region_admin + locality, as TourAPI names it
  districts       구·군 of a 광역시 (current names)       districts_former  older names addresses may still carry
  source          {name, url}: the city's official tourism site (the 원문 provider; link only)
  city            the block below (every key optional)
    address_prefixes   strings stripped in front of an address where the page is already in the city (a 구·군
                       name after them stays: it is location information). Default: region_admin + locality.
    address_rewrites   [[regex, replacement]] applied to every shown address (a renamed province)
    official           {name, short, match: [...], domains: [...], press: '…'} the official provider: its name in a
                       source line, its short name beside a contested value, the words that identify it in a provider
                       string and the domains that are its pages
    travel_regions     the 권역 rule (see Regions)
    distance_anchors   place names (or slugs) a place page measures straight-line distances to; each is resolved
                       from the collected data at build time and left out with a warning when it is not there
    designations       {order: [type…], short: {type: label}, short_year: [type…]} the city's own lists in front of
                       the national ones
    attraction_groups  {group label: [extra words]} added to the list filter's generic words
    list_hubs          {kind: [guide id, line]} the hub guide a list page points to
    purposes           [[label, guide id, fallback path, note]] the home's entry points
    hero_picks         [[place slug, n-th KOGL-1 photo]] home hero slides
    home               the home's city content (see home()); h1: the opening's H1 (default '<region> 여행의 모든 것')
    access_sources     {key: name} the nearby parking / bus block's source names
    fee_sources        {key: name} a parking fee version's source name
    intl               {code: {site_name, city, source, provider, admin, address: {prefix: [...], tail}}} the
                       other language versions; a version is built only when its names are here
    chat               {names: {lang: city name}, chips: {lang: [questions]}} the site assistant's words
    geo_bounds         [south, north, west, east]: the box every published point lies in (validate); none: no check
    geo_default_points [[lat, lng, note]]: points an official map shows for a record without coordinates — never a
                       place's location (validate)
    official_web       {host: [Korean page, other versions' page or null, checked date]}: official hosts the data
                       writes as bare text, linked where the text names them (added to the national ones in present)
    course_move        {guides: [guide ids before a course's own transit guides], guides_after: [… after them],
                       island_guide, island_route}: the course page's '차 없이 다니기' block (present.course_move)
    plan               {hubs: [{key, name}], island_regions: [권역 names]}: the AI course planner's start and end
                       points (names only) and the 권역 a '섬·바다' liking reads as islands; none: no hub choice
    resident_label     the residents' price group of the fee tables ('○○시민'); default: region + '시민'
    guide_pics         {guide id: [3D picture id, glyph, px]}: the small picture at the head of a guide (the mascot
                       with a suitcase on the getting-here guide …; templates/guide.html.j2); none: no picture
    search_aliases     {'a short name': ['the name the data writes', …]}: the site search reads the short name as those
                       names too ('인천공항' → 인천국제공항; present.search_form_data)
    event_kind_words   {kind: [words]}: words that pick an event card's picture (pipeline/art.py event_kind); a kind
                       the engine does not have becomes the city's own (its pictures events.kind.<kind>)
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

NONE_LABEL_DEFAULT = "권역 미정"
FAR_LABEL_DEFAULT = "먼 섬"


def _words_rx(text: str) -> str:
    """'○○도 ○○시' -> r'○○도\\s*○○시' (any spacing between the words)."""
    return r"\s*".join(re.escape(w) for w in str(text).split())


def _host(url: str) -> str:
    try:
        h = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


@dataclass
class Region:
    """One travel region: its name, the AI art key of its band (area.<art>) and how places fall in it — an anchor
    place (method nearest_anchor) or address matches (method district: [{district, dongs, except_dongs}])."""
    name: str
    art: str = ""
    anchor: str = ""
    match: list = field(default_factory=list)


@dataclass
class City:
    site: dict = field(default_factory=dict)
    region: str = ""
    locality: str = ""
    region_admin: str = ""
    region_full: str = ""
    districts: tuple = ()
    districts_former: tuple = ()
    cfg: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_site(cls, site: dict | None) -> "City":
        site = site or {}
        cfg = site.get("city") or {}
        locality = str(site.get("locality") or "").strip()
        admin = str(site.get("region_admin") or "").strip()
        return cls(site=site, region=str(site.get("region") or "").strip(), locality=locality, region_admin=admin,
                   region_full=str(site.get("region_full") or f"{admin} {locality}").strip(),
                   districts=tuple(site.get("districts") or ()),
                   districts_former=tuple(site.get("districts_former") or ()), cfg=cfg)

    def __post_init__(self):
        prefixes = self.cfg.get("address_prefixes")
        if prefixes is None:
            prefixes = [p for p in (f"{self.region_admin} {self.locality}".strip(), self.locality) if p]
        prefixes = sorted({p for p in prefixes if p}, key=len, reverse=True)
        self._prefix = (re.compile(r"^(?:" + "|".join(_words_rx(p) for p in prefixes) + r")(?:\s+|$)")
                        if prefixes else None)
        self._rewrites = [(re.compile(rx), rep) for rx, rep in self.cfg.get("address_rewrites") or []]
        self.regions_cfg = self.cfg.get("travel_regions") or {}
        self.regions = [Region(name=r["name"], art=r.get("art", ""), anchor=r.get("anchor", ""),
                               match=list(r.get("match") or [])) for r in self.regions_cfg.get("regions") or []]

    # ------------------------------------------------------------------ names
    @property
    def names(self) -> tuple:
        """Every way an address or a name writes the city ('인천광역시', '인천'), longest first."""
        return tuple(sorted({x for x in (self.locality, self.region) if x}, key=len, reverse=True))

    @property
    def all_districts(self) -> tuple:
        return tuple(dict.fromkeys((*self.districts, *self.districts_former)))

    def strip_prefix(self, text: str | None) -> str:
        """The address without the city in front ('인천광역시 중구 …' -> '중구 …'); the 구·군 stays."""
        t = re.sub(r"\s+", " ", text or "").strip()
        return self._prefix.sub("", t) if self._prefix else t

    def display_address(self, text: str) -> str:
        for rx, rep in self._rewrites:
            text = rx.sub(rep, text, count=1)
        return text

    def without_city(self, name: str | None) -> str:
        """A name without the city in front ('인천 차이나타운' -> '차이나타운'): twins and name matching."""
        n = str(name or "")
        for c in self.names:
            if n.startswith(c):
                return n[len(c):].lstrip()
        return n

    def without_city_words(self, text: str) -> str:
        """Text with the city's names taken out (a word test that must not read the city's own name)."""
        for c in self.names:
            text = text.replace(c, " ")
        return text

    # ------------------------------------------------------------------ the official tourism site
    @property
    def official(self) -> dict:
        o = dict(self.cfg.get("official") or {})
        src = self.site.get("source") or {}
        o.setdefault("name", src.get("name") or "")
        o.setdefault("short", self.locality or o["name"])
        o.setdefault("match", [x for x in (self.locality, o["name"]) if x])
        o.setdefault("domains", [d for d in (_host(src.get("url") or ""),) if d])
        o.setdefault("press", f"{o['short']} 보도자료" if o["short"] else "보도자료")
        return o

    def is_official(self, provider: str | None) -> bool:
        p = str(provider or "")
        return any(m and m in p for m in self.official["match"])

    def official_url(self, url: str | None) -> bool:
        h = _host(str(url or ""))
        return bool(h) and any(h == d or h.endswith("." + d) for d in self.official["domains"])

    def short_provider(self, p: str) -> str:
        if "TourAPI" in p or "한국관광공사" in p:
            return "한국관광공사"
        if self.is_official(p):
            return self.official["short"]
        return p

    # ------------------------------------------------------------------ addresses
    def district_of(self, address: str | None, fallback: str = "") -> str:
        """The 구·군 an address names right after the city ('인천광역시 중구 신포동 …' -> '중구'); else fallback (the
        district TourAPI's statutory code gave, data field `district`); '' for a city without districts."""
        if not self.all_districts:
            return ""
        rest = self.strip_prefix(address)
        first = rest.split(" ", 1)[0] if rest else ""
        if first in self.all_districts:
            return first
        return fallback if fallback in self.all_districts else ""

    def place_where(self, district: str = "", area: str = "") -> str:
        """'인천광역시 중구 신포동' / '○○도 ○○시 ○○동': the city, the 구·군 and the 동 as far as known."""
        return " ".join(x for x in (self.region_admin, self.locality, district, area) if x)

    def place_short(self, district: str = "", area: str = "") -> str:
        """'인천광역시 중구 신포동' / '○○시 ○○동': the city as addresses write it, the 구·군 and the 동 (no province)."""
        return " ".join(x for x in (self.locality, district, area) if x)

    def postal_parts(self, addr: str) -> tuple[str, str, str]:
        """(addressRegion, addressLocality, rest) of a shown address, each split off only when the address starts
        with it: a 시 under a province ('○○도', '○○시', …) or a 구·군 under a 광역시 ('인천광역시', '중구', …)."""
        rest = addr
        region = locality = ""
        if self.districts or self.districts_former:
            top = self.locality
            if top and rest.startswith(top):
                region, rest = top, rest[len(top):].lstrip()
                first = rest.split(" ", 1)[0] if rest else ""
                if first in self.all_districts:
                    locality, rest = first, rest[len(first):].lstrip()
            return region, locality, rest
        if self.region_admin and rest.startswith(self.region_admin):
            region, rest = self.region_admin, rest[len(self.region_admin):].lstrip()
        if self.locality and rest.startswith(self.locality):
            locality, rest = self.locality, rest[len(self.locality):].lstrip()
        return region, locality, rest

    def taut_rx(self, name: str) -> str:
        """CLAUDE.md 3.5's stock first sentence '○○은 <city> ○○에 있는 ○○입니다.' alone, for this city."""
        words = [_words_rx(f"{self.region_admin} {self.locality}".strip())] if self.region_admin else []
        words += [_words_rx(c) for c in self.names] + [re.escape(d) for d in self.all_districts]
        city = "(?:" + "|".join(words) + ")" if words else r"\S+(?:시|군|구)"
        return rf"^{re.escape(name)}\s*(은|는)\s*{city}[^.]*?(있는|위치한)[^.]*?입니다\.$"

    # ------------------------------------------------------------------ travel regions (권역)
    @property
    def region_method(self) -> str:
        return self.regions_cfg.get("method") or ("nearest_anchor" if any(r.anchor for r in self.regions) else "none")

    @property
    def far_m(self) -> int:
        return int(self.regions_cfg.get("far_m") or 0)

    @property
    def far_label(self) -> str:
        return self.regions_cfg.get("far_label") or FAR_LABEL_DEFAULT

    @property
    def none_label(self) -> str:
        return self.regions_cfg.get("none_label") or NONE_LABEL_DEFAULT

    @property
    def region_art(self) -> dict:
        """{권역 name: art key} for the map page's AI art bands (area.<key>)."""
        out = {r.name: r.art for r in self.regions if r.art}
        if self.regions_cfg.get("far_art") and self.region_method == "nearest_anchor":
            out[self.far_label] = self.regions_cfg["far_art"]
        return out

    def district_region(self, district: str, dong: str) -> str | None:
        """The 권역 of an address by the district rule: the first region with a match for its 구·군 whose 법정동
        list (if any) has the 동 and whose except list does not. None when no region matches."""
        if not district:
            return None
        for r in self.regions:
            for m in r.match:
                if m.get("district") != district:
                    continue
                if m.get("dongs") and dong not in m["dongs"]:
                    continue
                if m.get("except_dongs") and (not dong or dong in m["except_dongs"]):
                    continue
                return r.name
        return None

    def region_rule_lines(self) -> list[str]:
        """The district rule as the map page prints it, made from the same configuration that assigns the places; a
        name only addresses still use (districts_former) reads '옛 <name>'."""
        if self.region_method != "district":
            return []
        lines = []
        for r in self.regions:
            parts = []
            for m in r.match:
                d = m.get("district", "")
                if d in self.districts_former and d not in self.districts:
                    d = f"옛 {d}"
                if m.get("dongs"):
                    parts.append(f"{d} 중 {'·'.join(m['dongs'])}")
                elif m.get("except_dongs"):
                    from .textutil import josa
                    parts.append(f"{d} 중 {josa('·'.join(m['except_dongs']), '을/를')} 뺀 곳")
                else:
                    parts.append(d)
            lines.append(f"{r.name}: {', '.join(parts)}")
        return lines

    @property
    def region_rule_note(self) -> str:
        return str(self.regions_cfg.get("rule_note") or "")

    # ------------------------------------------------------------------ the rest of the block
    def get(self, key: str, default=None):
        v = self.cfg.get(key)
        return default if v is None else v

    def home(self, key: str, default=None):
        v = (self.cfg.get("home") or {}).get(key)
        return default if v is None else v

    @property
    def distance_anchors(self) -> list[str]:
        return [str(x) for x in self.cfg.get("distance_anchors") or [] if str(x).strip()]

    def intl(self, code: str) -> dict:
        return (self.cfg.get("intl") or {}).get(code) or {}

    # ------------------------------------------------------------------ coordinates, fees, the planner
    @property
    def geo_bounds(self) -> tuple | None:
        """(south, north, west, east) every published point lies in, or None (no box configured: no check)."""
        b = self.cfg.get("geo_bounds")
        return tuple(float(x) for x in b) if isinstance(b, (list, tuple)) and len(b) == 4 else None

    @property
    def geo_default_points(self) -> list[tuple[float, float]]:
        """Points an official map falls back to for a record without coordinates (never a place's location)."""
        return [(float(x[0]), float(x[1])) for x in self.cfg.get("geo_default_points") or [] if len(x) >= 2]

    @property
    def resident_label(self) -> str:
        """The residents' price group as the fee tables head it ('○○시민')."""
        return str(self.cfg.get("resident_label") or (f"{self.region}시민" if self.region else "시민"))

    @property
    def plan(self) -> dict:
        """The AI course planner's city values: {hubs: [{key, name}], island_regions: [권역 names]}."""
        p = self.cfg.get("plan") or {}
        hubs = [{"key": str(h.get("key") or ""), "name": str(h.get("name") or "")} for h in p.get("hubs") or []
                if isinstance(h, dict) and h.get("key") and h.get("name")]
        return {"hubs": hubs, "island_regions": [str(x) for x in p.get("island_regions") or [] if str(x).strip()]}

    def island_region(self, name: str | None) -> bool:
        """Whether a 권역 is an island one for a '섬·바다' liking: listed in plan.island_regions, else its name says 섬."""
        n = str(name or "")
        return bool(n) and (n in self.plan["island_regions"] or "섬" in n)


_ACTIVE = City()


def activate(site: dict | None) -> City:
    """Make this site.json's city the one every helper reads; returns it."""
    global _ACTIVE
    _ACTIVE = City.from_site(site)
    return _ACTIVE


def activate_dir(data_dir: Path | str) -> City:
    """activate() with data_dir/site.json (a missing file activates the neutral city)."""
    path = Path(data_dir) / "site.json"
    site = json.loads(path.read_text("utf-8")) if path.exists() else {}
    return activate(site)


def current() -> City:
    return _ACTIVE
