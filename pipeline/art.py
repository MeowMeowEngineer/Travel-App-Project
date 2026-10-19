"""AI art — illustrations made with ChatGPT (owner decisions 2026-10-13, CLAUDE.md 4).

AI-made landscapes and illustrations may be used as backgrounds, campaign art and decoration, never as real photos:
  - only through templates/_art.html.j2 figure(): a <figure data-art> whose <img> alt starts with the illustration
    prefix of the page's language ('일러스트: ', 'Illustration: ', 'イラスト：' … — ALT_PREFIX, the other languages'
    words in pipeline/locales.py art_alt), with its width and height;
  - with no label on the picture: the owner dropped the 'AI 생성 이미지' caption on 2026-10-13 night ('AI 생성 이미지
    표시는 다 빼'). The about pages say once that the illustrations are drawn with generative AI, and that label, in
    any page language (DROPPED_LABELS), may not appear on any page — so it cannot come back unnoticed;
  - never on a place page or inside a place card (a link to a place page) — place photos stay the provider's
    (CLAUDE.md 3.4) — and never in structured data: not in an ImageObject, not in any node but the page itself
    (WebPage …; an Event, a TouristTrip, a place), nothing in a place page's JSON-LD or og:image.
validate.py enforces this on every built page with page_problems(), and checks art.json with data_problems().

data/<region>/art.json is the one file that says which picture is used where:
  {"images": {ID: {"file": "<ID>.png", "alt": "일러스트: …", "alt_en": "Illustration: …", "alt_ja": "イラスト：…",
                   "slot": "home.hero.autumn", "status": "연결" | "개편 뒤 연결",
                   "langs": ["ko"] (pages it may appear on; default ["ko", "en"]), "text": [lines printed in it]}},
   "held":   {ID: "why it is not used yet (to be redrawn)"}}
The alt of a language is "alt" for Korean and "alt_<tag>" for the others (alt_en, alt_ja, alt_zh_hans, alt_zh_hant,
alt_de, alt_fr, alt_es, alt_ru — the locale's record suffix, pipeline/locales.py); a picture appears on a language's
pages only when that language is in its langs (for_lang) and data_problems() requires that language's alt. A picture
with printed words (campaign cards, link previews) carries them in "text", in one language only, and its alt repeats
them verbatim. A slot shows a picture only when the picture's status is '연결' and its renditions are on disk (slots());
otherwise the slot renders exactly as it does without art. The originals stay in incoming/ai-images/ (git-ignored).
tools/art_media.py writes the renditions templates/assets/art/<ID>-<width>.avif|webp (link previews: <ID>-1200.jpg)
and manifest.json {ID: {"w", "h", "avif": [[name, width, bytes], …], "webp": […] | "jpg": […]}}. The build
publishes to /assets/art/ only the files a built page refers to (copy_used), so a picture whose slot does not exist
yet ('개편 뒤 연결') adds nothing.

The slots (known_slot(); data/gunsan/art.json _notes, docs/handover/image_prompts_round2_2026-10-13.md):
home.card.*, list.head.*, guide.banner.<guide id>, en.guide.banner.<guide id>, og.*, page.404, search.empty,
theme.head.<theme slug>, videos.head.<topic> (build.VIDEO_TOPIC_ART), course.banner.<course id>, area.<권역>
(present.REGION_ART), events.month.<MM>, events.kind.<kind> (event_kind), abroad.group.<group>, about.head.
A '연결' picture whose slot is none of these is an error (data_problems); so is one whose guide, course or theme id
the region's data does not have (ID_SLOTS: a typo). One with an id the data has that no page of a build shows (that
page is not in this build: a draft, a guide whose English translation waits for an update, a theme without places)
is a warning (unshown()). home.hero.<season> is not a slot any more (owner 2026-10-13 night: the Korean home opens on
an official photo): its four pictures stay in art.json with the status for a slot the site does not have,
'개편 뒤 연결', and a note — their renditions stay on disk and no build publishes them.
"""
from __future__ import annotations

import functools
import json
import re
import shutil
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

from . import locales as LC

