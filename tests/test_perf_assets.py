"""Stage 4 performance rules: first screen never hidden by script, motion/map libraries on demand, split fonts.

Round-3 redesign (deliberate changes): the stylesheet is written as partials in templates/assets/css and built
into one /assets/style.css (pipeline.build.site_css; the behaviour states of package B2 are the partial
65-states.css, not a second stylesheet); site.js is the only script in the HTML and attaches motion.js after the
window 'load' event, never with reduced motion (and map.js / course.js / search.js on pages with their hooks).
Count-ups are gone; SplitText line rises are an opt-in hook for headings below the first screen."""
import re
import shutil
from pathlib import Path

from pipeline.build import build, css_source, site_css

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "templates" / "assets"
FONTS = ASSETS / "vendor" / "pretendard"


def test_first_screen_is_never_hidden_and_libraries_are_not_in_head(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "sample", data)
    out = tmp_path / "out"
    build(data, out, "preview")
    pages = [out / "index.html", out / "places" / "index.html"]
    pages += sorted((out / "places").glob("*/index.html"))[:2]
    for page in pages:
        html = page.read_text("utf-8")
        assert "motion-pending" not in html
        # one deferred script in the HTML: site.js. It attaches motion.js after page load (never with reduced
        # motion); motion.js / map.js attach GSAP·ScrollTrigger·SplitText·Lenis and the Kakao Maps SDK later, on demand.
        assert html.count("<script src=") == 1 and '<script src="/assets/site.js" defer></script>' in html
        assert "/assets/motion.js" not in html
        assert '<script src="/assets/vendor/' not in html
        assert 'href="/assets/vendor/lenis/' not in html and '<script src="https://dapi.kakao.com' not in html
        assert html.count('rel="stylesheet"') == 2  # fonts + the one built stylesheet
    built = (out / "assets" / "style.css").read_text("utf-8")
    assert built == site_css() and not (out / "assets" / "css").exists()
    assert "motion-pending" not in css_source() and "/*" not in built
    motion = (ASSETS / "motion.js").read_text("utf-8")
    assert "motion-pending" not in motion and "prefers-reduced-motion" in motion
    # no count-ups (they briefly show numbers that are not in the data); line-rise headings only as an opt-in
    # hook below the first screen, and SplitText is fetched only then
    assert "data-count" not in motion and "counts(" not in motion
    assert 'split: all("[data-split]").filter(below)' in motion
    assert 'if (T.split.length) files.push("gsap/SplitText.min.js")' in motion
    site = (ASSETS / "site.js").read_text("utf-8")
    assert 'if (!reduce) {\n    afterLoad(function () { attach("motion.js"); });' in site


def test_fonts_are_split_400_700_with_digit_only_200_and_no_semibold():
    css = (FONTS / "pretendard.css").read_text("utf-8")
    faces = re.findall(r"@font-face\{([^}]*)\}", css)
    assert faces
    weights: dict[str, set[str]] = {}
    for face in faces:
        family = re.search(r"font-family:([^;]+)", face).group(1).strip("'\"")
        weight = re.search(r"font-weight:(\d+)", face).group(1)
        if family.startswith("Pretendard Fallback"):  # metric-matched system fonts: local() only, one script each
            assert "url(" not in face and "local(" in face and "size-adjust:" in face
            # Hangul faces, or (round 3, deliberate) Latin·digits·punctuation faces so a swap does not rewrap lines
            assert "unicode-range:U+1100-11ff," in face or "unicode-range:U+0020-007e," in face
            if "U+0020-007e" in face:
                assert "U+ac00" not in face
            continue
        weights.setdefault(family, set()).add(weight)
        assert "font-display:swap" in face and "unicode-range:" in face
        src = re.search(r"url\(([^)]+)\)", face).group(1)
        assert (FONTS / src).exists(), src
        if weight == "200":  # digits only: no Hangul syllable may be drawn in weight 200
            for a, b in re.findall(r"U\+([0-9a-f]+)(?:-([0-9a-f]+))?", face, re.I):
                lo, hi = int(a, 16), int(b or a, 16)
                assert hi < 0xAC00 or lo > 0xD7A3
    assert weights == {"Pretendard": {"400", "700"}, "Light Numerals": {"200"}}
    assert (FONTS / "LICENSE.txt").exists()
    assert not list(FONTS.glob("*SemiBold*"))

    style = css_source()
    stack = re.search(r"--font:([^;]+);", style).group(1)
    fallbacks = set(re.findall(r"font-family:'(Pretendard Fallback [^']+)'", css))
    assert fallbacks and all(f"'{f}'" in stack for f in fallbacks)
    assert stack.strip().startswith("'Pretendard', 'Pretendard Fallback")
    used = set(re.findall(r"font-weight:\s*(\d+)", style))
    assert used <= {"200", "400", "700", "800"}, used
    for rule in style.split("}"):
        if re.search(r"font-weight:\s*200", rule):
            assert "var(--font-num)" in rule, rule.strip()[:80]
