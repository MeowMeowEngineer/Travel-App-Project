"""The language versions besides Korean, as one table (English is one locale of it).

A version exists in a build only when data/<region>/<code> exists (pipeline/en_site.py). Everything that differs
by language and is not a translation of our data lives here: the route and data folder, <html lang> / hreflang,
og:locale, the version's site name and the city's name, the language menu label, dates, distances and decimals,
how money is written (the translation rules and checks of tools/en_content.py), sentence splitting, plural forms,
and the word lists and script checks the translation check (tools/en_content.py) and the page check
(pipeline/validate.py) share: promotional words, disclaimers, weekday and month names, Chinese script both ways
(OpenCC character tables), kana in Japanese prose, Cyrillic in Russian prose, the language of German, French and
Spanish prose (a small stopword test). Russian names: kontsevich() (Kontsevich system, Cyrillic).

The words the pages print (the UI text) are not here: English's are pipeline/intl_text.py, the other versions'
are translations of those in data/<region>/<code>/strings.json ('chrome.<key>', tools/en_content.py).
"""
from __future__ import annotations

import datetime as dt
import functools
import os
import re
from dataclasses import dataclass, field

ORDER = ("en", "ja", "zh-hans", "zh-hant", "de", "fr", "es", "ru")   # the language menu and hreflang order after ko
KO = {"code": "ko", "html": "ko", "label": "한국어", "home": "/"}
HANGUL = re.compile(r"[ᄀ-ᇿㄱ-ㆎ가-힣]")
KANA = re.compile(r"[ぁ-ゖァ-ヺー]")
CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
CYR = re.compile(r"[А-Яа-яЁё]")
LAT = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ]")
NNBSP = "\u202f"   # narrow no-break space: French and Russian thousands


@dataclass(frozen=True)
class Locale:
    code: str            # route (/ja/), data folder (data/<region>/ja), --lang
    tag: str             # record field suffix (name_ja, strings.json {"ja": …})
    html: str            # <html lang>, hreflang, JSON-LD inLanguage
    og: str              # og:locale
    label: str           # the language menu label, in the language itself
    english: str         # the language's English name (translator rules)
    site_name: str       # '' here: the city's (site.json city.intl.<code>.site_name), filled by get()
    city: str            # '' here: the city's name in this language (city.intl.<code>.city), filled by get()
    service: str         # TourAPI multilingual service (official names)
    cjk: bool = False
    dec: str = "."       # decimal mark
    grp: str = ","       # thousands separator
    title_max: int = 70  # <title> length (characters)
    desc_max: int = 160  # meta description length (characters)
    sent_max: int = 40   # a prose sentence: words (characters for CJK)
    plural: tuple = ("one", "other")
    weekdays: tuple = ()          # Monday … Sunday, the names a translation uses
    weekdays_short: tuple = ()    # in a date: (Mo.) (月) (周一)
    months: tuple = ()            # month names in a date (genitive for Russian)
    months_short: tuple = ()
    conflict: str = ""            # where two sources differ (places)
    event_conflict: str = ""      # the same for an event's values
    untranslated: str = ""        # the language menu's note on a link to a list (no translation of this page there)
    money_word: str = ""          # '3,000 <word>'
    promo: tuple = ()             # promotional words (CLAUDE.md 3.5: answer-first plain sentences)
    disclaimers: tuple = ()
    free: str = ""                # regex: the word for 무료
    colon: str = ": "
    list_sep: str = ", "
    sjoin: str = " "              # between sentences
    abbr: tuple = ()              # abbreviations a sentence never ends with
    # AI art (owner decisions 2026-10-13, CLAUDE.md 4; pipeline/art.py): the words an illustration's alt text starts
    # with, in the language ('일러스트: ' for Korean). No label on the picture since 2026-10-13 night.
    art_alt: str = ""
    units: tuple = ("m", "km")             # Locale.dist: metres, kilometres
    same_xy: str = "same coordinates"      # Locale.dist under 10 m (two places on the same stored coordinates)
    home_h1: str = ""                      # '' here: the home opening's H1, what the site is in this language
                                           # (city.intl.<code>.home_h1, filled by get()); else the site name
    extra: dict = field(default_factory=dict)

    @property
    def home(self) -> str:
        return f"/{self.code}/"

    @property
    def name_key(self) -> str:
        return f"name_{self.tag}"

    # ---- numbers, dates, distances
    def num(self, n: float, decimals: int = 0) -> str:
        s = f"{n:,.{decimals}f}"
        return s.translate(str.maketrans({",": "\x00", ".": "\x01"})).replace("\x00", self.grp).replace("\x01", self.dec)

    def money(self, won: int) -> str:
        """'3,000 won' as this language writes it (the spec's formats)."""
        n = self.num(won)
        if self.cjk:
            return f"{n}{self.money_word}"
        return f"{n} {self.money_word}"

    def dist(self, m) -> str:
        """'430 m' (rounded to 10 m), '2.4 km' / '2,4 km' / '2,4 км' (units: the language's), under 10 m the words for
        'same coordinates' (present.dist: '같은 좌표'); '' for unknown."""
        if m is None:
            return ""
        m = float(m)
        if m < 10:
            return self.same_xy
        mu, ku = self.units
        return f"{int(round(m / 10) * 10)} {mu}" if m < 1000 else f"{m / 1000:.1f}".replace(".", self.dec) + f" {ku}"

    def date(self, iso: str | None) -> str:
        """A full date with its weekday ('2026年10月13日（月）', '13. Oktober 2026 (Di.)'); English: 'October 9, 2026'."""
        try:
            d = dt.date.fromisoformat(str(iso or "")[:10])
        except ValueError:
            return re.sub(r"\s+", " ", str(iso or "")).strip()
        if self.code == "en":
            return f"{d.strftime('%B')} {d.day}, {d.year}"
        wd = self.weekdays_short[d.weekday()]
        mo = self.months[d.month - 1]
        return self.extra["date"].format(y=d.year, m=d.month, d=d.day, mo=mo, wd=wd)

    def date_bare(self, iso: str | None) -> str:
        """A date without its weekday (a founding date): date() without the bracketed weekday it ends with."""
        return re.sub(r"\s*[（(][^（()）]*[)）]$", "", self.date(iso))

    def md(self, iso: str | None) -> str:
        """A short month-day ('Oct 9', '10月9日', '9. Okt.')."""
        try:
            d = dt.date.fromisoformat(str(iso or "")[:10])
        except ValueError:
            return re.sub(r"\s+", " ", str(iso or "")).strip()
        if self.code == "en":
            return f"{d.strftime('%b')} {d.day}"
        return self.extra["md"].format(m=d.month, d=d.day, mo=self.months_short[d.month - 1])

    def mon(self, ym: str | None) -> str:
        """A month standing alone ('Oct', '10月', 'Okt.', 'окт.'): an end the source gives only as a month
        ('2026-10'), never turned into that month's last day (QA 2026-10-15 SRC-06)."""
        m = int(str(ym or "")[5:7])
        if self.code == "en":
            return dt.date(2000, m, 1).strftime("%b")
        return self.extra.get("mon_alone", self.months_short)[m - 1]

    # ---- plural forms (CLDR cardinal categories)
    def plural_form(self, n: int) -> str:
        if self.plural == ("other",):
            return "other"
        if self.plural == ("one", "few", "many"):
            if n % 10 == 1 and n % 100 != 11:
                return "one"
            if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
                return "few"
            return "many"
        if self.code == "fr":
            return "one" if n in (0, 1) else "other"
        return "one" if n == 1 else "other"

    # ---- sentences
    def sentences(self, text: str | None) -> list[str]:
        """Sentences of a prose text, each whole; joined with self.sjoin they are the text again."""
        t = re.sub(r"\s+", " ", str(text or "")).strip()
        if not t:
            return []
        if self.cjk:
            parts = re.split(r"(?<=[。！？])(?![」』）】〕”’。！？])\s*", t)
            return [p for p in parts if p]
        rx = re.compile(r"(?<=[.?!…])\s+(?=[\"'«„“¿¡(\[0-9A-ZÀ-ÖØ-ÞА-ЯЁ])")
        abbr = re.compile(rf"\b(?:{'|'.join(map(re.escape, self.abbr))})\.$") if self.abbr else None
        out: list[str] = []
        for part in rx.split(t):
            if out and ((abbr and abbr.search(out[-1]))   # 'Nr. 5', 'ул. Ленина'
                        or (self.code == "de" and re.search(r"(?:^|\s)\d{1,2}\.$", out[-1]))):   # '13. Oktober'
                out[-1] = f"{out[-1]} {part}"
            elif part:
                out.append(part)
        return out