ROOT = Path(__file__).resolve().parent.parent
ART_DIR = ROOT / "templates" / "assets" / "art"
URL_PREFIX = "/assets/art/"
# the alt text's first words, per page language: Korean here, the others in pipeline/locales.py
ALT_PREFIX = {"ko": "일러스트: ", **{code: loc.art_alt for code, loc in LC.LOCALES.items()}}
LANGS = tuple(ALT_PREFIX)         # ko, en, ja, zh-hans, zh-hant, de, fr, es, ru
# the label every illustration carried until the owner dropped it (2026-10-13 night, 'AI 생성 이미지 표시는 다 빼'), in
# each page language: none of them may appear on a page any more (page_problems), with any spacing or letter case
DROPPED_LABELS = ("AI 생성 이미지", "AI-generated image", "AI生成画像", "AI生成图像", "AI生成圖像", "KI-generiertes Bild",
                  "Image générée par IA", "Imagen generada por IA", "Изображение создано ИИ")


def _label_pattern(labels: tuple[str, ...]) -> re.Pattern:
    """One pattern for the labels: their words in order, joined by any spaces or hyphens (also none), any case."""
    alts = []
    for label in labels:
        words = re.split(r"[\s\-]+", re.sub(r"(?<=[A-Za-z])(?=[^\x00-\x7f])", " ", label))
        alts.append(r"[\s\-]*".join(re.escape(w) for w in words if w))
    return re.compile("|".join(alts), re.I)


DROPPED_LABEL_RE = _label_pattern(DROPPED_LABELS)
DEFAULT_LANGS = ("ko", "en")      # a picture without "langs" (no printed words): the Korean and English pages
STATUSES = ("연결", "개편 뒤 연결")
SLOT_RE = re.compile(r"^[a-z0-9]+(?:\.[a-z0-9-]+)+$")
FILE_RE = re.compile(re.escape(URL_PREFIX) + r"([A-Za-z0-9._-]+)")
PLACE_LINK = re.compile(r"^/(?:[a-z]{2}(?:-[a-z]+)?/)?places/[^/?#]+")   # /places/<slug>/, /en/places/<slug>/
OG_IMAGE = {"og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src"}
# JSON-LD nodes that may name a picture of the page itself (the link preview of a page without a photo); AI art in
# any other node (an ImageObject, a place, an Event, a TouristTrip, an Article …) is reported
PAGE_NODES = frozenset({"WebPage", "CollectionPage", "AboutPage", "SearchResultsPage", "WebSite"})

# K events.kind.<kind> (docs/handover/image_prompts_round2_2026-10-13.md K): the picture of an event card without a
# photo. events.json has no kind field, so the kind is the first row whose words appear in the event's series name
# (else its name); none: 'other'. The 2026-10-13 data (75 records, 44 series) falls into these rows the same way
# whether series or name is read.
EVENT_KINDS = (
    ("race", ("대회",)),
    ("ceremony", ("기념식", "추모제", "기념행사", "제전")),
    ("book", ("북페어", "책책북북")),
    ("sea", ("섬", "선유도", "어청도", "노을", "비치", "해맞이", "해넘이", "방류", "갑토리의 날")),
    ("night", ("야행", "야시장", "나이트", "밤", "미디어아트")),
    ("food", ("짬뽕", "맥주")),
    ("flowers", ("보리", "벚꽃", "연꽃")),
    ("nature", ("걷기", "등산", "철새")),
    ("alley", ("골목", "시간여행", "우체통", "손편지")),
    ("stage", ("탱고", "마이크", "예술제", "영화제", "쉬엄쉬엄")),
    ("market", ("장터", "마켓", "캠핑쇼", "로컬페스타")),
)
EVENT_KIND_OTHER = "other"


def event_kind(ev: dict) -> str:
    """'race' … 'market', else 'other': the first EVENT_KINDS row with a word in the series name (else the name)."""
    name = " ".join(str(ev.get("series") or ev.get("name") or "").split())
    return next((kind for kind, words in EVENT_KINDS if any(w in name for w in words)), EVENT_KIND_OTHER)


