"""The words the pages of the other language versions print, in English (written here; pipeline/en_site.UIText).

English pages print these as they are. Every other version prints its translation of them, stored in
data/<region>/<code>/strings.json as 'chrome.<key>' (tools/en_content.py prepare --lang <code> puts them in the
strings batch with the English as the source, check keeps every {placeholder}, merge writes them). A version whose
strings lack a key is not built (pipeline/en_site.load_all).

Values: a text with {placeholders} (str.format: the template passes the values; place names and links come in as
markup), or a dict of plural forms by CLDR category ('one' / 'other' in English; Japanese and Chinese have only
'other', Russian 'one' / 'few' / 'many': the strings batch asks each language for its own forms).
INTL_SOURCE: a different English source for translators where English's own text speaks of English ('the English
edition', 'English names'); INTL_ONLY: words only the other versions need (map.js has English built in).
"""
from __future__ import annotations

EN: dict[str, str | dict] = {
    # header, crumbs, footer (en/_chrome.html.j2)
    "skip": "Skip to main content",
    "main_menu": "Main menu",
    "language": "Language",
    "menu": "Menu",
    "full_menu": "Full menu",
    "about_sources": "About and sources",
    "you_are_here": "You are here",
    "explore": "Explore",
    "sources": "Sources",
    "foot_tourapi": "Places, hours and photos:",
    "kto_tourapi": "Korea Tourism Organization TourAPI",
    "foot_official": "Official tourism site:",
    "city_tourism": "{city_source}",
    "foot_maps": "Maps: Kakao Map",
    "about": "About",
    "about_site": "About this site",
    "how_made": "How the pages are made",
    "report_error": "Report an error",
    "llms_guide": "Guide for AI (llms.txt)",
    "sitemap": "Sitemap",
    "run_by": "Run by",
    "editor_role": "Editor in charge",
    "home": "Home",
    # navigation and lists
    "nav_attraction": "Things to do",
    "nav_food": "Food",
    "nav_stay": "Stay",
    "guides": "Guides",
    "courses": "Courses",
    "events": "Events",
    "h1_attraction": "Things to Do in {r}",
    "h1_food": "Where to Eat in {r}",
    "h1_stay": "Where to Stay in {r}",
    "title_attraction": "Things to Do in {r}: {n} Attractions with Hours, Fees and Parking",
    "title_food": "Where to Eat in {r}: {n} Restaurants with Dishes, Hours and Parking",
    "title_stay": "Where to Stay in {r}: {n} Stays with Check-in, Parking and Contacts",
    "desc_attraction": {"one": "{n} attractions in {r}: opening hours, closed days, fees and parking, each with its "
                               "source and check date, and directions.",
                        "other": "{n} attractions in {r}: opening hours, closed days, fees and parking, each with its "
                                 "source and check date, and directions."},
    "desc_food": {"one": "{n} restaurants in {r}: signature dishes, hours, closed days and parking, each with its source "
                         "and check date, and directions.",
                  "other": "{n} restaurants in {r}: signature dishes, hours, closed days and parking, each with its "
                           "source and check date, and directions."},
    "desc_stay": {"one": "{n} stays in {r}: check-in and check-out times, parking and phone numbers, each with its "
                         "source and check date, and directions.",
                  "other": "{n} stays in {r}: check-in and check-out times, parking and phone numbers, each with its "
                           "source and check date, and directions."},
    "count_attraction": {"one": "{n} attractions", "other": "{n} attractions"},
    "count_food": {"one": "{n} restaurants", "other": "{n} restaurants"},
    "count_stay": {"one": "{n} stays", "other": "{n} stays"},
    "guide_link": "Guide: {name}",
    "by_area": "By area",
    "rec_call": "Sources differ · call before visiting",
    "photos_is": "Photos: {name}",
    "map_only_n": {"one": "Only the {n} places with coordinates", "other": "Only the {n} places with coordinates"},
    "list_map": "{name} map",
    "show_map": "Show the map",
    # sources and photos
    "source": "Source",
    "source_word": "source",
    "source_is": "Source: {name}",
    "kto": "Korea Tourism Organization",
    "kto_visitkorea": "Korea Tourism Organization (VisitKorea)",
    "kto_page": "Korea Tourism Organization page (in Korean)",
    "provider_kto": "Korea Tourism Organization",
    "provider_city": "{city_provider}",
    "provider_official": "Official website",
    "rechecked_with": "rechecked with {name}",
    "photo_alt": "{name} photo {i}",
    "photo_is": "Photo: {name}",
    "photos_n": {"one": "{n} photo", "other": "{n} photos"},
    "prev_photo": "Previous photo",
    "next_photo": "Next photo",
    # key facts and the facts card
    "not_listed": "Not listed",
    "not_listed_list": "Not listed: {items}",
    "sources_list": "Sources: {items}",
    "more_down": "more ↓",
    "more": "more",
    "kf_differ": "{labels}: sources differ",
    "call_before": "Call before visiting",
    "or_word": "or",
    "in_korean": "In Korean: {name}",
    "in_korean_paren": "{name} (in Korean)",
    "designations": "Designations",
    "parking_seats": "Parking and seating",
    "rooms_n": {"one": "{n} rooms", "other": "{n} rooms"},
    # directions and maps
    "how_to_get": "How to get to {name}",
    "search_tag": "search",
    "other_maps": "Other maps",
    "map_google": "Google Maps",
    "map_naver": "Naver Map",
    "map_kakao": "Kakao Map",
    "route_kakao": "Kakao Map directions",
    "route_google": "Google Maps directions",
    "route_tmap": "TMAP (app)",
    "directions": "Directions",
    "map_loading": "Loading the map.",
    "map_credit": "Map: Kakao Map",
    "map_of": "Map of {name}",
    "map_straight": "Distances are straight lines between coordinates",
    # place page
    "sec_facts": "Facts",
    "sec_photos": "Photos",
    "sec_map": "Map",
    "sec_nearby": "Nearby",
    "sec_details": "Details",
    "sec_faq": "FAQ",
    "sec_sources": "Sources",
    "sec_places": "Places",
    "sec_stops": "Stops",
    "jump_place": "Jump to a section of {name}",
    "h_facts": "{name} before you go",
    "h_photos": "{name} photos",
    "h_more": "{name} more information",
    "h_fit": "{name} facilities and access",
    "h_map": "{name} map",
    "h_near": "{name} nearby and related",
    "h_details": "{name} in detail",
    "h_faq": "{name} FAQ",
    "h_sources": "{name} sources",
    "near_sights": "Things to do nearby",
    "near_biz": "Places to stay and eat nearby",
    "near_note": "Within {m} m · straight-line distance · {provider}",
    "courses_here": "Official courses through this place",
    "guides_here": "Guides that include this place",
    "events_here": "Events held here",
    "original_page": "Original page",
    "visitkorea": "VisitKorea",
    "korean_page": "Korean page",
    "name_in_region": "{name}, {r}",
    "visit_information": "{name}: Visit Information",
    "place_desc_fallback": "{name} in {r}.",
    # guides
    "jump_guide": "Jump to a section of this guide",
    "guide_places_n": {"one": "The {n} places in this guide", "other": "The {n} places in this guide"},
    "full_list": "Full list",
    "n_more": {"one": "{n} more", "other": "{n} more"},
    "see_full_list": "See the full list",
    "places_in_guide": "The places in this guide",
    "prev_place": "Previous place",
    "next_place": "Next place",
    "toc_label": "Contents of this guide",
    "toc_head": "Contents",
    "places_in_section": "Places named in this section",
    "places_again": "Places named in this section that have a card above",
    "guide_map": "Map of the places in this guide",
    "map_numbers": "Numbers: the order of the list below",
    "guides_h1": "{r} travel guides",
    "guides_lede": "Where to eat by dish, where to stay, things to do by area, and trips without a car, with kids or on a "
                   "rainy day. Each guide lists its places with their visit information.",
    "all_guides": "All guides",
    "places_unit": {"one": "places", "other": "places"},
    "label_in_region": "{label} in {r}",
    "guides_title": "{r} Travel Guides by Purpose",
    "guides_desc": {"one": "{n} guides to {r}: where to eat by dish, where to stay, things to do by area, trips without a "
                           "car, with kids or on a rainy day, each with its places and their visit information.",
                    "other": "{n} guides to {r}: where to eat by dish, where to stay, things to do by area, trips "
                             "without a car, with kids or on a rainy day, each with its places and their visit "
                             "information."},
    # courses
    "jump_course": "Jump to a section of this course",
    "official_course_of": "Official course of {name}",
    "straight_total": "Straight-line total",
    "legs_coords": "Legs with coordinates",
    "start_end": "Start → end",
    "directions_to_stop": "Directions to stop {n}",
    "stops_in_order": {"one": "{n} stops in order", "other": "{n} stops in order"},
    "next_stop": "next stop {d}",
    "visit_info_for": "Visit information for {name}",
    "course_map": "Course map",
    "map_of_stops": "Map of the stops of {name}",
    "course_map_caption": {"one": "{a} of {b} stops have coordinates · joined in order by straight lines",
                           "other": "{a} of {b} stops have coordinates · joined in order by straight lines"},
    "course_source": "Course source",
    "distances": "Distances",
    "legs_measured": {"one": "{a} of {b} legs measured as straight lines between Korea Tourism Organization TourAPI "
                             "coordinates",
                      "other": "{a} of {b} legs measured as straight lines between Korea Tourism Organization TourAPI "
                               "coordinates"},
    "courses_h1": "{r} travel courses",
    "courses_lede": "The official courses of {city_source}, stop by stop, with each stop's visit information.",
    "stops_of": "Stops of {name} in order",
    "plus_more": "+ {n} more",
    "n_stops": {"one": "{n} stops", "other": "{n} stops"},
    "straight_line": "straight-line {d}",
    "region_name": "{r} {name}",
    "n_stops_title": {"one": "{n} Stops", "other": "{n} Stops"},
    "course_desc_fallback": {"one": "{name}: {n} stops.", "other": "{name}: {n} stops."},
    "courses_title": "{r} Travel Courses: Day Trips and Overnight Trips",
    "courses_desc": {"one": "The {n} official travel courses of {provider}, stop by stop, with the visit information "
                            "of each stop.",
                     "other": "The {n} official travel courses of {provider}, stop by stop, with the visit "
                              "information of each stop."},
    "lede_longest": "the longest leg is from {a} to {b}, {d} in a straight line",
    "lede_near": {"one": "The first {n} stops are within 1 km of the start in a straight line",
                  "other": "The first {n} stops are within 1 km of the start in a straight line"},
    "lede_both": "{near}, and {longest}.",
    "lede_one": "{text}.",
    "lede_ends": {"one": "The {n} stops start at {a} and end at {b}.", "other": "The {n} stops start at {a} and end at {b}."},
    # events
    "ev_dates": "Dates",
    "ev_time": "Time",
    "ev_fee": "Fee",
    "ev_venue": "Venue",
    "ev_address": "Address",
    "ev_organizer": "Organizer",
    "ev_contact": "Contact",
    "website": "Website",
    "program": "Program",
    "usually": "Usually:",
    "other_editions": "Other editions:",
    "places_label": "Places:",
    "sources_label": "Sources:",
    "events_h1": "{r} festivals and events",
    "events_lede": "The dates, venue and fee of each festival's newest edition, its program and where the information "
                   "comes from. Where two sources give different values, both are shown.",
    "upcoming": "Upcoming and ongoing",
    "past": "Past",
    "festivals": "Festivals and events",
    "past_editions": "Past editions",
    "past_note": "The newest edition of each series, newest first.",
    "events_title": "{r} Festivals and Events: Dates, Venues and Fees",
    "events_desc": "{a} upcoming or ongoing and {b} past festivals and events in {r}: dates, venue, fee and organizer of "
                   "the newest edition, with sources.",
    # about
    "about_title": "About This Site: Sources, Photos and Corrections",
    "about_desc": "What {site} is, where its information comes from, how sources are shown, photo licenses, English names "
                  "and how to report an error.",
    "about_lede": "{site} is the English edition of {ko_site}, a travel information site about {r}: when places open, "
                  "what they cost, where to park and how to get there, for attractions, restaurants and places to stay, "
                  "with the official courses and festival dates.",
    "about_what": "What is here",
    "about_counts": "English pages for {places} places ({indexed} of them in search results; the others are listed but "
                    "not indexed until they meet the site's index rule), {guides} guides, {courses} official courses "
                    "and {series} festival and event series.",
    "about_sync": "Each English page is a translation of its Korean page. When the Korean page changes, its English page "
                  "is taken down until the translation is updated, so the two never say different things.",
    "about_how_1": "Opening hours, closed days, fees, parking, phone numbers, check-in times and menus come from the "
                   "Korea Tourism Organization's TourAPI and from {city_source}, and for some places "
                   "from their own official websites. Nothing is filled in from general knowledge.",
    "about_how_2": "Every value names its source. Where two sources give different values, the page shows both, each "
                   "with its source, and says \"{note}\". A value no source gives is listed once as \"{missing}\".",
    "about_how_3": "Texts from {city_source} are not copied; each place page links to its original "
                   "page. Distances are straight lines between coordinates, not travel distances.",
    "about_photos": "Photos are from the Korea Tourism Organization under the Korea Open Government License (KOGL): {n1} "
                    "under {lic1} and {n3} under {lic3}. Type 3 photos are shown exactly as published: never cropped, "
                    "enlarged or edited. Each photo carries its source and license.",
    # owner 2026-10-13 night: no label on the illustrations; this one sentence says what they are
    "about_art": "The illustrations on this site were drawn with generative AI; every photo of a place is an official "
                 "Korea Tourism Organization photo, shown with its source.",
    "about_names_h": "Names",
    "about_names": "English names follow the Korean government's guideline for public terms: the proper part in Revised "
                   "Romanization and the generic part in English (for example, Eunpa Lake Park). Business names are "
                   "romanized. Every place page also shows the Korean name, which helps when you search a Korean map or "
                   "show it to a taxi driver.",
    "the_operator": "the operator",
    "about_report": "If a value is wrong or out of date, write to {mail} with the page address and the source that shows "
                    "the correct value.",
    "about_operator": "Operator: {op}. This site is run independently of {city_admin}.",
    "official_sites": "Official sites",
    # home
    "home_title": "{site}: {r} Attractions, Food, Stays, Courses and Festivals",
    "home_desc": "{a} attractions, {f} restaurants and {s} places to stay in {r}, with opening hours, prices, parking and "
                 "directions, plus official courses and festival dates, in one place.",
    "home_kicker": "{r}, Jeonbuk State, Korea",
    "home_sub": "Opening hours, prices and how to get there for {r}'s attractions, restaurants and places to stay, in "
                "one place.",
    "home_cta": "Start with an official course",
    "cat_attraction": "Attractions",
    "cat_food": "Restaurants",
    "cat_stay": "Places to stay",
    "now_on": "Now on",
    "until": "until {d}",
    "start_here": "Start here",
    "num_attraction": {"one": "attractions", "other": "attractions"},
    "num_food": {"one": "restaurants", "other": "restaurants"},
    "num_stay": {"one": "places to stay", "other": "places to stay"},
    "num_courses": {"one": "official courses", "other": "official courses"},
    "num_guides": {"one": "guides", "other": "guides"},
    "nums_title": "{r} travel, in numbers.",
    "feat_eyebrow": "On the most official courses",
    "feat_h": "Places to start",
    "all_attractions": {"one": "All {n} attractions", "other": "All {n} attractions"},
    "hubs_h": "Eat, stay, see",
    "coming_up": "Coming up",
    "all_events": "All festivals and events",
    "lines_h": "Official courses, in order",
    "all_courses": "All courses",
    "hub_tiny_stay": "Including pensions",
    "hub_tiny_attraction": "Area by area",
    "tile_courses_short": "Official day and overnight courses",
    "tile_courses_tiny": "Day and overnight",
    "tile_courses_pill": "Official",
    "tile_attraction": "Attractions",
    "tile_food": "Restaurants",
    "tile_stay": "Stays",
    "tile_short_attraction": "Hours, closed days, fees and parking",
    "tile_tiny_attraction": "Hours · fees",
    "tile_short_food": "Dishes, hours, closed days and parking",
    "tile_tiny_food": "Dishes · hours",
    "tile_short_stay": "Check-in, check-out, parking and phone",
    "tile_tiny_stay": "Check-in times",
    "tile_events_short": "Upcoming and ongoing festivals",
    "tile_events_tiny": "Upcoming",
    "llms_home": "{r} attractions, restaurants and places to stay with hours, prices, parking and directions; official "
                 "courses and festival dates.",
}