_DE_WD = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
LOCALES: dict[str, Locale] = {
    "en": Locale("en", "en", "en", "en_US", "English", "English", "", "", "EngService2",
                 weekdays=("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
                 conflict="Sources differ — call before visiting",
                 event_conflict="Sources differ — check with the organizer before visiting", money_word="won",
                 untranslated="not translated",
                 abbr=("No", "Dr", "Mt", "St", "Mr", "Ms", "Jr", "vs", "approx", "Ave"),
                 art_alt="Illustration: "),
    "ja": Locale("ja", "ja", "ja", "ja_JP", "日本語", "Japanese", "", "", "JpnService2", cjk=True,
                 title_max=40, desc_max=110, sent_max=80, plural=("other",),
                 weekdays=("月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"),
                 weekdays_short=("月", "火", "水", "木", "金", "土", "日"),
                 months=tuple(f"{i}月" for i in range(1, 13)), months_short=tuple(f"{i}月" for i in range(1, 13)),
                 conflict="情報源によって値が異なります。訪問前に電話でご確認ください",
                 event_conflict="情報源によって値が異なります。訪問前に電話でご確認ください", money_word="ウォン",
                 untranslated="未翻訳",
                 promo=("必見", "絶対", "最高", "人気", "有名", "おすすめ", "オススメ", "お勧め", "お薦め", "話題"),
                 disclaimers=("参考程度", "変更される場合があります", "変更になる場合があります", "責任を負いかねます", "免責"),
                 free="無料", colon="：", list_sep="、", sjoin="",
                 art_alt="イラスト：", same_xy="同じ座標",
                 extra={"date": "{y}年{m}月{d}日（{wd}）", "md": "{m}月{d}日", "lang_word": "言語"}),
    "zh-hans": Locale("zh-hans", "zh_hans", "zh-Hans", "zh_CN", "中文(简体)", "Simplified Chinese", "",
                      "", "ChsService2", cjk=True, title_max=40, desc_max=110, sent_max=70, plural=("other",),
                      weekdays=("周一", "周二", "周三", "周四", "周五", "周六", "周日"),
                      weekdays_short=("周一", "周二", "周三", "周四", "周五", "周六", "周日"),
                      months=tuple(f"{i}月" for i in range(1, 13)), months_short=tuple(f"{i}月" for i in range(1, 13)),
                      conflict="不同来源的信息不一致，请出发前致电确认",
                      event_conflict="不同来源的信息不一致，请出发前致电确认", money_word="韩元",
                      untranslated="未翻译",
                      promo=("必去", "必游", "最好", "最佳", "著名", "热门", "网红", "推荐", "人气"),
                      disclaimers=("仅供参考", "如有变动", "以实际为准", "概不负责", "免责声明"),
                      free="免费", colon="：", list_sep="、", sjoin="",
                      art_alt="插图：", same_xy="相同坐标",
                      extra={"date": "{y}年{m}月{d}日（{wd}）", "md": "{m}月{d}日", "lang_word": "语言"}),
    "zh-hant": Locale("zh-hant", "zh_hant", "zh-Hant", "zh_TW", "中文(繁體)", "Traditional Chinese", "",
                      "", "ChtService2", cjk=True, title_max=40, desc_max=110, sent_max=70, plural=("other",),
                      weekdays=("週一", "週二", "週三", "週四", "週五", "週六", "週日"),
                      weekdays_short=("週一", "週二", "週三", "週四", "週五", "週六", "週日"),
                      months=tuple(f"{i}月" for i in range(1, 13)), months_short=tuple(f"{i}月" for i in range(1, 13)),
                      conflict="不同來源的資訊不一致，請出發前致電確認",
                      event_conflict="不同來源的資訊不一致，請出發前致電確認", money_word="韓元",
                      untranslated="未翻譯",
                      promo=("必去", "必遊", "最好", "最佳", "著名", "熱門", "網紅", "推薦", "人氣"),
                      disclaimers=("僅供參考", "如有變動", "以實際為準", "概不負責", "免責聲明"),
                      free="免費", colon="：", list_sep="、", sjoin="",
                      art_alt="插圖：", same_xy="相同座標",
                      extra={"date": "{y}年{m}月{d}日（{wd}）", "md": "{m}月{d}日", "lang_word": "語言"}),
    "de": Locale("de", "de", "de", "de_DE", "Deutsch", "German", "", "", "GerService2",
                 dec=",", grp=".", weekdays=_DE_WD, weekdays_short=("Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So."),
                 months=("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
                         "November", "Dezember"),
                 months_short=("Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sept.", "Okt.", "Nov.",
                               "Dez."),
                 conflict="Die Quellen nennen unterschiedliche Angaben – bitte vor dem Besuch anrufen.",
                 event_conflict="Die Quellen nennen unterschiedliche Angaben – bitte vor dem Besuch anrufen.",
                 untranslated="nicht übersetzt",
                 money_word="Won", promo=("unbedingt", "Geheimtipp", "berühmt", "beliebt", "beste", "Muss"),
                 disclaimers=("ohne Gewähr", "Änderungen vorbehalten", "keine Haftung", "Haftungsausschluss",
                              "unverbindlich"),
                 free=r"kostenlos|gratis|Eintritt frei|eintrittsfrei|frei(?:er)? Eintritt|gebührenfrei",
                 abbr=("Nr", "z", "B", "ca", "bzw", "Str", "St", "Dr", "usw", "inkl", "evtl", "u", "a", "Tel"),
                 art_alt="Illustration: ", same_xy="gleiche Koordinaten",
                 extra={"date": "{d}. {mo} {y} ({wd})", "md": "{d}. {mo}", "lang_word": "Sprache"}),
    "fr": Locale("fr", "fr", "fr", "fr_FR", "Français", "French", "", "", "FreService2",
                 dec=",", grp=NNBSP,
                 weekdays=("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"),
                 weekdays_short=("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."),
                 months=("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
                         "octobre", "novembre", "décembre"),
                 months_short=("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.",
                               "nov.", "déc."),
                 conflict="Les sources indiquent des valeurs différentes : appelez avant votre visite.",
                 event_conflict="Les sources indiquent des valeurs différentes : appelez avant votre visite.",
                 untranslated="non traduit",
                 money_word="wons", promo=("incontournable", "célèbre", "populaire", "meilleur", "à ne pas manquer"),
                 disclaimers=("sous réserve", "à titre indicatif", "susceptible de changer",
                              "décline toute responsabilité", "avertissement"),
                 free=r"gratuit(?:e|s|es)?|entrée libre", colon=" : ",
                 abbr=("M", "Mme", "St", "Ste", "av", "bd", "env", "n°", "tél", "p. ex"),
                 art_alt="Illustration : ", same_xy="mêmes coordonnées",
                 extra={"date": "{d} {mo} {y} ({wd})", "md": "{d} {mo}", "lang_word": "Langue"}),
    "es": Locale("es", "es", "es", "es_ES", "Español", "Spanish", "", "", "SpnService2",
                 dec=",", grp=".",
                 weekdays=("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
                 weekdays_short=("lun.", "mar.", "mié.", "jue.", "vie.", "sáb.", "dom."),
                 months=("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                         "octubre", "noviembre", "diciembre"),
                 months_short=("ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sept.", "oct.",
                               "nov.", "dic."),
                 conflict="Las fuentes indican datos distintos: llame antes de su visita.",
                 event_conflict="Las fuentes indican datos distintos: llame antes de su visita.",
                 untranslated="sin traducir",
                 money_word="wones", promo=("imprescindible", "famoso", "popular", "mejor", "no te puedes perder"),
                 disclaimers=("sujeto a cambios", "a título informativo", "no nos hacemos responsables",
                              "descargo de responsabilidad"),
                 free=r"gratis|gratuit[oa]s?|entrada libre",
                 abbr=("Sr", "Sra", "Dr", "Dra", "av", "Avda", "núm", "aprox", "tel", "p. ej"),
                 art_alt="Ilustración: ", same_xy="mismas coordenadas",
                 extra={"date": "{d} de {mo} de {y} ({wd})", "md": "{d} {mo}", "lang_word": "Idioma"}),
    "ru": Locale("ru", "ru", "ru", "ru_RU", "Русский", "Russian", "", "", "RusService2",
                 dec=",", grp=NNBSP, plural=("one", "few", "many"),
                 weekdays=("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"),
                 weekdays_short=("пн", "вт", "ср", "чт", "пт", "сб", "вс"),
                 months=("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
                         "октября", "ноября", "декабря"),
                 months_short=("янв.", "февр.", "марта", "апр.", "мая", "июня", "июля", "авг.", "сент.", "окт.",
                               "нояб.", "дек."),
                 conflict="Источники расходятся — позвоните перед визитом.",
                 event_conflict="Источники расходятся — позвоните перед визитом.",
                 untranslated="нет перевода",
                 money_word="вон", promo=("обязательно", "знаменитый", "популярный", "лучший"),
                 disclaimers=("может измениться", "носит справочный характер", "не несём ответственности",
                              "не несем ответственности", "отказ от ответственности"),
                 free=r"бесплатн\w*",
                 abbr=("г", "ул", "д", "т", "е", "др", "им", "ок", "мин", "пр", "просп", "тел", "руб"),
                 art_alt="Иллюстрация: ", units=("м", "км"),
                 same_xy="те же координаты",
                 extra={"date": "{d} {mo} {y} г. ({wd})", "md": "{d} {mo}", "lang_word": "Язык",
                        # a month standing alone is nominative (months_short holds the genitive марта, мая, июня, июля)
                        "mon_alone": ("янв.", "февр.", "март", "апр.", "май", "июнь", "июль", "авг.", "сент.", "окт.",
                                      "нояб.", "дек.")}),
}
CODES = tuple(LOCALES)


def get(code: str) -> Locale:
    """The locale with this city's site name and city name in that language (site.json city.intl.<code>; '' when the
    city has none — en_site.load_all then builds no such version)."""
    from dataclasses import replace

    from . import city
    loc = LOCALES[code.lower()]
    names = city.current().intl(loc.code)
    return replace(loc, site_name=str(names.get("site_name") or ""), city=str(names.get("city") or ""),
                   home_h1=str(names.get("home_h1") or ""))


def by_html(html: str) -> Locale | None:
    return next((loc for loc in LOCALES.values() if loc.html == html), None)


def code_of_path(path: str) -> str:
    """'/ja/places/x/' -> 'ja'; a Korean path -> 'ko'."""
    first = path.replace("\\", "/").strip("/").split("/", 1)[0].lower()
    return first if first in LOCALES else "ko"


# ------------------------------------------------------------------ promotional words and disclaimers
def _word_rx(words: tuple, cjk: bool, code: str) -> re.Pattern | None:
    if not words:
        return None
    if cjk:
        return re.compile("|".join(map(re.escape, words)))
    stems = {   # inflected forms of the spec's words
        "de": {"beste": r"beste[nmrs]?", "beliebt": r"beliebte?[nmrs]?", "berühmt": r"berühmte?[nmrs]?",
               "Geheimtipp": r"Geheimtipps?", "Muss": r"(?-i:Muss)"},
        "fr": {"incontournable": r"incontournables?", "célèbre": r"célèbres?", "populaire": r"populaires?",
               "meilleur": r"meilleure?s?"},
        "es": {"famoso": r"famos[oa]s?", "popular": r"populares|popular", "mejor": r"mejores|mejor",
               "imprescindible": r"imprescindibles?"},
        "ru": {"обязательно": r"обязательн\w*", "знаменитый": r"знаменит\w*", "популярный": r"популярн\w*",
               "лучший": r"лучш\w*"},
    }.get(code, {})
    alts = [stems.get(w, re.escape(w)) for w in words]
    return re.compile(rf"(?<![\w-])(?:{'|'.join(alts)})(?![\w-])", re.I)


@functools.lru_cache(maxsize=None)
def promo_rx(code: str):
    loc = get(code)
    return _word_rx(loc.promo, loc.cjk, code)


@functools.lru_cache(maxsize=None)
def disclaimer_rx(code: str):
    loc = get(code)
    return _word_rx(loc.disclaimers, loc.cjk, code)


# ------------------------------------------------------------------ Chinese script (OpenCC character tables)
@functools.lru_cache(maxsize=None)
def _opencc_tables() -> tuple[dict, dict, set]:
    """(simplified -> [traditional …], traditional -> [simplified …], characters Taiwan/Hong Kong standards use)."""
    import opencc   # opencc-python-reimplemented (requirements.txt)
    base = os.path.join(os.path.dirname(opencc.__file__), "dictionary")

    def load(name: str) -> dict:
        out = {}
        with open(os.path.join(base, name), encoding="utf-8") as f:
            for line in f:
                k, _, v = line.rstrip("\n").partition("\t")
                if k:
                    out[k] = v.split(" ")
        return out
    st, ts = load("STCharacters.txt"), load("TSCharacters.txt")
    variants = {c for name in ("TWVariants.txt", "HKVariants.txt") for vals in load(name).values() for c in vals}
    return st, ts, variants


def traditional_only(text: str) -> list[str]:
    """Characters of `text` that Simplified Chinese does not use (OpenCC: a traditional form whose simplified form
    differs and that is not itself a simplified character)."""
    _, ts, _ = _opencc_tables()
    return list(dict.fromkeys(c for c in text if c in ts and c not in ts[c]))


def simplified_only(text: str) -> list[str]:
    """Characters of `text` that Traditional Chinese (Taiwan / Hong Kong standards) does not use."""
    st, _, variants = _opencc_tables()
    return list(dict.fromkeys(c for c in text if c in st and c not in st[c] and c not in variants))


# ------------------------------------------------------------------ the language of a text
STOPWORDS = {
    "en": {"the", "and", "of", "to", "is", "are", "was", "with", "for", "on", "at", "from", "this", "that", "it", "its",
           "by", "or", "you", "your", "there", "which", "be", "has", "have", "can", "an"},
    "de": {"der", "die", "das", "und", "ist", "sind", "mit", "für", "von", "zu", "im", "den", "dem", "des", "ein",
           "eine", "einen", "auf", "nicht", "sie", "wird", "werden", "bei", "auch", "als", "nach", "aus", "am", "vom",
           "zum", "zur", "über", "oder", "kann", "gibt"},
    "fr": {"le", "les", "et", "est", "sont", "des", "du", "une", "pour", "dans", "sur", "avec", "au", "aux", "par",
           "qui", "il", "elle", "ne", "pas", "ce", "cette", "ou", "vous", "peut", "être"},
    "es": {"el", "los", "las", "y", "son", "del", "una", "para", "con", "por", "al", "lo", "su", "sus", "está",
           "están", "pero", "hay", "puede", "también", "muy", "como",
           # 2026-10-14: words only Spanish writes among these four languages — without them a plain Spanish sentence
           # ('Huirak es un restaurante de sopas cuya especialidad es la sopa de pescado') had no stopword at all, since
           # de/la/en/un are French too; English or German left in Spanish is caught exactly as before
           "es", "qué", "sí", "cuya", "cuyo", "tiene", "tienen", "hasta", "desde"},
}
_SHARED = {w for a in STOPWORDS for b in STOPWORDS if a < b for w in STOPWORDS[a] & STOPWORDS[b]}
_STOP = {k: v - _SHARED for k, v in STOPWORDS.items()}


def _stop_counts(text: str) -> dict[str, int]:
    words = re.findall(r"[^\W\d_]+", text.lower())
    return {k: sum(1 for w in words if w in s) for k, s in _STOP.items()}


def script_problems(text: str, code: str, prose: bool = True) -> list[str]:
    """What is wrong with the script or language of a translated text (English: nothing here — tools/en_content.py
    style() has its own checks). prose: a sentence or more (the kana, Cyrillic and stopword tests need words)."""
    loc = get(code)
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not t or code == "en":
        return []
    out: list[str] = []
    if code in ("zh-hans", "zh-hant", "ja"):
        if CYR.search(t):
            out.append(f"Cyrillic in {loc.english}")
    else:
        hits = "".join(dict.fromkeys(CJK.findall(t) + KANA.findall(t)))
        if hits:
            out.append(f"Chinese or Japanese characters in {loc.english}: {hits[:10]}")
    if code == "zh-hans":
        bad = traditional_only(t)
        if bad:
            out.append(f"Traditional characters in Simplified Chinese: {''.join(bad[:10])}")
    if code == "zh-hant":
        bad = simplified_only(t)
        if bad:
            out.append(f"Simplified characters in Traditional Chinese: {''.join(bad[:10])}")
    if code in ("zh-hans", "zh-hant") and KANA.search(t):
        out.append(f"Japanese kana in {loc.english}: {''.join(dict.fromkeys(KANA.findall(t)))[:10]}")
    if not prose:   # a label or a value (romanized addresses and names are Latin in every language)
        return out
    if code == "ja":
        for s in loc.sentences(t):
            if len(CJK.findall(s)) >= 8 and not KANA.search(s):
                out.append(f"Chinese text in Japanese (no kana): '{s[:30]}'")
                break
        for s in loc.sentences(t):
            words = re.findall(r"[A-Za-z]{2,}", s)
            if len(words) >= 4 and not KANA.search(s) and not CJK.search(s):
                out.append(f"English left in Japanese: '{s[:40]}'")
                break
    elif code in ("zh-hans", "zh-hant"):
        for s in loc.sentences(t):
            words = re.findall(r"[A-Za-z]{2,}", s)
            if len(words) >= 4 and not CJK.search(s):
                out.append(f"English left in {loc.english}: '{s[:40]}'")
                break
    elif code == "ru":
        lat, cyr = len(re.findall(r"[A-Za-z]", t)), len(CYR.findall(t))
        en = _stop_counts(t)["en"]
        if (lat + cyr >= 20 and lat > 0.3 * (lat + cyr)) or en >= 2:
            out.append(f"Latin text in Russian: '{t[:40]}'")
    else:   # de, fr, es: the prose is in the language (a small stopword test)
        words = re.findall(r"[^\W\d_]+", t)
        counts = _stop_counts(t)
        own = counts[code]
        other = max((k for k in counts if k != code), key=lambda k: counts[k])
        if (counts[other] >= 2 and counts[other] > own) or (len(words) >= 12 and own == 0):
            name = {"en": "English", "de": "German", "fr": "French", "es": "Spanish"}[other]
            out.append(f"{name} left in {loc.english} (stopwords {other} {counts[other]} vs {code} {own}): '{t[:40]}'")
    return out


# ------------------------------------------------------------------ Russian: Kontsevich transcription of Korean
# choseong 0..18: ㄱ ㄲ ㄴ ㄷ ㄸ ㄹ ㅁ ㅂ ㅃ ㅅ ㅆ ㅇ ㅈ ㅉ ㅊ ㅋ ㅌ ㅍ ㅎ — word-initial / after an obstruent (voiceless) and
# after a vowel or a sonorant (voiced)
_K_INIT = ("к", "кк", "н", "т", "тт", "р", "м", "п", "пп", "с", "сс", "", "ч", "чч", "чх", "кх", "тх", "пх", "х")
_K_MED = ("г", "кк", "н", "д", "тт", "р", "м", "б", "пп", "с", "сс", "", "дж", "чч", "чх", "кх", "тх", "пх", "х")
# jungseong 0..20: ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅗ ㅘ ㅙ ㅚ ㅛ ㅜ ㅝ ㅞ ㅟ ㅠ ㅡ ㅢ ㅣ
_K_VOW = ("а", "э", "я", "йе", "о", "е", "ё", "йе", "о", "ва", "вэ", "ве", "ё", "у", "во", "ве", "ви", "ю", "ы",
          "ый", "и")
# jongseong 1..27 by how they sound before a consonant or at the end
_K_K, _K_T, _K_P = {1, 2, 3, 9, 24}, {7, 19, 20, 22, 23, 25, 27}, {14, 17, 18, 26}
_K_L = {8, 11, 12, 13, 15}
_K_FIN = {**{f: "к" for f in _K_K}, **{f: "т" for f in _K_T}, **{f: "п" for f in _K_P}, **{f: "ль" for f in _K_L},
          4: "н", 5: "н", 6: "н", 10: "м", 16: "м", 21: "н", 0: ""}
_K_SONORANT = {0, 4, 5, 6, 8, 10, 11, 12, 13, 15, 16, 21}
# a final before a vowel (liaison): (kept in this syllable, carried to the next)
_K_LIAISON = {1: ("", "г"), 2: ("", "кк"), 3: ("к", "с"), 4: ("", "н"), 5: ("н", "дж"), 6: ("", "н"), 7: ("", "д"),
              8: ("", "р"), 9: ("ль", "г"), 10: ("ль", "м"), 11: ("ль", "б"), 12: ("ль", "с"), 13: ("ль", "тх"),
              14: ("ль", "пх"), 15: ("", "р"), 16: ("", "м"), 17: ("", "б"), 18: ("п", "с"), 19: ("", "с"),
              20: ("", "сс"), 21: ("нъ", ""), 22: ("", "дж"), 23: ("", "чх"), 24: ("", "кх"), 25: ("", "тх"),
              26: ("", "пх"), 27: ("", "")}
_K_ADMIN = {"동": "дон", "읍": "ып", "면": "мён", "리": "ри"}


def _k_boundary(f: int, i: int, v: int) -> tuple[str, str]:
    """(this syllable's final, the next syllable's initial) for final f, next initial i and next vowel v —
    liaison, nasalization, ㄹ assimilation and ㅎ aspiration, as Kontsevich writes the pronunciation."""
    if f == 0:
        return "", _K_MED[i]
    if i == 11:   # a vowel next
        if v == 20 and f in (7, 25):   # 해돋이 Хэдоджи, 같이 качхи
            return "", "дж" if f == 7 else "чх"
        return _K_LIAISON[f]
    if i == 18:   # ㅎ next: aspiration
        if f in _K_K:
            return "", "кх"
        if f in _K_T:
            return "", "тх" if f != 22 else "чх"
        if f in _K_P:
            return "", "пх"
        return _K_FIN[f], "х"
    if f in (27, 6, 15) and i in (0, 3, 12):   # 좋고 чокхо
        return {27: "", 6: "н", 15: "ль"}[f], {0: "кх", 3: "тх", 12: "чх"}[i]
    if i in (2, 6):   # ㄴ ㅁ next: 백마 Пэнма, 십만 симман
        if f in _K_K:
            return "н", _K_INIT[i]
        if f in _K_T:
            return "н", _K_INIT[i]
        if f in _K_P:
            return "м", _K_INIT[i]
        if i == 2 and f in _K_L:   # 칼날 каллаль
            return "л", "л"
    if i == 5:   # ㄹ next: 신라 Силла, 종로 Чонно, 백리 пэнни
        if f in (4, 5) or f in _K_L:
            return "л", "л"
        if f in (10, 16, 21):
            return _K_FIN[f], "н"
        if f in _K_K or f in _K_T:
            return "н", "н"
        if f in _K_P:
            return "м", "н"
    return _K_FIN[f], (_K_MED[i] if f in _K_SONORANT else _K_INIT[i])


def _k_run(text: str) -> str:
    """One run of Hangul syllables in Cyrillic (lowercase), sound changes inside the run."""
    parts = [((ord(c) - 0xAC00) // 588, (ord(c) - 0xAC00) // 28 % 21, (ord(c) - 0xAC00) % 28) for c in text]
    out, carry = [], None
    for n, (cho, jung, jong) in enumerate(parts):
        init = _K_INIT[cho] if carry is None else carry
        if n == 0 and cho == 11:
            vow = {5: "э", 3: "йе", 7: "йе"}.get(jung, _K_VOW[jung])
        elif cho != 11 and jung in (3, 7):   # ㅒ ㅖ after a consonant
            vow = "е"
        else:
            vow = _K_VOW[jung]
        nxt = parts[n + 1] if n + 1 < len(parts) else None
        if nxt:
            fin, carry = _k_boundary(jong, nxt[0], nxt[1])
        else:
            fin, carry = _K_FIN[jong], None
        out.append(init + vow + fin)
    return "".join(out)


def kontsevich(text: str | None) -> str:
    """Cyrillic for a Korean name by the Kontsevich system ('경암동' -> 'Кёнам-дон'): each
    word capitalized, Latin letters and digits kept, administrative units hyphenated."""
    words = []
    for word in re.sub(r"\s+", " ", str(text or "")).strip().split(" "):
        if not word:
            continue
        if len(word) >= 3 and all(0xAC00 <= ord(c) <= 0xD7A3 for c in word) and word[-1] in "동읍면":
            base = _k_run(word[:-1])
            words.append(base[:1].upper() + base[1:] + "-" + _K_ADMIN[word[-1]])
            continue
        out, prev = [], ""
        for run in re.findall(r"[가-힣]+|[^가-힣]+", word):
            if all(0xAC00 <= ord(c) <= 0xD7A3 for c in run):
                r = _k_run(run)
                if not prev or not prev[-1].isalnum():
                    r = r[:1].upper() + r[1:]
                out.append(r)
            else:
                out.append(run)
            prev = out[-1]
        words.append("".join(out))
    return " ".join(words)


def area_name(area: str | None, code: str) -> str:
    """An administrative area ('장미동') in a language without a written form of its own in our data: Revised
    Romanization for every language but Russian ('Jangmi-dong'), Kontsevich Cyrillic for Russian ('Чанми-дон')."""
    from .en_source import _admin, romanize
    a = re.sub(r"\s+", " ", str(area or "")).strip()
    if not a:
        return ""
    if code == "ru":
        if re.fullmatch(r"[가-힣]{2,}", a) and a[-1] in "동읍면리":
            base = _k_run(a[:-1])
            return f"{base[:1].upper()}{base[1:]}-{_K_ADMIN[a[-1]]}"
        return kontsevich(a)
    if re.fullmatch(r"[가-힣]{2,}", a) and a[-1] in "동읍면리":
        return _admin(a)
    return romanize(a)


# the map's keyboard line (map.js: the map box's accessible name '… · <keys>' — the map takes the focus, the arrow keys
# move it, + and − zoom): English and Korean are in map.js itself; the other versions pass theirs in data-words.keys
# (post-launch review 2026-10-14: the Japanese maps had none)
MAP_KEYS = {
    "ja": "矢印キーで移動、+ と − キーで拡大・縮小",
    "zh-hans": "方向键移动，+ − 键放大缩小",
    "zh-hant": "方向鍵移動，+ − 鍵放大縮小",
    "de": "Pfeiltasten verschieben, + und − zoomen",
    "fr": "flèches pour déplacer, + et − pour zoomer",
    "es": "flechas para moverse, + y − para acercar o alejar",
    "ru": "стрелки — сдвиг, + и − — масштаб",
}



# the site search of the other language versions (owner 2026-10-14: '이 언어들도 다 검색이 되는 거지?'): the bar's field,
# the search page (<home>search/) and the words assets/search.js prints there (data-words). {r} the city, {q} the query.
# Nothing found (QA 2026-10-15 F08): none (one line), sug before the names it may have meant, diet for a food-rule
# word (the site has no such data: it says so and names no place), ask / all ({n} places) / browse in the help below.
# Evaluation 2026-10-18: scope — the line under the box (what the search finds; travel questions go to the AI chat,
# named as on the chat's launcher, templates/_chat.html.j2); related — the heading of the guides that match a part of
# a query nothing matches whole; syn — before the words a query word was also searched as (present.SEARCH_CONCEPTS).
SEARCH_WORDS = {
    "en": {"bar": "Search places, dishes, areas", "go": "Search", "close": "Close search", "open": "Search",
           "label": "Place name, dish, area, course, guide or event", "ph": "Name, dish or area",
           "h1": "Search {r}", "title": "Search {r}: places, dishes, areas and courses",
           "desc": "Find {r}'s places by name, signature dish or area, and its courses, guides and events by name.",
           "none": "Nothing matches ‘{q}’.", "dir": "Every place", "jump": "Jump to",
           "menu": "Dish: ", "other": "Also: ", "via": "Stops: ", "des": "Listed: ", "of": "{n} of {m}",
           "sug": "Did you mean: ", "ask": "Ask the AI chat",
           "all": "Show every place ({n})", "browse": "Browse the lists",
           "scope": "Finds places by name, dish or area, and guides; ask the AI chat your travel questions.",
           "related": "Related guides", "syn": "Also searched: ",
           "diet": "This site has no halal, vegetarian, vegan or allergy information on its restaurants. Ask the"
                   " restaurant before you go; when the site has its phone number, it is on the restaurant's page."},
    "ja": {"bar": "場所・料理・地域を検索", "go": "検索", "close": "検索を閉じる", "open": "検索",
           "label": "場所の名前、料理、地域、コース・ガイド・イベントの名前", "ph": "名前・料理・地域",
           "h1": "{r}を検索", "title": "{r}を検索：場所・料理・地域・コース",
           "desc": "{r}の場所を名前・看板料理・地域で、コース・ガイド・イベントを名前で探せます。",
           "none": "「{q}」に合う結果はありません。", "dir": "すべての場所", "jump": "移動",
           "menu": "料理：", "other": "別名：", "via": "経由：", "des": "指定：", "of": "{m}件中{n}件",
           "sug": "もしかして：", "ask": "AIチャットに聞く",
           "all": "すべての場所を表示（{n}か所）", "browse": "一覧から探す",
           "scope": "場所の名前・料理・地域・ガイドを探せます。旅行の質問はAIチャットへどうぞ。",
           "related": "関連ガイド", "syn": "あわせて検索：",
           "diet": "このサイトには飲食店のハラール・ベジタリアン・ヴィーガン・アレルギーの情報がありません。"
                   "訪れる前にお店に直接確認してください。電話番号がわかる場合は、そのお店のページに載っています。"},
    "zh-hans": {"bar": "搜索地点、菜品、地区", "go": "搜索", "close": "关闭搜索", "open": "搜索",
                "label": "地点名称、菜品、地区，或路线、指南、活动名称", "ph": "名称、菜品或地区",
                "h1": "在{r}搜索", "title": "在{r}搜索：地点、菜品、地区与路线",
                "desc": "按名称、招牌菜或地区查找{r}的地点，按名称查找路线、指南和活动。",
                "none": "没有与“{q}”相符的结果。", "dir": "全部地点", "jump": "跳转",
                "menu": "菜品：", "other": "别名：", "via": "途经：", "des": "认定：", "of": "{m}条中的{n}条",
                "sug": "您是不是要找：", "ask": "询问AI助手",
                "all": "显示全部地点（{n}个）", "browse": "按列表查找",
                "scope": "按名称、菜品、地区查找地点和指南；旅行问题请问AI助手。",
                "related": "相关指南", "syn": "同时搜索：",
                "diet": "本网站没有餐厅的清真、素食或过敏原信息。前往前请直接向餐厅确认；本网站有餐厅电话时，可在该餐厅的页面上找到。"},
    "zh-hant": {"bar": "搜尋地點、菜色、地區", "go": "搜尋", "close": "關閉搜尋", "open": "搜尋",
                "label": "地點名稱、菜色、地區，或路線、指南、活動名稱", "ph": "名稱、菜色或地區",
                "h1": "在{r}搜尋", "title": "在{r}搜尋：地點、菜色、地區與路線",
                "desc": "依名稱、招牌菜或地區查找{r}的地點，依名稱查找路線、指南和活動。",
                "none": "沒有與「{q}」相符的結果。", "dir": "全部地點", "jump": "跳至",
                "menu": "菜色：", "other": "別名：", "via": "途經：", "des": "認定：", "of": "{m}筆中的{n}筆",
                "sug": "您是不是要找：", "ask": "詢問AI助手",
                "all": "顯示全部地點（{n}處）", "browse": "依列表查找",
                "scope": "依名稱、菜色、地區查找地點和指南；旅行問題請問AI助手。",
                "related": "相關指南", "syn": "同時搜尋：",
                "diet": "本網站沒有餐廳的清真、素食或過敏原資訊。前往前請直接向餐廳確認；本網站有餐廳電話時，可在該餐廳的頁面上找到。"},
    "de": {"bar": "Orte, Gerichte, Viertel suchen", "go": "Suchen", "close": "Suche schließen", "open": "Suche",
           "label": "Ortsname, Gericht, Viertel, Route, Ratgeber oder Veranstaltung", "ph": "Name, Gericht oder Viertel",
           "h1": "{r} durchsuchen", "title": "{r} durchsuchen: Orte, Gerichte, Viertel und Routen",
           "desc": "Orte in {r} nach Name, Hauptgericht oder Viertel finden, Routen, Ratgeber und Veranstaltungen nach Namen.",
           "none": "Nichts passt zu „{q}“.", "dir": "Alle Orte", "jump": "Springen zu",
           "menu": "Gericht: ", "other": "Auch: ", "via": "Stationen: ", "des": "Ausgezeichnet: ", "of": "{n} von {m}",
           "sug": "Meinten Sie: ", "ask": "Den KI-Chat fragen",
           "all": "Alle Orte zeigen ({n})", "browse": "In den Listen suchen",
           "scope": "Findet Orte nach Name, Gericht oder Viertel und Ratgeber; Reisefragen beantwortet der KI-Chat.",
           "related": "Passende Ratgeber", "syn": "Auch gesucht: ",
           "diet": "Diese Website hat zu ihren Restaurants keine Angaben zu halal, vegetarisch, vegan oder Allergenen."
                   " Fragen Sie vor dem Besuch im Restaurant nach; hat die Website seine Telefonnummer, steht sie"
                   " auf der Seite des Restaurants."},
    "fr": {"bar": "Rechercher lieux, plats, quartiers", "go": "Rechercher", "close": "Fermer la recherche",
           "open": "Recherche", "label": "Nom de lieu, plat, quartier, itinéraire, guide ou événement",
           "ph": "Nom, plat ou quartier", "h1": "Rechercher à {r}",
           "title": "Rechercher à {r} : lieux, plats, quartiers et itinéraires",
           "desc": "Trouvez les lieux de {r} par nom, plat phare ou quartier, et les itinéraires, guides et événements par nom.",
           "none": "Aucun résultat pour « {q} ».", "dir": "Tous les lieux",
           "jump": "Aller à", "menu": "Plat : ", "other": "Aussi : ", "via": "Étapes : ",
           "des": "Labellisé : ", "of": "{n} sur {m}",
           "sug": "Vouliez-vous dire : ", "ask": "Demander au chat IA",
           "all": "Afficher tous les lieux ({n})", "browse": "Parcourir les listes",
           "scope": "Trouve les lieux par nom, plat ou quartier, et les guides ; posez vos questions de voyage"
                    " au chat IA.",
           "related": "Guides liés", "syn": "Recherché aussi : ",
           "diet": "Ce site n’a aucune information halal, végétarienne, végane ou sur les allergènes pour ses restaurants."
                   " Renseignez-vous auprès du restaurant avant d’y aller ; quand le site a son numéro de téléphone,"
                   " il figure sur la page du restaurant."},
    "es": {"bar": "Buscar lugares, platos, barrios", "go": "Buscar", "close": "Cerrar la búsqueda", "open": "Buscar",
           "label": "Nombre del lugar, plato, barrio, ruta, guía o evento", "ph": "Nombre, plato o barrio",
           "h1": "Buscar en {r}", "title": "Buscar en {r}: lugares, platos, barrios y rutas",
           "desc": "Encuentre los lugares de {r} por nombre, plato estrella o barrio, y las rutas, guías y eventos por nombre.",
           "none": "No hay resultados para «{q}».", "dir": "Todos los lugares",
           "jump": "Ir a", "menu": "Plato: ", "other": "También: ", "via": "Paradas: ", "des": "Distinción: ",
           "of": "{n} de {m}",
           "sug": "Quizá quiso decir: ", "ask": "Preguntar al chat IA",
           "all": "Ver todos los lugares ({n})", "browse": "Buscar en las listas",
           "scope": "Busca lugares por nombre, plato o barrio, y guías; haga sus preguntas de viaje al chat IA.",
           "related": "Guías relacionadas", "syn": "También se buscó: ",
           "diet": "Este sitio no tiene información halal, vegetariana, vegana ni sobre alérgenos de sus restaurantes."
                   " Consulte al restaurante antes de ir; cuando el sitio tiene su teléfono, figura en la página"
                   " del restaurante."},
    "ru": {"bar": "Поиск мест, блюд, районов", "go": "Найти", "close": "Закрыть поиск", "open": "Поиск",
           "label": "Название места, блюдо, район, маршрут, путеводитель или событие", "ph": "Название, блюдо или район",
           "h1": "Поиск: {r}", "title": "Поиск: {r} — места, блюда, районы и маршруты",
           "desc": "Ищите места в городе {r} по названию, фирменному блюду или району, а маршруты, путеводители и события — по названию.",
           "none": "По запросу «{q}» ничего не найдено.", "dir": "Все места",
           "jump": "Перейти к", "menu": "Блюдо: ", "other": "Также: ", "via": "Остановки: ", "des": "Статус: ",
           "of": "{n} из {m}",
           "sug": "Возможно, вы искали: ", "ask": "Спросить ИИ-чат",
           "all": "Показать все места ({n})", "browse": "Искать по спискам",
           "scope": "Ищет места по названию, блюду или району, а также путеводители; вопросы о поездке"
                    " задайте ИИ-чату.",
           "related": "Связанные путеводители", "syn": "Также искали: ",
           "diet": "На этом сайте нет сведений о халяльной, вегетарианской или веганской еде и об аллергенах в"
                   " ресторанах. Уточните в ресторане перед визитом; если на сайте есть его телефон, он указан"
                   " на странице ресторана."},
}


# the place page's '주변·함께 가기' chapter (owner 2026-10-14: 시각화·모션; templates/_near.html.j2): the words of the course
# segments, the nearby rows, the guide and event cards, for Korean and every version. The headings keep their words
# (Korean literals; the versions' chrome strings courses_here, near_sights, near_biz, guides_here, events_here), so a
# version never drops out of the build for a missing string. Counts sit in parentheses: no plural forms. Distances are
# straight lines between coordinates and say so in every language ({d}: present.dist / Locale.dist).
# part_of / same_building: the line under a place's name that names the place it is inside / the other page for the
# same building ({name}: that place's name in this version, a link where it has a page here); parts: the heading of
# the list of places inside this one (pipeline/relations.py, operator decision 2026-10-16).
NEAR_WORDS = {
    "ko": {"prev": "이전 경유지", "next": "다음 경유지", "here": "이곳", "first": "코스 시작", "last": "코스 끝",
           "to_next": "다음 경유지까지", "to_here": "이곳까지", "varies": "{label} 출처마다 다름", "leg": "직선 {d}", "pos": "경유지 {N}곳 중 {n}번째", "order": "경유지 순서",
           "key": "점 사이 간격은 순서만 · 거리는 좌표 사이 직선", "more_segs": "다른 구간 보기 ({n})",
           "more_guides": "가이드 더 보기 ({n})", "more_events": "행사 더 보기 ({n})", "scale": "막대 끝 = 직선 {d}",
           "see_map": "지도에서 보기", "ev_on": "진행·예정", "ev_past": "지난 회차", "ev_varies": "기간 출처마다 다름",
           "credit": "사진 출처: 한국관광공사 · {lic}", "ext": "지도 검색", "branch": "다른 안",
           "part_of": "속한 곳: {name}", "same_building": "같은 건물: {name}", "parts": "{name} 안에 있는 곳"},
    "en": {"prev": "Previous stop", "next": "Next stop", "here": "Here", "first": "Start of the course",
           "last": "End of the course", "to_next": "To the next stop:", "to_here": "To here:",
           "varies": "{label}: sources differ", "leg": "straight-line {d}",
           "pos": "stop {n} of {N}", "order": "Order of stops",
           "key": "Dots are spaced by order only · distances are straight lines between coordinates",
           "more_segs": "Other sections ({n})", "more_guides": "More guides ({n})", "more_events": "More events ({n})",
           "scale": "Full bar = straight-line {d}", "see_map": "See on the map", "ev_on": "On now or coming up",
           "ev_past": "Past edition", "ev_varies": "Dates differ by source",
           "credit": "Photos: Korea Tourism Organization · {lic}", "ext": "map search", "branch": "Other option",
           "part_of": "Part of {name}", "same_building": "Same building as {name}", "parts": "Places within {name}"},
    "ja": {"prev": "前の経由地", "next": "次の経由地", "here": "ここ", "first": "コースの始まり", "last": "コースの終わり",
           "to_next": "次の経由地まで", "to_here": "ここまで", "varies": "{label}：出典により異なる", "leg": "直線{d}", "pos": "{N}か所中{n}番目の経由地", "order": "経由地の順序",
           "key": "点の間隔は順序だけを表します・距離は座標間の直線距離です", "more_segs": "ほかの区間（{n}）",
           "more_guides": "ほかのガイド（{n}）", "more_events": "ほかのイベント（{n}）", "scale": "バーの端＝直線{d}",
           "see_map": "地図で見る", "ev_on": "開催中・開催予定", "ev_past": "過去の開催", "ev_varies": "日程は出典により異なる",
           "credit": "写真：韓国観光公社・{lic}", "ext": "地図で検索", "branch": "別の案",
           "part_of": "{name}内にあります", "same_building": "{name}と同じ建物です", "parts": "{name}内の場所"},
    "zh-hans": {"prev": "上一站", "next": "下一站", "here": "此处", "first": "路线开始", "last": "路线结束",
                "to_next": "到下一站", "to_here": "到此处", "varies": "{label}：来源不一致", "leg": "直线{d}", "pos": "共{N}站中的第{n}站", "order": "途经顺序",
                "key": "圆点间距只表示顺序 · 距离为坐标之间的直线距离", "more_segs": "其他路段（{n}）",
                "more_guides": "更多指南（{n}）", "more_events": "更多活动（{n}）", "scale": "条形末端 = 直线{d}",
                "see_map": "在地图上查看", "ev_on": "进行中·即将举行", "ev_past": "往届", "ev_varies": "日期因来源而异",
                "credit": "照片：韩国观光公社 · {lic}", "ext": "地图搜索", "branch": "另一方案",
                "part_of": "位于{name}内", "same_building": "与{name}是同一栋建筑", "parts": "{name}内的地点"},
    "zh-hant": {"prev": "上一站", "next": "下一站", "here": "此處", "first": "路線開始", "last": "路線結束",
                "to_next": "到下一站", "to_here": "到此處", "varies": "{label}：來源不一致", "leg": "直線{d}", "pos": "共{N}站中的第{n}站", "order": "途經順序",
                "key": "圓點間距只表示順序 · 距離為座標之間的直線距離", "more_segs": "其他路段（{n}）",
                "more_guides": "更多指南（{n}）", "more_events": "更多活動（{n}）", "scale": "長條末端 = 直線{d}",
                "see_map": "在地圖上查看", "ev_on": "進行中·即將舉行", "ev_past": "往屆", "ev_varies": "日期因來源而異",
                "credit": "照片：韓國觀光公社 · {lic}", "ext": "地圖搜尋", "branch": "另一方案",
                "part_of": "位於{name}內", "same_building": "與{name}是同一棟建築", "parts": "{name}內的地點"},
    "de": {"prev": "Vorherige Station", "next": "Nächste Station", "here": "Hier", "first": "Beginn der Route",
           "last": "Ende der Route", "to_next": "Bis zur nächsten Station:", "to_here": "Bis hierher:",
           "varies": "{label}: je nach Quelle verschieden", "leg": "Luftlinie {d}",
           "pos": "Station {n} von {N}", "order": "Reihenfolge der Stationen",
           "key": "Punktabstände zeigen nur die Reihenfolge · Entfernungen sind Luftlinien zwischen Koordinaten",
           "more_segs": "Weitere Abschnitte ({n})", "more_guides": "Weitere Reiseführer ({n})",
           "more_events": "Weitere Veranstaltungen ({n})", "scale": "Ganzer Balken = Luftlinie {d}",
           "see_map": "Auf der Karte ansehen", "ev_on": "Läuft oder geplant", "ev_past": "Vergangene Ausgabe",
           "ev_varies": "Termine je nach Quelle verschieden", "credit": "Fotos: Koreanische Tourismusorganisation · {lic}", "ext": "Kartensuche", "branch": "Andere Variante",
           "part_of": "Teil von {name}", "same_building": "Im selben Gebäude wie {name}", "parts": "Orte innerhalb von {name}"},
    "fr": {"prev": "Étape précédente", "next": "Étape suivante", "here": "Ici", "first": "Début du circuit",
           "last": "Fin du circuit", "to_next": "Jusqu'à l'étape suivante :", "to_here": "Jusqu'ici :",
           "varies": "{label} : les sources divergent", "leg": "{d} en ligne droite",
           "pos": "étape {n} sur {N}", "order": "Ordre des étapes",
           "key": "L'écart entre les points indique seulement l'ordre · distances en ligne droite entre les coordonnées",
           "more_segs": "Autres tronçons ({n})", "more_guides": "Autres guides ({n})", "more_events": "Autres événements ({n})",
           "scale": "Barre entière = {d} en ligne droite", "see_map": "Voir sur la carte", "ev_on": "En cours ou à venir",
           "ev_past": "Édition passée", "ev_varies": "Dates différentes selon les sources",
           "credit": "Photos : Office national du tourisme coréen · {lic}", "ext": "recherche sur la carte", "branch": "Autre option",
           "part_of": "Fait partie de {name}", "same_building": "Même bâtiment que {name}", "parts": "Lieux situés dans {name}"},
    "es": {"prev": "Parada anterior", "next": "Parada siguiente", "here": "Aquí", "first": "Inicio de la ruta",
           "last": "Fin de la ruta", "to_next": "Hasta la parada siguiente:", "to_here": "Hasta aquí:",
           "varies": "{label}: las fuentes difieren", "leg": "{d} en línea recta",
           "pos": "parada {n} de {N}", "order": "Orden de las paradas",
           "key": "La separación entre puntos solo indica el orden · las distancias son líneas rectas entre coordenadas",
           "more_segs": "Otros tramos ({n})", "more_guides": "Más guías ({n})", "more_events": "Más eventos ({n})",
           "scale": "Barra completa = {d} en línea recta", "see_map": "Ver en el mapa", "ev_on": "En curso o próximo",
           "ev_past": "Edición pasada", "ev_varies": "Las fechas varían según la fuente",
           "credit": "Fotos: Organización de Turismo de Corea · {lic}", "ext": "búsqueda en el mapa", "branch": "Otra opción",
           "part_of": "Forma parte de {name}", "same_building": "Mismo edificio que {name}", "parts": "Lugares dentro de {name}"},
    "ru": {"prev": "Предыдущая остановка", "next": "Следующая остановка", "here": "Здесь", "first": "Начало маршрута",
           "last": "Конец маршрута", "to_next": "До следующей остановки:", "to_here": "До этого места:",
           "varies": "{label}: источники расходятся", "leg": "по прямой {d}",
           "pos": "остановка {n} из {N}", "order": "Порядок остановок",
           "key": "Интервалы между точками показывают только порядок · расстояния — по прямой между координатами",
           "more_segs": "Другие участки ({n})", "more_guides": "Ещё путеводители ({n})", "more_events": "Ещё события ({n})",
           "scale": "Вся полоса = {d} по прямой", "see_map": "Посмотреть на карте", "ev_on": "Идёт или скоро",
           "ev_past": "Прошедший выпуск", "ev_varies": "Даты в источниках расходятся",
           "credit": "Фото: Корейская организация по туризму · {lic}", "ext": "поиск на карте", "branch": "Другой вариант",
           "part_of": "Входит в состав: {name}", "same_building": "То же здание: {name}", "parts": "Объекты на территории: {name}"},
}


# the list pages' filter bar (QA 2026-10-15 SRC-01: the other versions had no filters and no list | map switch on phones):
# the words of templates/_filters.html.j2 for Korean and every version (hand-written like NEAR_WORDS, so a version never
# drops out of the build for a missing string). The chips' own labels are the data's (type, 권역, theme and check
# labels from strings.json); the filter VALUES are the Korean ones in every version (one URL vocabulary: ?type=한식 …).
# of: after the count while a filter is set ({m} = every place of the list). clear_one / clear_all: the buttons of the
# zero-result panel (outside evaluation 2026-10-18: '박물관·전시 + 섬과 바다' left only a sentence) — one per filter that
# brings rows back on its own ({v} = that chip's label in this version) and the reset of every filter. off_map: after
# the map caption, the shown places without coordinates ({n}; worded without a plural form, so one string serves 1 and
# 23 alike).
LIST_WORDS = {
    "ko": {"type": "유형", "all": "전체", "filters": "필터", "view": "보기", "list": "목록", "map": "지도", "area": "권역",
           "all_areas": "모든 권역", "theme": "테마", "all_themes": "모든 테마",
           "empty": "조건에 맞는 곳이 없습니다. 필터를 바꿔 보세요.", "of": " (전체 {m}곳 중)",
           "clear_one": "{v} 조건 해제", "clear_all": "전체 조건 초기화", "off_map": "지도에 없는 {n}곳은 목록에서"},
    "en": {"type": "Type", "all": "All", "filters": "Filters", "view": "View", "list": "List", "map": "Map", "area": "Area",
           "all_areas": "All areas", "theme": "Theme", "all_themes": "All themes",
           "empty": "No places match these filters. Try changing them.", "of": " (of {m})",
           "clear_one": "Remove filter: {v}", "clear_all": "Clear all filters", "off_map": "Not on the map: {n} (see the list)"},
    "ja": {"type": "種類", "all": "すべて", "filters": "絞り込み", "view": "表示", "list": "一覧", "map": "地図", "area": "エリア",
           "all_areas": "すべてのエリア", "theme": "テーマ", "all_themes": "すべてのテーマ",
           "empty": "条件に合う場所がありません。絞り込みを変えてください。", "of": "（全{m}か所中）",
           "clear_one": "「{v}」を解除", "clear_all": "条件をすべて解除", "off_map": "地図にない{n}か所は一覧で"},
    "zh-hans": {"type": "类型", "all": "全部", "filters": "筛选", "view": "查看方式", "list": "列表", "map": "地图", "area": "区域",
                "all_areas": "全部区域", "theme": "主题", "all_themes": "全部主题",
                "empty": "没有符合条件的地点，请更改筛选条件。", "of": "（共{m}个）",
                "clear_one": "取消“{v}”", "clear_all": "清除全部筛选条件", "off_map": "不在地图上的{n}个地点请见列表"},
    "zh-hant": {"type": "類型", "all": "全部", "filters": "篩選", "view": "檢視方式", "list": "列表", "map": "地圖", "area": "區域",
                "all_areas": "全部區域", "theme": "主題", "all_themes": "全部主題",
                "empty": "沒有符合條件的地點，請變更篩選條件。", "of": "（共{m}處）",
                "clear_one": "取消「{v}」", "clear_all": "清除全部篩選條件", "off_map": "不在地圖上的{n}處地點請見列表"},
    "de": {"type": "Art", "all": "Alle", "filters": "Filter", "view": "Ansicht", "list": "Liste", "map": "Karte", "area": "Gebiet",
           "all_areas": "Alle Gebiete", "theme": "Thema", "all_themes": "Alle Themen",
           "empty": "Keine Orte passen zu diesen Filtern. Ändern Sie die Auswahl.", "of": " (von {m})",
           "clear_one": "Filter entfernen: {v}", "clear_all": "Alle Filter zurücksetzen",
           "off_map": "Nicht auf der Karte: {n} (siehe Liste)"},
    "fr": {"type": "Type", "all": "Tous", "filters": "Filtres", "view": "Affichage", "list": "Liste", "map": "Carte",
           "area": "Secteur", "all_areas": "Tous les secteurs", "theme": "Thème", "all_themes": "Tous les thèmes",
           "empty": "Aucun lieu ne correspond à ces filtres. Modifiez-les.", "of": " (sur {m})",
           "clear_one": "Retirer le filtre : {v}", "clear_all": "Effacer tous les filtres",
           "off_map": "Hors de la carte : {n} (voir la liste)"},
    "es": {"type": "Tipo", "all": "Todos", "filters": "Filtros", "view": "Vista", "list": "Lista", "map": "Mapa", "area": "Zona",
           "all_areas": "Todas las zonas", "theme": "Tema", "all_themes": "Todos los temas",
           "empty": "Ningún lugar coincide con estos filtros. Pruebe a cambiarlos.", "of": " (de {m})",
           "clear_one": "Quitar el filtro: {v}", "clear_all": "Quitar todos los filtros",
           "off_map": "Fuera del mapa: {n} (ver la lista)"},
    "ru": {"type": "Тип", "all": "Все", "filters": "Фильтры", "view": "Вид", "list": "Список", "map": "Карта", "area": "Район",
           "all_areas": "Все районы", "theme": "Тема", "all_themes": "Все темы",
           "empty": "Нет мест, подходящих под эти фильтры. Измените их.", "of": " (из {m})",
           "clear_one": "Убрать фильтр: {v}", "clear_all": "Сбросить все фильтры", "off_map": "Нет на карте: {n} (см. список)"},
}


# the course pages (QA 2026-10-15 F09, F09-a/b/c; templates/en/course.html.j2 and _en.html.j2 week()): the closed-day
# grid by weekday, the source's day / option headings and duration, the optional stop, the unlinked stops' map search,
# and the '차 없이 다니기' block (bus stops near the stops, transit directions per leg, the city bus timetable's first
# and last buses), for Korean and every version — hand-written like NEAR_WORDS, so a version never drops out of the
# build for a missing string. A dict value has one form per plural category of the language (course_word picks it);
# a tuple has one entry per weekday (Monday first) or per item. Bus-stop and timetable stop names stay Korean on the
# pages (lang="ko", with their romanization): the words here never carry them.
COURSE_WORDS = {
    "ko": {"closed": "쉬는 날", "closed_day": ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"),
           "closed_n": "{day} 휴무 {n}곳", "wd_short": ("월", "화", "수", "목", "금", "토", "일"),
           "week_title": "{name} 경유지의 요일별 쉬는 날", "place": "장소", "src_col": "쉬는 날(출처 표기)",
           "closed_on": "{day} 휴무", "partial": "일부 주 휴무", "key_closed": "매주 쉬는 요일",
           "key_partial": "격주·특정 주만 쉬는 요일", "key_blank": "빈칸: 쉬는 날로 적히지 않은 요일",
           "key_na": "쉬는 날 자료가 없거나 출처마다 다른 칸", "day": "{n}일차", "day_opt": "{n}일차({k}안)",
           "day_head": "코스 원문 일정", "taketime": "소요시간", "hours_n": "{n}시간", "optional": "선택 경유지",
           "gmaps_search": "구글 지도에서 찾기(검색)", "guide": "가이드: {name}", "map_opt": " · 선택 경유지는 그리지 않음",
           "move_h": "차 없이 다니기", "bus_h": "경유지 근처 버스 정류장", "bus_r": "직선거리 {m}m 안", "stop_word": "정류장",
           "city_bus": "시내버스 {routes}번", "more_bus": "다른 경유지 근처 정류장 ({n})",
           "legs_h": "경유지 사이 대중교통 길찾기", "legs_r": "경로와 시간은 지도 앱이 계산", "transit_link": "대중교통 길찾기",
           "tt_h": "시내버스 첫차·막차", "tt_r": "시간표의 기준 정류장 시각", "bus_no": "시내버스 {no}번", "weekdays": "평일",
           "same_all": "평일·토·일·공휴일 같음", "weekend": "토·일·공휴일", "out": "가는 편", "back": "돌아오는 편",
           "runs": "{n}회", "past_hour": "매시 {m}분", "differ": "{dir} {stop} 시각 출처마다 다름",
           "tt_two": "시간표 {a} · {provider} {b}", "guides_h": "가이드", "routes_more": "다른 노선 {nos}번", "routes_all": "노선 {nos}번", "missing_items": ("구간별 이동 시간", "총 소요 시간"),
           "src_bus": "정류장·거리: {stops} · 노선 번호: {tt}", "src_times": "시각: {name} — {provider}",
           "src_dir": "길찾기: 지도 앱"},
    "en": {"closed": "Closed days",
           "closed_day": ("Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"),
           "closed_n": {"one": "{n} stop closed on {day}", "other": "{n} stops closed on {day}"},
           "wd_short": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
           "week_title": "{name}: closed days of the stops by weekday", "place": "Place", "src_col": "Closed days as listed",
           "closed_on": "closed on {day}", "partial": "closed in some weeks only", "key_closed": "Closed every week",
           "key_partial": "Closed in some weeks only (every other week or given weeks)",
           "key_blank": "Blank: not listed as a closed day", "key_na": "No closed-day data, or the sources differ",
           "day": "Day {n}", "day_opt": "Day {n}, option {k}", "day_head": "Itinerary", "taketime": "Time needed",
           "hours_n": {"one": "{n} hour", "other": "{n} hours"}, "optional": "Optional stop",
           "gmaps_search": "Search on Google Maps", "guide": "Guide: {name}", "map_opt": " · the optional stop is not drawn",
           "move_h": "Getting around without a car", "bus_h": "Bus stops near the stops", "bus_r": "straight line, within {m} m",
           "stop_word": "stop", "city_bus": "city bus {routes}", "more_bus": "Bus stops near the other stops ({n})",
           "legs_h": "Public transport between stops", "legs_r": "Google Maps works out the route and the time",
           "transit_link": "Public transport directions (Google Maps)", "tt_h": "First and last city buses",
           "tt_r": "times at the reference stops of the timetable", "bus_no": "City bus {no}", "weekdays": "Weekdays",
           "same_all": "Weekdays, Saturdays, Sundays and holidays alike", "weekend": "Saturdays, Sundays and holidays",
           "out": "outbound", "back": "return", "runs": {"one": "{n} run", "other": "{n} runs"},
           "past_hour": "at :{m} every hour", "differ": "{dir} {stop}: sources differ",
           "tt_two": "timetable {a} · {provider} {b}", "guides_h": "Guides", "routes_more": "Other routes: {nos}", "routes_all": "Routes: {nos}",
           "missing_items": ("travel time per leg", "total time"),
           "src_bus": "Bus stops and distances: {stops} · route numbers: {tt}",
           "src_times": "Times: {name} — {provider}", "src_dir": "Directions: Google Maps"},
    "ja": {"closed": "休業日", "closed_day": ("月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"),
           "closed_n": "{day}休み {n}か所", "wd_short": ("月", "火", "水", "木", "金", "土", "日"),
           "week_title": "{name}：立ち寄り先の曜日別の休業日", "place": "場所", "src_col": "休業日（出典の表記）",
           "closed_on": "{day}休み", "partial": "一部の週のみ休み", "key_closed": "毎週休み",
           "key_partial": "隔週・特定の週のみ休み", "key_blank": "空欄：休業日として記載のない曜日",
           "key_na": "休業日の情報がない、または出典により異なる", "day": "{n}日目", "day_opt": "{n}日目（{k}案）",
           "day_head": "日程", "taketime": "所要時間", "hours_n": "{n}時間", "optional": "任意の立ち寄り先",
           "gmaps_search": "Googleマップで検索", "guide": "ガイド：{name}", "map_opt": "・任意の立ち寄り先は地図に描いていません",
           "move_h": "車なしで回る", "bus_h": "立ち寄り先近くのバス停", "bus_r": "直線距離{m} m以内", "stop_word": "バス停",
           "city_bus": "市内バス{routes}番", "more_bus": "ほかの立ち寄り先近くのバス停（{n}）",
           "legs_h": "立ち寄り先間の公共交通ルート", "legs_r": "経路と所要時間はGoogleマップが計算",
           "transit_link": "公共交通ルート（Googleマップ）", "tt_h": "市内バスの始発・終発", "tt_r": "時刻表の基準停留所の時刻",
           "bus_no": "市内バス{no}番", "weekdays": "平日", "same_all": "平日・土日祝日とも同じ", "weekend": "土日祝日",
           "out": "往路", "back": "復路", "runs": "{n}本", "past_hour": "毎時{m}分", "differ": "{dir}{stop}：出典により異なる",
           "tt_two": "時刻表 {a}・{provider} {b}", "guides_h": "ガイド", "routes_more": "ほかの路線：{nos}番", "routes_all": "路線：{nos}番", "missing_items": ("区間ごとの所要時間", "全体の所要時間"),
           "src_bus": "バス停と距離：{stops}、路線番号：{tt}", "src_times": "時刻：{name}（{provider}）",
           "src_dir": "ルート：Googleマップ"},
    "zh-hans": {"closed": "休息日", "closed_day": ("周一", "周二", "周三", "周四", "周五", "周六", "周日"),
                "closed_n": "{day}休息 {n}处", "wd_short": ("一", "二", "三", "四", "五", "六", "日"),
                "week_title": "{name}：各途经地按星期的休息日", "place": "地点", "src_col": "休息日（来源原文）",
                "closed_on": "{day}休息", "partial": "仅部分周休息", "key_closed": "每周休息", "key_partial": "隔周或特定周休息",
                "key_blank": "空白：未列为休息日", "key_na": "无休息日资料或来源不一致", "day": "第{n}天",
                "day_opt": "第{n}天（方案{k}）", "day_head": "行程", "taketime": "所需时间", "hours_n": "{n}小时",
                "optional": "可选途经地", "gmaps_search": "在 Google 地图中搜索", "guide": "指南：{name}",
                "map_opt": " · 可选途经地未画出", "move_h": "无车出行", "bus_h": "途经地附近的公交站", "bus_r": "直线{m} m以内",
                "stop_word": "站", "city_bus": "市内公交{routes}路", "more_bus": "其他途经地附近的公交站（{n}）",
                "legs_h": "途经地之间的公共交通路线", "legs_r": "路线和时间由 Google 地图计算",
                "transit_link": "公共交通路线（Google 地图）", "tt_h": "市内公交首末班车", "tt_r": "时刻表基准站的时刻",
                "bus_no": "市内公交{no}路", "weekdays": "工作日", "same_all": "工作日与周六、周日、节假日相同",
                "weekend": "周六、周日、节假日", "out": "去程", "back": "返程", "runs": "{n}班", "past_hour": "每小时{m}分",
                "differ": "{dir}{stop}：来源不一致", "tt_two": "时刻表{a} · {provider}{b}", "guides_h": "指南", "routes_more": "其他线路：{nos}路", "routes_all": "线路：{nos}路",
                "missing_items": ("各路段所需时间", "总所需时间"), "src_bus": "公交站与距离：{stops}；线路号：{tt}",
                "src_times": "时刻：{name}（{provider}）", "src_dir": "路线：Google 地图"},
    "zh-hant": {"closed": "休息日", "closed_day": ("週一", "週二", "週三", "週四", "週五", "週六", "週日"),
                "closed_n": "{day}休息 {n}處", "wd_short": ("一", "二", "三", "四", "五", "六", "日"),
                "week_title": "{name}：各途經地依星期的休息日", "place": "地點", "src_col": "休息日（來源原文）",
                "closed_on": "{day}休息", "partial": "僅部分週休息", "key_closed": "每週休息", "key_partial": "隔週或特定週休息",
                "key_blank": "空白：未列為休息日", "key_na": "無休息日資料或來源不一致", "day": "第{n}天",
                "day_opt": "第{n}天（方案{k}）", "day_head": "行程", "taketime": "所需時間", "hours_n": "{n}小時",
                "optional": "可選途經地", "gmaps_search": "在 Google 地圖搜尋", "guide": "指南：{name}",
                "map_opt": " · 可選途經地未畫出", "move_h": "無車出行", "bus_h": "途經地附近的公車站", "bus_r": "直線{m} m以內",
                "stop_word": "站", "city_bus": "市區公車{routes}路", "more_bus": "其他途經地附近的公車站（{n}）",
                "legs_h": "途經地之間的大眾運輸路線", "legs_r": "路線與時間由 Google 地圖計算",
                "transit_link": "大眾運輸路線（Google 地圖）", "tt_h": "市區公車首末班車", "tt_r": "時刻表基準站的時刻",
                "bus_no": "市區公車{no}路", "weekdays": "平日", "same_all": "平日與週六、週日、假日相同",
                "weekend": "週六、週日、假日", "out": "去程", "back": "回程", "runs": "{n}班", "past_hour": "每小時{m}分",
                "differ": "{dir}{stop}：來源不一致", "tt_two": "時刻表{a} · {provider}{b}", "guides_h": "指南", "routes_more": "其他路線：{nos}路", "routes_all": "路線：{nos}路",
                "missing_items": ("各路段所需時間", "總所需時間"), "src_bus": "公車站與距離：{stops}；路線號：{tt}",
                "src_times": "時刻：{name}（{provider}）", "src_dir": "路線：Google 地圖"},
    "de": {"closed": "Ruhetage",
           "closed_day": ("montags", "dienstags", "mittwochs", "donnerstags", "freitags", "samstags", "sonntags"),
           "closed_n": {"one": "{n} Station {day} geschlossen", "other": "{n} Stationen {day} geschlossen"},
           "wd_short": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
           "week_title": "{name}: Ruhetage der Stationen nach Wochentag", "place": "Ort", "src_col": "Ruhetage laut Quelle",
           "closed_on": "{day} geschlossen", "partial": "nur in manchen Wochen geschlossen",
           "key_closed": "Jede Woche geschlossen",
           "key_partial": "Nur in manchen Wochen geschlossen (jede zweite oder bestimmte Wochen)",
           "key_blank": "Leer: nicht als Ruhetag angegeben",
           "key_na": "Keine Angaben zu Ruhetagen oder die Quellen widersprechen sich", "day": "Tag {n}",
           "day_opt": "Tag {n}, Variante {k}", "day_head": "Tagesplan", "taketime": "Zeitbedarf",
           "hours_n": {"one": "{n} Stunde", "other": "{n} Stunden"}, "optional": "Optionale Station",
           "gmaps_search": "In Google Maps suchen", "guide": "Ratgeber: {name}",
           "map_opt": " · die optionale Station ist nicht eingezeichnet", "move_h": "Unterwegs ohne Auto",
           "bus_h": "Bushaltestellen bei den Stationen", "bus_r": "Luftlinie, bis {m} m", "stop_word": "Haltestelle",
           "city_bus": "Stadtbus {routes}", "more_bus": "Haltestellen bei den anderen Stationen ({n})",
           "legs_h": "Mit öffentlichen Verkehrsmitteln zwischen den Stationen",
           "legs_r": "Route und Fahrzeit berechnet Google Maps", "transit_link": "Route mit Bus und Bahn (Google Maps)",
           "tt_h": "Erste und letzte Stadtbusse", "tt_r": "Zeiten an den Bezugshaltestellen des Fahrplans",
           "bus_no": "Stadtbus {no}", "weekdays": "Montag bis Freitag",
           "same_all": "Montag bis Freitag, Samstag, Sonntag und Feiertage gleich",
           "weekend": "Samstag, Sonntag und Feiertage", "out": "Hinfahrt", "back": "Rückfahrt",
           "runs": {"one": "{n} Fahrt", "other": "{n} Fahrten"}, "past_hour": "stündlich um :{m}",
           "differ": "{dir} {stop}: die Quellen widersprechen sich", "tt_two": "Fahrplan {a} · {provider} {b}",
           "guides_h": "Ratgeber", "routes_more": "Weitere Linien: {nos}", "routes_all": "Linien: {nos}", "missing_items": ("Fahrzeit je Abschnitt", "Gesamtdauer"),
           "src_bus": "Haltestellen und Entfernungen: {stops} · Liniennummern: {tt}",
           "src_times": "Zeiten: {name} — {provider}", "src_dir": "Routen: Google Maps"},
    "fr": {"closed": "Jours de fermeture",
           "closed_day": ("le lundi", "le mardi", "le mercredi", "le jeudi", "le vendredi", "le samedi", "le dimanche"),
           "closed_n": {"one": "{n} étape fermée {day}", "other": "{n} étapes fermées {day}"},
           "wd_short": ("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."),
           "week_title": "{name} : jours de fermeture des étapes par jour de la semaine", "place": "Lieu",
           "src_col": "Jours de fermeture selon la source", "closed_on": "fermé le {day}",
           "partial": "fermé certaines semaines seulement", "key_closed": "Fermé chaque semaine",
           "key_partial": "Fermé certaines semaines seulement (une semaine sur deux ou des semaines précises)",
           "key_blank": "Case vide : pas indiqué comme jour de fermeture",
           "key_na": "Pas de données de fermeture, ou les sources divergent", "day": "Jour {n}",
           "day_opt": "Jour {n}, option {k}", "day_head": "Programme", "taketime": "Durée",
           "hours_n": {"one": "{n} heure", "other": "{n} heures"}, "optional": "Étape facultative",
           "gmaps_search": "Rechercher sur Google Maps", "guide": "Guide : {name}",
           "map_opt": " · l'étape facultative n'est pas tracée", "move_h": "Se déplacer sans voiture",
           "bus_h": "Arrêts de bus près des étapes", "bus_r": "à vol d'oiseau, moins de {m} m", "stop_word": "arrêt",
           "city_bus": "bus urbain {routes}", "more_bus": "Arrêts près des autres étapes ({n})",
           "legs_h": "Transports en commun entre les étapes", "legs_r": "Google Maps calcule l'itinéraire et la durée",
           "transit_link": "Itinéraire en transports en commun (Google Maps)", "tt_h": "Premiers et derniers bus urbains",
           "tt_r": "horaires aux arrêts de référence de la grille", "bus_no": "Bus urbain {no}",
           "weekdays": "Du lundi au vendredi",
           "same_all": "Identique du lundi au vendredi, le samedi, le dimanche et les jours fériés",
           "weekend": "Samedi, dimanche et jours fériés", "out": "aller", "back": "retour",
           "runs": {"one": "{n} départ", "other": "{n} départs"}, "past_hour": "toutes les heures à :{m}",
           "differ": "{dir} {stop} : les sources divergent", "tt_two": "grille {a} · {provider} {b}", "guides_h": "Guides", "routes_more": "Autres lignes : {nos}",
           "routes_all": "Lignes : {nos}",
           "missing_items": ("durée de chaque trajet", "durée totale"),
           "src_bus": "Arrêts et distances : {stops} · numéros de ligne : {tt}",
           "src_times": "Horaires : {name} — {provider}", "src_dir": "Itinéraires : Google Maps"},
    "es": {"closed": "Días de cierre",
           "closed_day": ("los lunes", "los martes", "los miércoles", "los jueves", "los viernes", "los sábados",
                          "los domingos"),
           "closed_n": {"one": "{n} parada cierra {day}", "other": "{n} paradas cierran {day}"},
           "wd_short": ("lun.", "mar.", "mié.", "jue.", "vie.", "sáb.", "dom."),
           "week_title": "{name}: días de cierre de las paradas por día de la semana", "place": "Lugar",
           "src_col": "Días de cierre según la fuente", "closed_on": "cierra el {day}", "partial": "cierra solo algunas semanas",
           "key_closed": "Cierra todas las semanas", "key_partial": "Cierra solo algunas semanas (semanas alternas o concretas)",
           "key_blank": "En blanco: no figura como día de cierre", "key_na": "Sin datos de cierre, o las fuentes difieren",
           "day": "Día {n}", "day_opt": "Día {n}, opción {k}", "day_head": "Programa", "taketime": "Duración",
           "hours_n": {"one": "{n} hora", "other": "{n} horas"}, "optional": "Parada opcional",
           "gmaps_search": "Buscar en Google Maps", "guide": "Guía: {name}", "map_opt": " · la parada opcional no se dibuja",
           "move_h": "Moverse sin coche", "bus_h": "Paradas de autobús cerca de las paradas de la ruta",
           "bus_r": "en línea recta, a menos de {m} m", "stop_word": "parada", "city_bus": "autobús urbano {routes}",
           "more_bus": "Paradas cerca de las demás paradas de la ruta ({n})", "legs_h": "Transporte público entre las paradas",
           "legs_r": "Google Maps calcula el recorrido y el tiempo",
           "transit_link": "Cómo llegar en transporte público (Google Maps)", "tt_h": "Primeros y últimos autobuses urbanos",
           "tt_r": "horas en las paradas de referencia del horario", "bus_no": "Autobús urbano {no}",
           "weekdays": "De lunes a viernes", "same_all": "Igual de lunes a viernes, sábados, domingos y festivos",
           "weekend": "Sábados, domingos y festivos", "out": "ida", "back": "vuelta",
           "runs": {"one": "{n} salida", "other": "{n} salidas"}, "past_hour": "cada hora a las :{m}",
           "differ": "{dir} {stop}: las fuentes difieren", "tt_two": "horario {a} · {provider} {b}", "guides_h": "Guías", "routes_more": "Otras líneas: {nos}", "routes_all": "Líneas: {nos}",
           "missing_items": ("tiempo de cada tramo", "tiempo total"),
           "src_bus": "Paradas y distancias: {stops} · números de línea: {tt}",
           "src_times": "Horas: {name} — {provider}", "src_dir": "Rutas: Google Maps"},
    "ru": {"closed": "Выходные дни",
           "closed_day": ("по понедельникам", "по вторникам", "по средам", "по четвергам", "по пятницам", "по субботам",
                          "по воскресеньям"),
           "closed_n": {"one": "{n} остановка закрыта {day}", "few": "{n} остановки закрыты {day}",
                        "many": "{n} остановок закрыты {day}"},
           "wd_short": ("пн", "вт", "ср", "чт", "пт", "сб", "вс"),
           "week_title": "{name}: выходные дни остановок по дням недели", "place": "Место",
           "src_col": "Выходные дни по источнику", "closed_on": "закрыто: {day}",
           "partial": "закрыто только в некоторые недели", "key_closed": "Закрыто каждую неделю",
           "key_partial": "Закрыто только в некоторые недели (через неделю или в определённые недели)",
           "key_blank": "Пусто: не указан как выходной", "key_na": "Нет данных о выходных или источники расходятся",
           "day": "День {n}", "day_opt": "День {n}, вариант {k}", "day_head": "Программа", "taketime": "Продолжительность",
           "hours_n": {"one": "{n} час", "few": "{n} часа", "many": "{n} часов"}, "optional": "Необязательная остановка",
           "gmaps_search": "Найти в Google Картах", "guide": "Путеводитель: {name}",
           "map_opt": " · необязательная остановка на карте не показана", "move_h": "Без машины",
           "bus_h": "Автобусные остановки рядом с местами маршрута", "bus_r": "по прямой, до {m} м",
           "stop_word": "остановка", "city_bus": "городской автобус {routes}",
           "more_bus": "Остановки рядом с другими местами маршрута ({n})",
           "legs_h": "Общественный транспорт между остановками маршрута",
           "legs_r": "маршрут и время рассчитывают Google Карты",
           "transit_link": "Маршрут на общественном транспорте (Google Карты)",
           "tt_h": "Первые и последние городские автобусы", "tt_r": "время на опорных остановках расписания",
           "bus_no": "Городской автобус {no}", "weekdays": "Будни",
           "same_all": "Одинаково в будни, субботу, воскресенье и праздники", "weekend": "Суббота, воскресенье и праздники",
           "out": "туда", "back": "обратно", "runs": {"one": "{n} рейс", "few": "{n} рейса", "many": "{n} рейсов"},
           "past_hour": "каждый час в :{m}", "differ": "{dir} {stop}: источники расходятся",
           "tt_two": "расписание {a} · {provider} {b}", "guides_h": "Путеводители", "routes_more": "Другие маршруты: {nos}",
           "routes_all": "Маршруты: {nos}",
           "missing_items": ("время в пути на каждом участке", "общее время"),
           "src_bus": "Остановки и расстояния: {stops} · номера маршрутов: {tt}",
           "src_times": "Время: {name} — {provider}", "src_dir": "Маршруты: Google Карты"},
}


def course_word(code: str, key: str, n: int | None = None, **kw) -> str:
    """COURSE_WORDS[code][key] filled in: a plural dict takes the form of n in the language (Korean has none)."""
    v = COURSE_WORDS[code][key]
    if isinstance(v, dict):
        v = v[LOCALES[code].plural_form(int(n or 0))]
    return v.format(n=n, **kw) if isinstance(v, str) else v


# 예약하기 (step 1, 2026-10-16; pipeline/booking.py, templates/_ui.html.j2 book()): the button word, the guide and course
# box's heading, the one note under the buttons, the page-nav link, the about pages' sentence and the names of the
# booking services of data/<region>/booking.json, for Korean and every version — hand-written like NEAR_WORDS, so a
# version never drops out of the build for a missing string. The chat's link cards name a booking link with 'book'
# (templates/assets/chat.js STR kinds.book: the same words — tests/test_booking.py).
BOOK_WORDS = {
    "ko": {"book": "예약하기", "box": "예약·예매", "nav": "예약",
           "note": "공식 예약 페이지로 이동합니다. 이 사이트는 예약을 받지 않습니다.",
           "about": "이 사이트는 예약·결제를 받지 않습니다. 장소·가이드·코스 페이지의 '예약하기' 버튼은 데이터에 있는 공식 예약 "
                    "페이지(시설이나 공공기관이 운영하는 곳)로만 이어지고, 여행사·숙박 예약 앱의 링크는 버튼으로 만들지 않습니다.",
           "svc": {"bus": "버스타고 시외버스", "rail": "코레일", "ferry": "한국해운조합 여객선", "forest": "산림청 숲나들e"}},
    "en": {"book": "Book", "box": "Booking and tickets", "nav": "Booking",
           "note": "Opens the official site. This site takes no bookings.",
           "about": "This site takes no bookings or payments. The ‘Book’ buttons on place, guide and course pages open only "
                    "the official booking pages in our data (run by the facility or a public body); links of travel "
                    "agencies and booking apps never become buttons.",
           "svc": {"bus": "Bustago intercity buses", "rail": "Korail", "ferry": "Korea Shipping Association ferries", "forest": "Sumnadeul-e, Korea Forest Service"}},
    "ja": {"book": "予約する", "box": "予約・チケット", "nav": "予約",
           "note": "公式サイトが開きます（このサイトでは予約不可）。",
           "about": "このサイトは予約や支払いを受け付けません。スポット・ガイド・コースのページの「予約する」ボタンは、データにある"
                    "公式の予約ページ（施設や公的機関が運営するもの）だけにつながり、旅行会社や宿泊予約アプリのリンクはボタンにしません。",
           "svc": {"bus": "バスタゴ 市外バス", "rail": "KORAIL 韓国鉄道公社", "ferry": "韓国海運組合 旅客船", "forest": "山林庁 スプナドゥルe"}},
    "zh-hans": {"book": "预订", "box": "预订与购票", "nav": "预订",
                "note": "将打开官方预订网站。本网站不接受预订。",
                "about": "本网站不接受预订或付款。景点、指南和路线页面上的“预订”按钮只链接到资料中的官方预订页面（由设施或公共机构运营），"
                         "旅行社和住宿预订应用的链接不会做成按钮。",
                "svc": {"bus": "Bustago 市外巴士", "rail": "KORAIL 韩国铁道公社", "ferry": "韩国海运组合 客轮", "forest": "山林厅 Sumnadeul-e"}},
    "zh-hant": {"book": "預訂", "box": "預訂與購票", "nav": "預訂",
                "note": "將開啟官方預訂網站。本網站不接受預訂。",
                "about": "本網站不接受預訂或付款。景點、指南和路線頁面上的「預訂」按鈕只連結到資料中的官方預訂頁面（由設施或公共機構營運），"
                         "旅行社和住宿預訂應用程式的連結不會做成按鈕。",
                "svc": {"bus": "BusTago 市外巴士", "rail": "KORAIL 韓國鐵道公社", "ferry": "韓國海運組合 客輪", "forest": "山林廳 Sumnadeul-e"}},
    "de": {"book": "Buchen", "box": "Buchung und Tickets", "nav": "Buchung",
           "note": "Zur offiziellen Seite. Diese Website bucht nicht.",
           "about": "Diese Website nimmt keine Buchungen oder Zahlungen an. Die Schaltflächen „Buchen“ auf den Seiten zu Orten, "
                    "Reiseführern und Routen öffnen nur die offiziellen Buchungsseiten aus unseren Daten (betrieben von der "
                    "Einrichtung oder einer öffentlichen Stelle); Links von Reisebüros und Buchungs-Apps werden nie zu Schaltflächen.",
           "svc": {"bus": "Bustago Überlandbusse", "rail": "Korail",
                   "ferry": "Fähren des Koreanischen Schifffahrtsverbands",
                   "forest": "Sumnadeul-e der Koreanischen Forstverwaltung"}},
    "fr": {"book": "Réserver", "box": "Réservations et billets", "nav": "Réservation",
           "note": "Ouvre le site officiel. Ce site ne réserve pas.",
           "about": "Ce site ne prend ni réservation ni paiement. Les boutons « Réserver » des pages de lieux, de guides et de "
                    "circuits ouvrent uniquement les pages de réservation officielles de nos données (gérées par "
                    "l’établissement ou un organisme public) ; les liens des agences de voyage et des applications de "
                    "réservation ne deviennent jamais des boutons.",
           "svc": {"bus": "Bustago, bus interurbains", "rail": "Korail",
                   "ferry": "Ferries de l’Association coréenne des transports maritimes", "forest": "Sumnadeul-e, Service forestier coréen"}},
    "es": {"book": "Reservar", "box": "Reservas y billetes", "nav": "Reservas",
           "note": "Abre la web oficial. Aquí no se reserva.",
           "about": "Este sitio no acepta reservas ni pagos. Los botones «Reservar» de las páginas de lugares, guías y rutas "
                    "solo abren las páginas oficiales de reserva de nuestros datos (gestionadas por el establecimiento o un "
                    "organismo público); los enlaces de agencias de viajes y aplicaciones de reserva nunca se convierten en botones.",
           "svc": {"bus": "Bustago, autobuses interurbanos", "rail": "Korail",
                   "ferry": "Ferris de la Asociación Naviera de Corea",
                   "forest": "Sumnadeul-e, Servicio Forestal de Corea"}},
    "ru": {"book": "Забронировать", "box": "Бронирование и билеты", "nav": "Бронирование",
           "note": "Откроется официальный сайт. Здесь не бронируют.",
           "about": "Этот сайт не принимает бронирования и оплату. Кнопки «Забронировать» на страницах мест, путеводителей и "
                    "маршрутов открывают только официальные страницы бронирования из наших данных (их ведёт само заведение "
                    "или государственная организация); ссылки турагентств и приложений бронирования никогда не становятся кнопками.",
           "svc": {"bus": "Bustago — междугородние автобусы", "rail": "Korail",
                   "ferry": "Паромы Корейской ассоциации судоходства",
                   "forest": "«Сумнадыль-е» Лесной службы Кореи"}},
}

# 공유 (operator 2026-10-17, ui.lnav's share button on place, guide, course and event pages): the button's word, and the
# short note after the link was copied (a screen without the phone's share sheet) or could not be
SHARE_WORDS = {
    "ko": {"label": "공유", "copied": "링크를 복사했습니다", "failed": "링크를 복사하지 못했습니다"},
    "en": {"label": "Share", "copied": "Link copied", "failed": "Couldn't copy the link"},
    "ja": {"label": "共有", "copied": "リンクをコピーしました", "failed": "リンクをコピーできませんでした"},
    "zh-hans": {"label": "分享", "copied": "链接已复制", "failed": "无法复制链接"},
    "zh-hant": {"label": "分享", "copied": "已複製連結", "failed": "無法複製連結"},
    "de": {"label": "Teilen", "copied": "Link kopiert", "failed": "Link konnte nicht kopiert werden"},
    "fr": {"label": "Partager", "copied": "Lien copié", "failed": "Impossible de copier le lien"},
    "es": {"label": "Compartir", "copied": "Enlace copiado", "failed": "No se pudo copiar el enlace"},
    "ru": {"label": "Поделиться", "copied": "Ссылка скопирована", "failed": "Не удалось скопировать ссылку"},
}