def alt_key(lang: str) -> str:
    """The art.json field of a language's alt text: 'alt' (Korean), 'alt_en', 'alt_ja', 'alt_zh_hans' …"""
    return "alt" if lang == "ko" else f"alt_{LC.get(lang).tag}"


def langs_of(meta: dict) -> list[str]:
    return list(meta.get("langs") or DEFAULT_LANGS)


def load(data_dir: Path) -> dict:
    """art.json as {"images": {...}, "held": {...}}; a region without the file has no art."""
    try:
        raw = json.loads((Path(data_dir) / "art.json").read_text("utf-8"))
    except FileNotFoundError:
        raw = {}
    return {"images": raw.get("images") or {}, "held": raw.get("held") or {}}


def load_manifest(art_dir: Path | None = None) -> dict:
    try:
        return json.loads((Path(art_dir or ART_DIR) / "manifest.json").read_text("utf-8"))
    except FileNotFoundError:
        return {}


def _srcset(files: list) -> str:
    return ", ".join(f"{URL_PREFIX}{name} {width}w" for name, width, _ in files)


def picture(art_id: str, meta: dict, manifest: dict, art_dir: Path | None = None) -> dict | None:
    """One picture as templates/_art.html.j2 needs it, or None when a rendition is missing (the slot then renders as
    it does without art). alts: the alt text per language (figure() picks the page's)."""
    m = manifest.get(art_id) or {}
    alts = {lang: str(meta[alt_key(lang)]) for lang in LANGS if meta.get(alt_key(lang))}
    base = {"id": art_id, "slot": meta.get("slot", ""), "w": m.get("w"), "h": m.get("h"), "alt": meta.get("alt", ""),
            "alt_en": meta.get("alt_en", ""), "langs": langs_of(meta), "alts": alts}
    if m.get("jpg"):                                                  # a link preview: one JPEG (og:image)
        name = m["jpg"][0][0]
        if not (Path(art_dir or ART_DIR) / name).is_file():
            return None
        return {**base, "src": URL_PREFIX + name, "avif": "", "webp": ""}
    avif = sorted(m.get("avif") or [], key=lambda f: f[1])
    webp = sorted(m.get("webp") or [], key=lambda f: f[1])
    if not (avif and webp and m.get("w") and m.get("h")):
        return None
    if not all((Path(art_dir or ART_DIR) / name).is_file() for name, _, _ in avif + webp):
        return None
    fallback = [f for f in webp if f[1] <= 1280][-1:] or webp[:1]      # the <img src> for browsers without srcset
    return {**base, "src": URL_PREFIX + fallback[0][0], "avif": _srcset(avif), "webp": _srcset(webp)}


def slots(data_dir: Path, art_dir: Path | None = None) -> dict:
    """{slot: picture} for every picture whose status is '연결' and whose renditions are on disk. A slot missing here
    renders exactly as it does without art (the hero's colour field, the card's type icon, no band)."""
    data, manifest = load(data_dir), load_manifest(art_dir)
    found = {}
    for art_id, meta in data["images"].items():
        if meta.get("status") != "연결" or not meta.get("slot"):
            continue
        pic = picture(art_id, meta, manifest, art_dir)
        if pic:
            found[meta["slot"]] = pic
    return found


def for_lang(found: dict, lang: str) -> dict:
    """The pictures a page in `lang` may show: those whose langs name it (a picture with Korean words never reaches an
    English page, an English campaign card never a Japanese one)."""
    return {slot: pic for slot, pic in (found or {}).items() if lang in (pic.get("langs") or DEFAULT_LANGS)}


PLACE_PAGE = re.compile(r"^/(?:[a-z]{2}(?:-[a-z]+)?/)?places/[^/]+/$")
OG_SLOTS = {"/abroad/": "og.abroad"}


def og_fallback(found: dict, path: str, lang: str = "ko") -> dict | None:
    """The link-preview illustration (og:image) of a page that has no photo of its own, or None. Never on a place
    page: a place's preview stays its provider photo, or none (CLAUDE.md 3.4·4). Korean pages: og.default (/abroad/
    has og.abroad); English: og.default-en; the other versions: og.<code> (og.ja …) — each picture carries its own
    language's words, so it is never shown on another language's pages."""
    if PLACE_PAGE.match(path) or path == "/404.html":
        return None
    if lang == "ko":
        pic = found.get(OG_SLOTS.get(path, "")) or found.get("og.default")
    else:
        pic = found.get("og.default-en" if lang == "en" else f"og.{lang}")
    return pic if pic and lang in (pic.get("langs") or [lang]) else None


