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
    site_name: str
    city: str            # Gunsan in this language
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
        """'430 m' (rounded to 10 m), '2.4 km' / '2,4 km'; '' for unknown."""
        if m is None:
            return ""
        m = float(m)
        if m < 10:
            return "0 m"
        return f"{int(round(m / 10) * 10)} m" if m < 1000 else f"{m / 1000:.1f}".replace(".", self.dec) + " km"

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

    def md(self, iso: str | None) -> str:
        """A short month-day ('Oct 9', '10月9日', '9. Okt.')."""
        try:
            d = dt.date.fromisoformat(str(iso or "")[:10])
        except ValueError:
            return re.sub(r"\s+", " ", str(iso or "")).strip()
        if self.code == "en":
            return f"{d.strftime('%b')} {d.day}"
        return self.extra["md"].format(m=d.month, d=d.day, mo=self.months_short[d.month - 1])

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
    "en": Locale("en", "en", "en", "en_US", "English", "English", "All About Gunsan Travel", "Gunsan", "EngService2",
                 weekdays=("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
                 conflict="Sources differ — call before visiting",
                 event_conflict="Sources differ — check with the organizer before visiting", money_word="won",
                 abbr=("No", "Dr", "Mt", "St", "Mr", "Ms", "Jr", "vs", "approx", "Ave"),
                 art_alt="Illustration: "),
    "ja": Locale("ja", "ja", "ja", "ja_JP", "日本語", "Japanese", "群山旅行のすべて", "群山", "JpnService2", cjk=True,
                 title_max=40, desc_max=110, sent_max=80, plural=("other",),
                 weekdays=("月曜日", "火曜日", "水曜日", "木曜日", "金曜日", "土曜日", "日曜日"),
                 weekdays_short=("月", "火", "水", "木", "金", "土", "日"),
                 months=tuple(f"{i}月" for i in range(1, 13)), months_short=tuple(f"{i}月" for i in range(1, 13)),
                 conflict="情報源によって値が異なります。訪問前に電話でご確認ください",
                 event_conflict="情報源によって値が異なります。訪問前に電話でご確認ください", money_word="ウォン",
                 promo=("必見", "絶対", "最高", "人気", "有名", "おすすめ", "オススメ", "お勧め", "お薦め", "話題"),
                 disclaimers=("参考程度", "変更される場合があります", "変更になる場合があります", "責任を負いかねます", "免責"),
                 free="無料", colon="：", list_sep="、", sjoin="",
                 art_alt="イラスト：",
                 extra={"date": "{y}年{m}月{d}日（{wd}）", "md": "{m}月{d}日", "lang_word": "言語"}),
    "zh-hans": Locale("zh-hans", "zh_hans", "zh-Hans", "zh_CN", "中文(简体)", "Simplified Chinese", "群山旅游全攻略",
                      "群山", "ChsService2", cjk=True, title_max=40, desc_max=110, sent_max=70, plural=("other",),
                      weekdays=("周一", "周二", "周三", "周四", "周五", "周六", "周日"),
                      weekdays_short=("周一", "周二", "周三", "周四", "周五", "周六", "周日"),
                      months=tuple(f"{i}月" for i in range(1, 13)), months_short=tuple(f"{i}月" for i in range(1, 13)),
                      conflict="不同来源的信息不一致，请出发前致电确认",
                      event_conflict="不同来源的信息不一致，请出发前致电确认", money_word="韩元",
                      promo=("必去", "必游", "最好", "最佳", "著名", "热门", "网红", "推荐", "人气"),
                      disclaimers=("仅供参考", "如有变动", "以实际为准", "概不负责", "免责声明"),
                      free="免费", colon="：", list_sep="、", sjoin="",
                      art_alt="插图：",
                      extra={"date": "{y}年{m}月{d}日（{wd}）", "md": "{m}月{d}日", "lang_word": "语言"}),
    "zh-hant": Locale("zh-hant", "zh_hant", "zh-Hant", "zh_TW", "中文(繁體)", "Traditional Chinese", "群山旅遊全攻略",
                      "群山", "ChtService2", cjk=True, title_max=40, desc_max=110, sent_max=70, plural=("other",),
                      weekdays=("週一", "週二", "週三", "週四", "週五", "週六", "週日"),
                      weekdays_short=("週一", "週二", "週三", "週四", "週五", "週六", "週日"),
                      months=tuple(f"{i}月" for i in range(1, 13)), months_short=tuple(f"{i}月" for i in range(1, 13)),
                      conflict="不同來源的資訊不一致，請出發前致電確認",
                      event_conflict="不同來源的資訊不一致，請出發前致電確認", money_word="韓元",
                      promo=("必去", "必遊", "最好", "最佳", "著名", "熱門", "網紅", "推薦", "人氣"),
                      disclaimers=("僅供參考", "如有變動", "以實際為準", "概不負責", "免責聲明"),
                      free="免費", colon="：", list_sep="、", sjoin="",
                      art_alt="插圖：",
                      extra={"date": "{y}年{m}月{d}日（{wd}）", "md": "{m}月{d}日", "lang_word": "語言"}),
    "de": Locale("de", "de", "de", "de_DE", "Deutsch", "German", "Alles über Gunsan", "Gunsan", "GerService2",
                 dec=",", grp=".", weekdays=_DE_WD, weekdays_short=("Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So."),
                 months=("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
                         "November", "Dezember"),
                 months_short=("Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sept.", "Okt.", "Nov.",
                               "Dez."),
                 conflict="Die Quellen nennen unterschiedliche Angaben – bitte vor dem Besuch anrufen.",
                 event_conflict="Die Quellen nennen unterschiedliche Angaben – bitte vor dem Besuch anrufen.",
                 money_word="Won", promo=("unbedingt", "Geheimtipp", "berühmt", "beliebt", "beste", "Muss"),
                 disclaimers=("ohne Gewähr", "Änderungen vorbehalten", "keine Haftung", "Haftungsausschluss",
                              "unverbindlich"),
                 free=r"kostenlos|gratis|Eintritt frei|eintrittsfrei|frei(?:er)? Eintritt|gebührenfrei",
                 abbr=("Nr", "z", "B", "ca", "bzw", "Str", "St", "Dr", "usw", "inkl", "evtl", "u", "a", "Tel"),
                 art_alt="Illustration: ",
                 extra={"date": "{d}. {mo} {y} ({wd})", "md": "{d}. {mo}", "lang_word": "Sprache"}),
    "fr": Locale("fr", "fr", "fr", "fr_FR", "Français", "French", "Tout sur Gunsan", "Gunsan", "FreService2",
                 dec=",", grp=NNBSP,
                 weekdays=("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"),
                 weekdays_short=("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."),
                 months=("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
                         "octobre", "novembre", "décembre"),
                 months_short=("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.",
                               "nov.", "déc."),
                 conflict="Les sources indiquent des valeurs différentes : appelez avant votre visite.",
                 event_conflict="Les sources indiquent des valeurs différentes : appelez avant votre visite.",
                 money_word="wons", promo=("incontournable", "célèbre", "populaire", "meilleur", "à ne pas manquer"),
                 disclaimers=("sous réserve", "à titre indicatif", "susceptible de changer",
                              "décline toute responsabilité", "avertissement"),
                 free=r"gratuit(?:e|s|es)?|entrée libre", colon=" : ",
                 abbr=("M", "Mme", "St", "Ste", "av", "bd", "env", "n°", "tél", "p. ex"),
                 art_alt="Illustration : ",
                 extra={"date": "{d} {mo} {y} ({wd})", "md": "{d} {mo}", "lang_word": "Langue"}),
    "es": Locale("es", "es", "es", "es_ES", "Español", "Spanish", "Todo sobre Gunsan", "Gunsan", "SpnService2",
                 dec=",", grp=".",
                 weekdays=("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"),
                 weekdays_short=("lun.", "mar.", "mié.", "jue.", "vie.", "sáb.", "dom."),
                 months=("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                         "octubre", "noviembre", "diciembre"),
                 months_short=("ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sept.", "oct.",
                               "nov.", "dic."),
                 conflict="Las fuentes indican datos distintos: llame antes de su visita.",
                 event_conflict="Las fuentes indican datos distintos: llame antes de su visita.",
                 money_word="wones", promo=("imprescindible", "famoso", "popular", "mejor", "no te puedes perder"),
                 disclaimers=("sujeto a cambios", "a título informativo", "no nos hacemos responsables",
                              "descargo de responsabilidad"),
                 free=r"gratis|gratuit[oa]s?|entrada libre",
                 abbr=("Sr", "Sra", "Dr", "Dra", "av", "Avda", "núm", "aprox", "tel", "p. ej"),
                 art_alt="Ilustración: ",
                 extra={"date": "{d} de {mo} de {y} ({wd})", "md": "{d} {mo}", "lang_word": "Idioma"}),
    "ru": Locale("ru", "ru", "ru", "ru_RU", "Русский", "Russian", "Всё о Кунсане", "Кунсан", "RusService2",
                 dec=",", grp=NNBSP, plural=("one", "few", "many"),
                 weekdays=("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"),
                 weekdays_short=("пн", "вт", "ср", "чт", "пт", "сб", "вс"),
                 months=("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
                         "октября", "ноября", "декабря"),
                 months_short=("янв.", "февр.", "марта", "апр.", "мая", "июня", "июля", "авг.", "сент.", "окт.",
                               "нояб.", "дек."),
                 conflict="Источники расходятся — позвоните перед визитом.",
                 event_conflict="Источники расходятся — позвоните перед визитом.",
                 money_word="вон", promo=("обязательно", "знаменитый", "популярный", "лучший"),
                 disclaimers=("может измениться", "носит справочный характер", "не несём ответственности",
                              "не несем ответственности", "отказ от ответственности"),
                 free=r"бесплатн\w*",
                 abbr=("г", "ул", "д", "т", "е", "др", "им", "ок", "мин", "пр", "просп", "тел", "руб"),
                 art_alt="Иллюстрация: ",
                 extra={"date": "{d} {mo} {y} г. ({wd})", "md": "{d} {mo}", "lang_word": "Язык"}),
}
CODES = tuple(LOCALES)


def get(code: str) -> Locale:
    return LOCALES[code.lower()]


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
           "están", "pero", "hay", "puede", "también", "muy", "como"},
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
    """Cyrillic for a Korean name by the Kontsevich system ('군산' -> 'Кунсан', '경암동' -> 'Кёнам-дон'): each
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
