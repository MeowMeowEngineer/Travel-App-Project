"""Pretendard 글꼴을 이 사이트용 unicode-range 조각(다이내믹 서브셋)으로 나눈다.

    npm pack pretendard@1.3.9 --ignore-scripts      # 저장소 밖 임시 폴더에서 받고 압축을 푼다
    python tools/build_public.py --out /tmp/prod     # 공개(production) 빌드: 방문자가 보는 페이지
    python -m pipeline.build --data data/gunsan --out dist-preview --mode preview   # 아직 draft인 페이지까지
    python tools/font_subset.py --src <압축 푼 폴더>/package/dist/web/static/woff2 \\
        --corpus /tmp/prod --corpus dist-preview --out templates/assets/vendor/pretendard

- 글자 빈도 자료(--corpus)는 빌드된 페이지다(보이는 글자만 센다). 2026-10-08에는 위 두 빌드로 다시 만들었다:
  사이트 글자 1,471자가 핵심 조각 + 사이트 조각 7개(굵기마다)에 모두 들어, 어느 페이지든 첫 방문 글꼴이
  두 굵기 전부를 받아도 235KB 이하다(실측: 홈 168KB, /places/ 199KB, /food/ 190KB). 페이지 글이 바뀌어
  사이트에 없던 글자가 생기면 그 글자는 300자짜리 일반 조각(약 20KB)으로 받게 되므로, 페이지를 크게 바꾼 뒤에는
  다시 만든다.

- 필요: pip install fonttools brotli (이 도구에만 필요하다. 빌드·테스트는 결과 파일만 쓴다).
- Regular(400)·Bold(700): 원본 글꼴의 **모든 글자**를 조각으로 나눈다. 빠진 글자가 없고 OpenType 기능과
  이름·저작권·라이선스 정보를 그대로 둔다(OFL FAQ 2.7·2.8 '기능 동등' 웹 최적화). 그래서 이름 Pretendard를 유지한다.
  조각 순서: 0번(핵심) = 라틴·문장부호 + 사이트 글에서 가장 많은 페이지에 나오는 한글 --core 자,
  다음은 사이트에 나오는 나머지 한글(빈도순 --site-chunk 자씩), 그 뒤는 사이트에 없는 글자(코드 순서).
  페이지는 쓰는 글자가 든 조각만 받는다.
- ExtraLight(200): 큰 숫자용으로 숫자·쉼표·마침표·%·km 등만 남긴 부분 글꼴이다. 원본 글자를 모두 담지 않은
  수정본이므로 OFL의 예약 글꼴 이름 규정에 따라 'Light Numerals'로 이름을 바꿨다(저작권·라이선스 표기는 유지).
  CSS에서 'Light Numerals', Pretendard 순서로 쓰면 숫자는 ExtraLight, 한글은 Pretendard Regular로 그려진다.
- 같은 굵기 안에서 unicode-range가 겹치면 나중에 선언한 @font-face가 먼저 쓰인다(CSS Fonts 4 §4.5).
  그래서 코드 순서 조각의 범위는 연속 구간으로 짧게 쓰고, 핵심·사이트 조각을 마지막에 선언한다.
- 대체 글꼴 보정(CLS): 첫 방문에는 글이 시스템 글꼴로 먼저 그려졌다가 Pretendard로 바뀐다(swap). 시스템 한글은
  글자 폭이 더 넓어(Pretendard 0.864em, Noto Sans CJK KR 0.92em, WenQuanYi Zen Hei 1em) 줄 수가 줄면서 아래 내용이
  밀려 올라간다. 그래서 폭을 잰 시스템 글꼴은 local()로 부르고 size-adjust·ascent/descent-override로 한글 폭과 줄
  높이를 Pretendard에 맞춘 대체 글꼴('Pretendard Fallback …')을 만든다. 한글 범위에만 적용한다.
  Apple SD Gothic Neo·Malgun Gothic은 이 환경에서 폭을 잴 수 없어 넣지 않았다(macOS·Windows에서 재서 FALLBACKS에 더한다).
  라틴 글자·숫자·문장부호(사이트 글에서 한글 밖 글자의 절반이 띄어쓰기)도 같은 방식으로 맞춘다(LATIN_FALLBACKS: 이 환경의
  기본 산세리프 Inter). 조각은 그대로 두고 대체 글꼴 규칙만 다시 쓰려면:
      python tools/font_subset.py --fallbacks-only --out templates/assets/vendor/pretendard
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

WEIGHTS = (("Regular", 400), ("Bold", 700))
NUMERAL_TEXT = "0123456789 ,.%+-–:/~·km"
NUMERAL_FAMILY = "Light Numerals"
# 핵심 조각에 늘 넣는 글자: ASCII 전체와 한국어 글에 흔한 문장부호(사이트 글에 나온 나머지 기호는 빈도로 들어간다)
CORE_TEXT = "\u00a0·×–—‘’“”…※→「」『』〈〉《》～"
HANGUL = (0xAC00, 0xD7A3)
HANGUL_RANGES = "U+1100-11ff,U+3130-318f,U+a960-a97f,U+ac00-d7a3,U+d7b0-d7ff"
# Metric-matched fallbacks: (family, Hangul advance of the system font in em — measured from the font files,
# {weight: local() names}). Order = order in the CSS font stack after Pretendard.
FALLBACKS = (
    ("Pretendard Fallback Noto", 0.92, {  # Android·Linux Noto Sans CJK KR, desktop Noto Sans KR (920/1000)
        400: ("Noto Sans CJK KR Regular", "NotoSansCJKkr-Regular", "Noto Sans KR Regular", "NotoSansKR-Regular", "Noto Sans KR"),
        700: ("Noto Sans CJK KR Bold", "NotoSansCJKkr-Bold", "Noto Sans KR Bold", "NotoSansKR-Bold")}),
    ("Pretendard Fallback WQY", 1.0, {  # Linux default CJK font WenQuanYi Zen Hei (1000/1000; no bold face)
        400: ("WenQuanYi Zen Hei", "WenQuanYiZenHei")}),
)
# Latin, digits and punctuation painted before the web font arrives come from the system sans. Their width decides
# where lines break as much as Hangul does (in the site's text a space is half of all non-Hangul characters), so a
# swap that changes it rewraps lines and moves everything after them (CLS). Metric-matched faces for local sans fonts,
# Latin ranges only: (family, {weight: (the local font's average advance in em, local() names)}). The advances are
# weighted by the site's own non-Hangul text (space, digits, '·', ':', '()', letters), measured from the font files
# on 2026-10-08 over the preview build; LATIN_ADVANCE is Pretendard's on the same text. Add Roboto (Android) and
# Arial/Helvetica (Windows, macOS) the same way once measured.
LATIN_ADVANCE = {400: 0.3597, 700: 0.3657}
LATIN_FALLBACKS = (
    ("Pretendard Fallback Inter", {400: (0.3874, ("Inter Regular", "Inter-Regular")),
                                   700: (0.3784, ("Inter Bold", "Inter-Bold"))}),
)
LATIN_RANGES = "U+0020-007e,U+00a0-00ff,U+2010-2027,U+2030-205e"
VERSION_NOTE = "Pretendard 1.3.9"


class _Text(HTMLParser):
    """Visible text of a page (what the browser actually draws with the web font)."""

    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "title", "template"):
            self.skip += 1
        for key, value in attrs:
            if key in ("alt", "aria-label", "placeholder", "title") and value:
                self.parts.append(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "title", "template"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def corpus_docs(paths: list[Path]):
    """Yield one character set per document: each built HTML page and each record of a JSON list."""
    for root in paths:
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.suffix in (".html", ".json"))
        for path in files:
            if path.suffix == ".html":
                parser = _Text()
                parser.feed(path.read_text("utf-8", errors="replace"))
                yield set("".join(parser.parts))
            elif path.suffix == ".json":
                try:
                    data = json.loads(path.read_text("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    continue
                for record in (data if isinstance(data, list) else [data]):
                    yield set("".join(_strings(record)))


def document_frequency(paths: list[Path]) -> Counter:
    df: Counter = Counter()
    for chars in corpus_docs(paths):
        df.update(chars)
    return df


def plan_chunks(cmap: set[int], df: Counter, core: int, site_chunk: int, hangul_chunk: int, other_chunk: int):
    """Return ordered chunks [(codepoints, kind)] covering every codepoint of cmap exactly once."""
    in_core_block = lambda cp: 0x20 <= cp <= 0x7E or chr(cp) in CORE_TEXT
    is_hangul = lambda cp: HANGUL[0] <= cp <= HANGUL[1]
    used = [(n, ord(c)) for c, n in df.items() if len(c) == 1 and ord(c) in cmap]
    used_hangul = [cp for n, cp in sorted(used, key=lambda x: (-x[0], x[1])) if is_hangul(cp)]
    core_set = {cp for cp in cmap if in_core_block(cp)}
    core_set |= {cp for _, cp in used if not is_hangul(cp)}
    core_set |= set(used_hangul[:core])
    chunks = [(sorted(core_set), "core")]
    rest_site = [cp for cp in used_hangul[core:]]
    for i in range(0, len(rest_site), site_chunk):
        chunks.append((sorted(rest_site[i:i + site_chunk]), "site"))
    taken = set().union(*(set(c) for c, _ in chunks))
    left_hangul = sorted(cp for cp in cmap - taken if is_hangul(cp))
    left_other = sorted(cp for cp in cmap - taken if not is_hangul(cp))
    for i in range(0, len(left_hangul), hangul_chunk):
        chunks.append((left_hangul[i:i + hangul_chunk], "general"))
    for i in range(0, len(left_other), other_chunk):
        chunks.append((left_other[i:i + other_chunk], "general"))
    return chunks


def css_ranges(members: list[int], higher: set[int]) -> str:
    """unicode-range for a chunk; gaps made only of codepoints served by higher-priority chunks are bridged."""
    spans: list[list[int]] = []
    for cp in members:
        if spans and all(g in higher for g in range(spans[-1][1] + 1, cp)):
            spans[-1][1] = cp
        else:
            spans.append([cp, cp])
    return ",".join(f"U+{a:x}" if a == b else f"U+{a:x}-{b:x}" for a, b in spans)


def _subset(raw: bytes, unicodes: list[int], keep_everything: bool) -> "TTFont":
    from fontTools import subset
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(raw))
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.notdef_outline = True
    opts.name_IDs = ["*"]
    opts.name_languages = ["*"]
    opts.name_legacy = True
    opts.layout_features = ["*"] if keep_everything else ["tnum", "kern", "ccmp", "locl", "calt"]
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=unicodes)
    sub.subset(font)
    font.flavor = "woff2"
    return font


def _decoded(path: Path) -> bytes:
    from fontTools.ttLib import TTFont

    font = TTFont(path)
    font.flavor = None
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


def _rename(font, family: str, style: str = "ExtraLight") -> None:
    """Give a modified (partial) font its own name, keeping copyright, version and licence records."""
    ps = family.replace(" ", "") + "-" + style
    full = f"{family} {style}"
    values = {1: full, 2: "Regular", 3: f"{ps};derived from {VERSION_NOTE}", 4: full, 6: ps, 16: family, 17: style}
    table = font["name"]
    for rec in list(table.names):
        if rec.nameID in (1, 2, 3, 4, 6, 16, 17, 18, 21, 22, 25) or rec.nameID >= 256:
            table.removeNames(nameID=rec.nameID)
    for name_id, value in values.items():
        table.setName(value, name_id, 3, 1, 0x409)


def _metrics(scale: float, hhea, upm: int) -> str:
    # size-adjust also scales the override metrics, so divide to land on Pretendard's own line box.
    return (f"size-adjust:{scale * 100:.2f}%;ascent-override:{hhea.ascent / upm / scale * 100:.2f}%;"
            f"descent-override:{-hhea.descent / upm / scale * 100:.2f}%;line-gap-override:{hhea.lineGap / upm / scale * 100:.2f}%")


def fallback_faces(regular: bytes) -> list[str]:
    """@font-face rules that scale local system fonts to Pretendard's advance and line metrics: Hangul (FALLBACKS)
    and Latin · digits · punctuation (LATIN_FALLBACKS). `regular` = Pretendard Regular, or any chunk of it that
    keeps U+AC00 (the core chunk does)."""
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(regular))
    upm = font["head"].unitsPerEm
    advance = font["hmtx"][font.getBestCmap()[HANGUL[0]]][0] / upm
    hhea = font["hhea"]
    faces = []
    for family, their_advance, sources in FALLBACKS:
        metrics = _metrics(advance / their_advance, hhea, upm)
        for weight, names in sources.items():
            local = ",".join(f"local('{n}')" for n in names)
            faces.append("@font-face{font-family:'%s';font-weight:%d;src:%s;%s;unicode-range:%s}"
                         % (family, weight, local, metrics, HANGUL_RANGES))
    for family, sources in LATIN_FALLBACKS:
        for weight, (their_advance, names) in sources.items():
            local = ",".join(f"local('{n}')" for n in names)
            faces.append("@font-face{font-family:'%s';font-weight:%d;src:%s;%s;unicode-range:%s}"
                         % (family, weight, local, _metrics(LATIN_ADVANCE[weight] / their_advance, hhea, upm),
                            LATIN_RANGES))
    return faces


def rewrite_fallbacks(out: Path) -> dict:
    """--fallbacks-only: replace the 'Pretendard Fallback' rules of an existing pretendard.css (the chunks stay as
    they are); metrics from the vendored core chunk Pretendard-Regular.0.woff2."""
    css_path = out / "pretendard.css"
    lines = [l for l in css_path.read_text("utf-8").splitlines() if "font-family:'Pretendard Fallback" not in l]
    faces = fallback_faces((out / "Pretendard-Regular.0.woff2").read_bytes())
    css_path.write_text("\n".join(lines + faces) + "\n", "utf-8")
    return {"fallback_faces": len(faces), "css_bytes": css_path.stat().st_size}


def build(src: Path, corpus: list[Path], out: Path, core: int, site_chunk: int, hangul_chunk: int,
          other_chunk: int) -> dict:
    from fontTools.ttLib import TTFont

    df = document_frequency(corpus)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.woff2"):
        old.unlink()
    faces: list[str] = []
    report = {"corpus_distinct": len(df), "weights": {}}
    for style, weight in WEIGHTS:
        raw = _decoded(src / f"Pretendard-{style}.woff2")
        cmap = set(TTFont(io.BytesIO(raw)).getBestCmap())
        chunks = plan_chunks(cmap, df, core, site_chunk, hangul_chunk, other_chunk)
        assert sorted(cp for c, _ in chunks for cp in c) == sorted(cmap), "every glyph must be in exactly one chunk"
        files = []
        for i, (members, kind) in enumerate(chunks):
            name = f"Pretendard-{style}.{i}.woff2"
            buf = io.BytesIO()
            _subset(raw, members, keep_everything=True).save(buf)
            (out / name).write_bytes(buf.getvalue())
            files.append((i, name, members, kind, len(buf.getvalue())))
        # Declaration order = reverse priority: general (code order) first, then site chunks, core last.
        priority_after: dict[int, set[int]] = {}
        seen: set[int] = set()
        for i, _, members, _, _ in files:  # files are in priority order (core first)
            priority_after[i] = set(seen)
            seen |= set(members)
        for i, name, members, kind, size in reversed(files):
            faces.append("@font-face{font-family:Pretendard;font-weight:%d;font-display:swap;src:url(%s)format('woff2');"
                         "unicode-range:%s}" % (weight, name, css_ranges(members, priority_after[i])))
        report["weights"][weight] = {"chunks": len(files), "bytes": sum(f[4] for f in files),
                                     "core_bytes": files[0][4], "core_glyphs": len(files[0][2])}
    # Thin numerals (modified, renamed): only the characters big numbers need.
    raw = _decoded(src / "Pretendard-ExtraLight.woff2")
    numerals = sorted({ord(c) for c in NUMERAL_TEXT})
    font = _subset(raw, numerals, keep_everything=False)
    _rename(font, NUMERAL_FAMILY)
    buf = io.BytesIO()
    font.save(buf)
    num_name = "LightNumerals-ExtraLight.woff2"
    (out / num_name).write_bytes(buf.getvalue())
    faces.append("@font-face{font-family:'%s';font-weight:200;font-display:swap;src:url(%s)format('woff2');"
                 "unicode-range:%s}" % (NUMERAL_FAMILY, num_name, css_ranges(numerals, set())))
    report["numerals_bytes"] = len(buf.getvalue())
    faces += fallback_faces(_decoded(src / "Pretendard-Regular.woff2"))
    header = f"""/*
{VERSION_NOTE} — self-hosted unicode-range split made by tools/font_subset.py (see vendor/README.md).
Copyright (c) 2021 Kil Hyung-jin, with Reserved Font Name Pretendard. https://github.com/orioncactus/pretendard
This Font Software is licensed under the SIL Open Font License, Version 1.1 (see LICENSE.txt).
Pretendard 400/700: every character of the original font, split into chunks (all OpenType features and name records kept).
'{NUMERAL_FAMILY}' 200: digits-only subset of Pretendard ExtraLight, renamed as a Modified Version under the OFL.
Within one weight, the face declared last wins where unicode-ranges overlap (CSS Fonts 4), so the core chunk comes last.
'Pretendard Fallback *': local system fonts (Hangul; Latin, digits and punctuation) scaled to Pretendard's width and line box, so the swap does not reflow text (CLS).
*/
"""
    (out / "pretendard.css").write_text(header + "\n".join(faces) + "\n", "utf-8")
    report["css_bytes"] = (out / "pretendard.css").stat().st_size
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, help="Pretendard dist/web/static/woff2 폴더(원본 woff2)")
    ap.add_argument("--corpus", type=Path, action="append", help="빌드 결과 폴더나 data 폴더(여러 번)")
    ap.add_argument("--fallbacks-only", action="store_true",
                    help="조각은 그대로 두고 pretendard.css의 'Pretendard Fallback' 규칙만 다시 쓴다(--src·--corpus 불필요)")
    ap.add_argument("--out", type=Path, default=Path("templates/assets/vendor/pretendard"))
    ap.add_argument("--core", type=int, default=450, help="핵심 조각에 넣을 한글 수")
    ap.add_argument("--site-chunk", type=int, default=90)
    ap.add_argument("--hangul-chunk", type=int, default=300)
    ap.add_argument("--other-chunk", type=int, default=400)
    a = ap.parse_args(argv)
    if a.fallbacks_only:
        print(json.dumps(rewrite_fallbacks(a.out), ensure_ascii=False))
        return 0
    if not (a.src and a.corpus):
        ap.error("--src와 --corpus가 필요합니다(대체 글꼴 규칙만 다시 쓸 때는 --fallbacks-only)")
    report = build(a.src, a.corpus, a.out, a.core, a.site_chunk, a.hangul_chunk, a.other_chunk)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