def slot_lang(slot: str) -> str | None:
    """The one language a slot belongs to: en.guide.banner.* → 'en', og.ja → 'ja', og.default → 'ko' …; None for a
    slot every language may use (a picture without words)."""
    head, _, rest = slot.partition(".")
    if head in LC.LOCALES:
        return head
    if head == "og":
        return {"default": "ko", "abroad": "ko", "default-en": "en"}.get(rest) or (rest if rest in LC.LOCALES else None)
    return None


@functools.lru_cache(maxsize=None)
def _slot_rules() -> re.Pattern:
    """Every slot a page can show (the callers of templates/_art.html.j2 and og_fallback). Fixed families list their
    keys; guides, courses and themes take their ids."""
    from . import build as B, present as P   # their tables name the video topics, the 권역 and the /abroad/ groups

    def one(keys) -> str:
        return "(?:" + "|".join(re.escape(k) for k in keys) + ")"
    rules = (   # no home.hero.<season> since 2026-10-13 night: the Korean home opens on an official photo
        r"home\.card\.(?:event|abroad|video|guide|festival-[a-z0-9-]+)",
        r"list\.head\.(?:places|food|stays|courses|guides|events|videos|abroad|map)",
        rf"og\.(?:default|default-en|abroad|{one(c for c in LC.CODES if c != 'en')})",
        r"page\.404", r"search\.empty", r"about\.head",
        r"(?:en\.)?guide\.banner\.[a-z0-9-]+", r"course\.banner\.[a-z0-9-]+", r"theme\.head\.[a-z0-9-]+",
        rf"videos\.head\.{one(B.VIDEO_TOPIC_ART.values())}",
        rf"area\.{one(P.REGION_ART.values())}",
        r"events\.month\.(?:0[1-9]|1[0-2])",
        rf"events\.kind\.{one([k for k, _ in EVENT_KINDS] + [EVENT_KIND_OTHER])}",
        rf"abroad\.group\.{one([k for k, _ in B.ABROAD_SOURCES] + ['videos'])}",
    )
    return re.compile("^(?:" + "|".join(rules) + ")$")


def known_slot(slot: str) -> bool:
    return bool(_slot_rules().match(slot))


# the slot families whose last part is an id of the region's data — known_slot() checks only its form: the file
# (under data/<region>/) that has the ids, the record field that holds one (None: the file is {id: record}), and
# what the id names. en/guides.json: the guides with an English translation (a page in English once it is current).
ID_SLOTS = {"guide.banner": ("guides.json", "id", "가이드 id"),
            "en.guide.banner": ("en/guides.json", None, "영어 가이드 id"),
            "course.banner": ("courses.json", "id", "코스 id"),
            "theme.head": ("themes.json", "slug", "테마 slug")}


def id_slot(slot: str) -> tuple[str, str] | None:
    """('course.banner', 'c-1') for 'course.banner.c-1': a slot of an ID_SLOTS family and its id; else None."""
    family, _, ident = slot.rpartition(".")
    return (family, ident) if family in ID_SLOTS else None


def data_ids(data_dir: Path) -> dict[str, set[str]]:
    """{family: the ids the region's data has} for ID_SLOTS, whatever their status — a page a build leaves out is
    not a typo (unshown())."""
    out = {}
    for family, (name, field, _) in ID_SLOTS.items():
        try:
            raw = json.loads((Path(data_dir) / name).read_text("utf-8"))
        except FileNotFoundError:
            raw = {}
        out[family] = {str(k) for k in raw} if field is None else {str(r[field]) for r in raw if r.get(field)}
    return out