# the English source translators get where English's own words speak of English
INTL_SOURCE: dict[str, str] = {
    "about_desc": "What {site} is, where its information comes from, how sources are shown, photo licenses, how names "
                  "are written and how to report an error.",
    "about_lede": "{site} is the edition in this language of {ko_site}, a travel information site about {r}: when "
                  "places open, what they cost, where to park and how to get there, for attractions, restaurants and "
                  "places to stay, with the official courses and festival dates.",
    "about_counts": "Pages in this language for {places} places ({indexed} of them in search results; the others are "
                    "listed but not indexed until they meet the site's index rule), {guides} guides, {courses} official "
                    "courses and {series} festival and event series.",
    "about_sync": "Each page in this language is a translation of its Korean page. When the Korean page changes, the "
                  "translated page is taken down until the translation is updated, so the two never say different "
                  "things.",
    "about_names": "Place names are the Korea Tourism Organization's official names in this language when it gives one; "
                   "otherwise they are translated from the Korean name (the proper part transcribed, the generic part "
                   "translated). Every place page also shows the Korean name, which helps when you search a Korean map "
                   "or show it to a taxi driver.",
}

# words only the other versions need: map.js writes English and Korean itself, the others come in data-words
INTL_ONLY: dict[str, str] = {
    "map_zoom_in": "Zoom in",
    "map_zoom_out": "Zoom out",
    "map_whole_course": "Whole course",
    "map_fail": "The map could not be loaded.",
    "map_off": "Some stops lie off the map · show them",
}