def data_problems(data_dir: Path, art_dir: Path | None = None) -> list[str]:
    """A region's art.json against the renditions on disk: an alt text per language the picture appears in (with
    its printed words verbatim, in one language), one well-formed slot per picture that is a place the site has when
    the picture is '연결' (a guide, course or theme id the region's data has: data_ids), a language slot's pictures
    only in that language, a known status, every listed rendition present with its recorded size, nothing both used
    and held. (The renditions folder is shared by every region; tests/test_art.py keeps it free of files no art.json
    lists.)"""
    data, manifest, ids = load(data_dir), load_manifest(art_dir), data_ids(data_dir)
    problems, seen = [], {}
    for art_id, meta in data["images"].items():
        where = f"art.json {art_id}"
        langs = langs_of(meta)
        if not set(langs) <= set(LANGS):
            problems.append(f"{where}: langs는 {'·'.join(LANGS)} 가운데에서: {langs}")
        lines = meta.get("text") or []
        printed = [" ".join(str(x).split()) for x in ([lines] if isinstance(lines, str) else lines) if str(x).strip()]
        if printed and len(langs) != 1:
            problems.append(f"{where}: 글자가 든 그림은 그 글자의 언어 하나만(langs): {langs}")
        for lang in (x for x in langs if x in LANGS):
            key, prefix = alt_key(lang), ALT_PREFIX[lang]
            text = " ".join(str(meta.get(key) or "").split())
            if not text.startswith(prefix) or len(text) <= len(prefix):
                problems.append(f"{where}: {key}는 '{prefix}'로 시작하는 설명이어야 함")
            elif any(line not in text for line in printed):
                problems.append(f"{where}: {key}에 그림 속 문장이 그대로 없음: {' / '.join(printed)}")
        slot = str(meta.get("slot") or "")
        if not SLOT_RE.match(slot):
            problems.append(f"{where}: slot 형식이 아님: {slot!r}")
        else:
            if slot in seen:
                problems.append(f"{where}: slot {slot}을 {seen[slot]}도 씀")
            if slot_lang(slot) and langs != [slot_lang(slot)]:
                problems.append(f"{where}: slot {slot}은 {slot_lang(slot)} 페이지 전용 — langs는 [\"{slot_lang(slot)}\"]")
            if meta.get("status") == "연결" and not known_slot(slot):
                problems.append(f"{where}: '연결'인데 사이트에 없는 자리: {slot} — slot 이름 확인"
                                "(docs/handover/image_prompts_round2_2026-10-13.md), 자리가 아직 없으면 status '개편 뒤 연결'")
            elif meta.get("status") == "연결" and (fam := id_slot(slot)) and fam[1] not in ids[fam[0]]:
                name, _, what = ID_SLOTS[fam[0]]
                problems.append(f"{where}: '연결'인데 사이트에 없는 자리: {slot} — {name}에 없는 {what}: {fam[1]} "
                                "(오타 확인, 그 가이드·코스·테마가 아직 없으면 status '개편 뒤 연결')")
        seen.setdefault(slot, art_id)
        if meta.get("status") not in STATUSES:
            problems.append(f"{where}: status는 {' 또는 '.join(STATUSES)}")
        if art_id in data["held"]:
            problems.append(f"{where}: held(보류)에도 있음")
        m = manifest.get(art_id)
        if not m:
            problems.append(f"{where}: 파생본 없음 — python tools/art_media.py")
            continue
        for fmt in (("jpg",) if m.get("jpg") else ("avif", "webp")):
            if not m.get(fmt):
                problems.append(f"{where}: {fmt} 파생본 없음")
            for name, _, size in m.get(fmt) or []:
                f = Path(art_dir or ART_DIR) / name
                if not f.is_file() or f.stat().st_size != size:
                    problems.append(f"{where}: 파생본 파일이 없거나 크기가 manifest와 다름: {name}")
    return problems


def files_in(html: str) -> set[str]:
    """Rendition file names one page refers to."""
    return set(FILE_RE.findall(html)) if URL_PREFIX in html else set()


def used_files(out: Path) -> set[str]:
    """Rendition file names the built pages refer to."""
    names: set[str] = set()
    for f in Path(out).rglob("*.html"):
        names |= files_in(f.read_text("utf-8"))
    return names


def unshown(data_dir: Path, used: set[str], art_dir: Path | None = None) -> list[str]:
    """The '연결' pictures of a guide, course or theme (ID_SLOTS) whose id the data has but no page of a build shows
    (`used`: the rendition names its pages refer to): that page is not in this build — a draft, a guide whose English
    translation waits for an update, a theme without places. validate.py warns; an id the data lacks is an error
    (data_problems)."""
    ids, out = data_ids(data_dir), []
    for slot, pic in sorted(slots(data_dir, art_dir).items()):
        fam = id_slot(slot)
        if fam and fam[1] in ids[fam[0]] and pic["src"][len(URL_PREFIX):] not in used:
            out.append(f"art.json {pic['id']}: '연결'인데 이번 빌드의 어느 페이지에도 나오지 않음: {slot} — 그 페이지가 "
                       "이번 빌드에 없음(비공개, 영어 번역 갱신 전, 장소 없는 테마) 또는 langs 확인")
    return out


# the classes css/49-art.css's art-slots block styles (pipeline/build.py ART_SLOT_CSS): a page that shows one of these
# pictures carries one of them
SLOT_CSS_MARKS = ('class="art art-band art-strip"', 'class="art-hd"', " has-art-hero")


def slot_css_needed(out: Path) -> bool:
    """Does a built page show a picture the art-slots CSS lays out (a map 권역 strip, a picture beside a heading, the
    about head's picture)?"""
    for f in Path(out).rglob("*.html"):
        text = f.read_text("utf-8")
        if URL_PREFIX in text and any(mark in text for mark in SLOT_CSS_MARKS):
            return True
    return False


def copy_used(out: Path, art_dir: Path | None = None) -> list[str]:
    """Publish only the renditions a page uses (validate reports a page that refers to a missing one)."""
    art_dir = Path(art_dir or ART_DIR)
    names = sorted(n for n in used_files(out) if (Path(art_dir) / n).is_file())
    for n in names:
        (Path(out) / "assets" / "art").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(art_dir) / n, Path(out) / "assets" / "art" / n)
    return names


def page_lang(html_lang: str) -> str | None:
    """'ko' / a locale code for a page's <html lang> ('zh-Hans' → 'zh-hans'), None when it names no version."""
    if (html_lang or "").lower() == "ko":
        return "ko"
    loc = LC.by_html(html_lang or "")
    return loc.code if loc else None