NOTES: dict[str, str] = {
    "foot_tourapi": "Followed by the link 'Korea Tourism Organization TourAPI'.",
    "foot_official": "Followed by the link with the name of the city's official tourism site.",
    "source_word": "Hidden word read by screen readers before a footnote number.",
    "kf_differ": "{labels} is a list of fact labels (Hours, Fee …).",
    "about_how_2": "{note} is this language's 'sources differ' note, {missing} its 'Not listed'.",
    "plus_more": "After the first stops of a course: how many more there are.",
    "region_name": "A course name with the city's name in front when the name lacks it.",
    "lede_both": "{near} and {longest} are two clauses this file gives (lede_near, lede_longest).",
    "lede_one": "{text} is one sentence without its final punctuation.",
    "name_in_region": "A place name followed by the city's name, for a page title.",
}


def flat(table: dict) -> dict[str, str]:
    """{'key': text, 'plural_key.one': text, …}"""
    out: dict[str, str] = {}
    for k, v in table.items():
        if isinstance(v, dict):
            for form, text in v.items():
                out[f"{k}.{form}"] = text
        else:
            out[k] = v
    return out


def keys_for(loc) -> list[str]:
    """The keys a version's strings must have (plural keys once per form of its language)."""
    if loc.code == "en":
        return list(flat(EN))
    out: list[str] = []
    for k, v in {**EN, **INTL_ONLY}.items():
        out += [f"{k}.{form}" for form in loc.plural] if isinstance(v, dict) else [k]
    return out


def source_for(key: str) -> str:
    """The English a translator works from for one key ('k.few' -> the English 'other' form)."""
    base, _, form = key.partition(".")
    if base in INTL_SOURCE:
        return INTL_SOURCE[base]
    v = EN.get(base, INTL_ONLY.get(base, ""))
    if isinstance(v, dict):
        return v.get(form) or v.get("other") or ""
    return v