class _ArtScan(HTMLParser):
    """Where a page uses AI art: <img>/<source> inside figure[data-art] (with its alt and size), og:image metas,
    preload links — and anything else that refers to /assets/art/, which is a problem. The page's language (<html
    lang>) sets the alt prefix every picture on it needs."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.problems: list[str] = []
        self.figures: list[dict | None] = []     # open <figure>s: a dict for figure[data-art], else None
        self.links: list[bool] = []              # open <a>s: does it go to a place page?
        self.og: list[str] = []
        self.count = 0
        self.lang: str | None = None             # the page's language, when <html lang> names one

    def handle_starttag(self, tag, attrs):
        a = {k: v or "" for k, v in attrs}
        if tag == "html":
            self.lang = page_lang(a.get("lang", ""))
        elif tag == "a":
            self.links.append(bool(PLACE_LINK.match(a.get("href", ""))))
        elif tag == "figure":
            fig = None
            if "data-art" in a:
                fig = {"id": a["data-art"] or "?", "imgs": [], "in_place_link": any(self.links)}
                self.count += 1
            self.figures.append(fig)
        keys = [k for k, v in a.items() if URL_PREFIX in v]
        if not keys:
            return
        if tag == "meta" and (a.get("property") in OG_IMAGE or a.get("name") in OG_IMAGE):
            self.og.append(a.get("content", ""))
            return
        if tag == "link" and "preload" in a.get("rel", "").split():
            return
        art_fig = next((f for f in reversed(self.figures) if f is not None), None)
        if tag in ("img", "source") and art_fig is not None and set(keys) <= {"src", "srcset"}:
            if tag == "img":
                art_fig["imgs"].append(a)
            return
        self.problems.append(f"AI 그림이 figure[data-art]의 <img>/<source> 밖에 있음: <{tag} {keys[0]}> "
                             f"{a[keys[0]][:60]}")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in ("a", "figure"):
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "a" and self.links:
            self.links.pop()
        elif tag == "figure" and self.figures:
            fig = self.figures.pop()
            if fig is not None:
                self._close(fig)

    def _close(self, fig: dict) -> None:
        name = fig["id"]
        if fig["in_place_link"]:
            self.problems.append(f"AI 그림({name})이 장소로 가는 링크(장소 카드) 안에 있음")
        if not fig["imgs"]:
            self.problems.append(f"figure[data-art]({name}) 안에 AI 그림 <img>가 없음")
        for img in fig["imgs"]:
            alt = " ".join(img.get("alt", "").split())
            # the page's language; a page without one: the language whose prefix the alt starts with
            lang = self.lang or next((code for code, p in ALT_PREFIX.items() if alt.startswith(p)), "ko")
            prefix = ALT_PREFIX[lang]
            if not alt.startswith(prefix) or len(alt) <= len(prefix):
                self.problems.append(f"AI 그림({name}) alt가 '{prefix}'로 시작하는 설명이 아님({lang} 페이지): "
                                     f"{alt[:30]!r}")
            if not (img.get("width") and img.get("height")):
                self.problems.append(f"AI 그림({name})에 width·height 없음")


def dropped_labels(html: str) -> list[str]:
    """The dropped 'AI 생성 이미지' labels (DROPPED_LABELS, any language) a page still carries — in its text, with
    tags taken out and characters decoded, or in its markup (an alt, a title, a meta)."""
    text = unescape(re.sub(r"<[^>]*>", " ", html))
    return list(dict.fromkeys(m.group(0) for m in (*DROPPED_LABEL_RE.finditer(text),
                                                   *DROPPED_LABEL_RE.finditer(unescape(html)))))


def _jsonld_hits(node, place: bool) -> list[str]:
    hits: list[str] = []

    def walk(value, types: frozenset):
        if isinstance(value, dict):
            t = value.get("@type")
            inner = types | frozenset(t if isinstance(t, list) else [t] if t else [])
            for v in value.values():
                walk(v, inner)
        elif isinstance(value, list):
            for v in value:
                walk(v, types)
        elif isinstance(value, str) and URL_PREFIX in value:
            if "ImageObject" in types:
                hits.append(f"구조화 데이터 ImageObject에 AI 그림: {value}")
            elif place:
                hits.append(f"장소 페이지 구조화 데이터에 AI 그림: {value}")
            elif types - PAGE_NODES:
                hits.append(f"구조화 데이터 {sorted(types - PAGE_NODES)[0]}에 AI 그림: {value}")

    walk(node, frozenset())
    return hits


def page_problems(html: str, nodes: list, place: bool, out: Path | None = None) -> list[str]:
    """AI-art problems of one built page. `nodes` are its JSON-LD nodes, `place` says it is a place page, `out` (the
    build folder) lets a reference to a rendition that was not published be reported. Every page, with art or not,
    must be free of the dropped label (dropped_labels)."""
    problems = [f"AI 그림 표기 '{hit}'가 페이지에 있음 — 그림에 'AI 생성 이미지' 표기는 하지 않는다(운영자 결정 "
                "2026-10-13 밤, CLAUDE.md 4절)" for hit in dropped_labels(html)]
    for node in nodes:
        problems += _jsonld_hits(node, place)
    if URL_PREFIX not in html and "data-art" not in html:     # most pages: no art at all, no parse
        return problems
    scan = _ArtScan()
    scan.feed(html)
    scan.close()
    problems += scan.problems
    if place and scan.count:
        problems.append("장소 페이지에 AI 그림 — 장소 사진 자리에는 한국관광공사 사진만(CLAUDE.md 3.4·4)")
    if place:
        problems += [f"장소 페이지 og:image·twitter:image에 AI 그림: {url}" for url in scan.og]
    if out is not None:
        for name in sorted(set(FILE_RE.findall(html))):
            if not (Path(out) / "assets" / "art" / name).is_file():
                problems.append(f"AI 그림 파일이 빌드에 없음: {URL_PREFIX}{name}")
    return problems
