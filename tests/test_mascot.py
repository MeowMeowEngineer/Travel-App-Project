"""The site's mascot (operator delivery 2026-10-19: a small round baby spotted seal with a sea-blue scarf and a coral
backpack, soft 3D clay): the files tools/mascot_media.py makes from the git-ignored originals (incoming/mascot/), the
manifest that lists them, their budget (an icon at most 8 KB), the one macro that draws them (templates/_mascot.html.j2:
decorative, 1x and 2x, width = height), and the tool itself on a generated picture — the faint specks gone, the body
opaque, the transparent margin cut to an even padding, square sizes, the same bytes every time.

Ported 2026-10-19: the Gunsan mascot is that site's own (owner decision 2026-10-13, '군산 사이트 전용') and was not
copied; this site's own, the seal, came the same day. The mascot stays optional for the engine (pipeline/icons.py
mascot()): without files the macro draws its fallback and no page names a mascot file (tested on an empty folder);
the tests that need a fixed set of poses make a test-owned one (fake_mascot) in a tmp folder."""
import json
import re
from pathlib import Path

import pytest

from pipeline import icons
from pipeline.build import build, make_env
from tools import mascot_media as mm

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
MASCOT = ROOT / "templates" / "assets" / "mascot"


@pytest.fixture
def fake_mascot(tmp_path, monkeypatch):
    """A test-owned mascot folder as tools/mascot_media.py lays it out (every pose, its sizes; placeholder bytes)."""
    folder = tmp_path / "mascot"
    folder.mkdir()
    manifest = {}
    for name, size in mm.POSES.items():
        entry = {"size": size, "px": list(mm.SIZES[size])}
        for fmt in ("avif", "webp"):
            entry[fmt] = []
            for px in mm.SIZES[size]:
                (folder / f"{name}-{px}.{fmt}").write_bytes(b"x" * 10)
                entry[fmt].append([f"{name}-{px}.{fmt}", px, 10])
        manifest[name] = entry
    (folder / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    monkeypatch.setattr(icons, "MASCOT", folder)
    icons.reset()
    yield folder
    icons.reset()


def test_the_committed_files_match_the_manifest_and_the_budget():
    if not (MASCOT / "manifest.json").exists():
        # no mascot chosen for this site yet: nothing stray in templates/assets/mascot either
        assert not MASCOT.exists() or not [f for f in MASCOT.iterdir()], sorted(f.name for f in MASCOT.iterdir())
        return
    manifest = json.loads((MASCOT / "manifest.json").read_text("utf-8"))
    assert set(manifest) == set(mm.POSES)
    # the chat states the later panel redesign uses, and the faces of the launcher
    assert {"mascot-icon-3d", "mascot-hello", "mascot-think", "mascot-sorry", "mascot-search", "mascot-404",
            "mascot-empty"} <= set(manifest)
    listed = set()
    for name, e in manifest.items():
        assert e["size"] == mm.POSES[name] and e["px"] == list(mm.SIZES[e["size"]]), name
        for fmt in ("avif", "webp"):
            assert [px for _, px, _ in e[fmt]] == list(mm.SIZES[e["size"]]), (name, fmt)
            for fname, px, size in e[fmt]:
                f = MASCOT / fname
                assert f.is_file() and f.stat().st_size == size, fname
                assert fname == f"{name}-{px}.{fmt}"
                if e["size"] == "icon":
                    assert size <= mm.ICON_BUDGET, fname       # an icon is at most 8 KB
                listed.add(fname)
    on_disk = {f.name for f in MASCOT.iterdir() if f.name != "manifest.json"}
    assert on_disk == listed                                    # nothing stray in templates/assets/mascot


def test_the_files_are_square_with_transparency():
    from PIL import Image, features
    if not features.check("avif"):
        pytest.skip("Pillow without AVIF")
    for f in sorted(MASCOT.glob("*.*")):
        if f.suffix not in (".avif", ".webp"):
            continue
        px = int(re.search(r"-(\d+)\.", f.name).group(1))
        with Image.open(f) as im:
            assert im.size == (px, px), f.name
            assert im.mode == "RGBA" and im.getchannel("A").getextrema()[0] == 0, f.name   # a transparent corner


def test_without_a_mascot_the_macro_draws_its_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(icons, "MASCOT", tmp_path / "none")
    icons.reset()
    pic = make_env().get_template("_mascot.html.j2").module.pic
    assert str(pic("mascot-hello", "small", 88, "hk-mascot")) == ""                   # decorative: nothing
    face = str(pic("mascot-icon-3d", "icon", 52, glyph="chat"))                      # the launcher keeps a face
    assert face.startswith('<span class="mascot-g" style="--mg:52px" aria-hidden="true"><svg') and "/assets/mascot/" not in face
    icons.reset()


def test_the_macro_draws_a_decorative_square_at_one_and_two_x(fake_mascot):
    pic = make_env().get_template("_mascot.html.j2").module.pic
    html = str(pic("mascot-hello", "small", 88, "hk-mascot"))
    assert html == ('<picture class="hk-mascot"><source type="image/avif" srcset="/assets/mascot/mascot-hello-96.avif 1x, '
                    '/assets/mascot/mascot-hello-192.avif 2x"><img src="/assets/mascot/mascot-hello-96.webp" '
                    'srcset="/assets/mascot/mascot-hello-96.webp 1x, /assets/mascot/mascot-hello-192.webp 2x" '
                    'width="88" height="88" alt="" decoding="async" fetchpriority="low"></picture>')
    assert make_env().get_template("_mascot.html.j2").module.MASCOT_PX == \
        {k: tuple(v) for k, v in mm.SIZES.items()}               # the macro and the tool name the same sizes


def _named(out):
    named = set()
    for page in out.rglob("*.html"):
        named |= set(re.findall(r"/assets/mascot/([A-Za-z0-9._-]+)", page.read_text("utf-8")))
    return named


def test_every_mascot_file_a_page_names_is_published(tmp_path, fake_mascot):
    out = tmp_path / "out"
    build(SAMPLE, out, "sample")
    named = _named(out)
    assert {"mascot-icon-3d-64.avif", "mascot-icon-3d-128.avif", "mascot-icon-3d-64.webp"} <= named
    for name in named:
        assert (out / "assets" / "mascot" / name).is_file(), name


def test_without_a_mascot_no_page_names_one(tmp_path, monkeypatch):
    monkeypatch.setattr(icons, "MASCOT", tmp_path / "none")
    icons.reset()
    out = tmp_path / "out"
    build(SAMPLE, out, "sample")
    icons.reset()
    assert _named(out) == set() and not (out / "assets" / "mascot").exists()


def test_the_tool_cleans_trims_and_is_deterministic(tmp_path):
    from PIL import Image, features
    if not features.check("avif"):
        pytest.skip("Pillow without AVIF")
    src, one, two = tmp_path / "src", tmp_path / "one", tmp_path / "two"
    src.mkdir()
    for name in mm.POSES:
        im = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        for x in range(100, 220):                                # the figure: 120×80, its body stored at alpha 253
            for y in range(140, 220):
                im.putpixel((x, y), (250, 210, 60, 253))
        im.putpixel((5, 5), (255, 255, 0, 4))                    # a faint speck far away, as the generator leaves
        im.save(src / f"{name}.png")
    assert mm.main(["--src", str(src), "--out", str(one)]) == 0
    assert mm.main(["--src", str(src), "--out", str(two), "--force"]) == 0
    files = sorted(f.name for f in one.iterdir())
    assert all((one / f).read_bytes() == (two / f).read_bytes() for f in files)   # the same bytes every time
    with Image.open(src / "mascot-hello.png") as orig:
        sq = mm.clean(orig)
    pad = round(120 * mm.MARGIN)
    assert sq.size == (120 + 2 * pad, 120 + 2 * pad)            # cut to the figure (the speck is gone), an even pad
    alpha = sq.getchannel("A")
    assert alpha.getbbox() == (pad, (sq.height - 80) // 2, pad + 120, (sq.height - 80) // 2 + 80)
    assert alpha.getextrema() == (0, 255)                        # the body is opaque now
    manifest = json.loads((one / "manifest.json").read_text("utf-8"))
    assert [px for _, px, _ in manifest["mascot-icon-3d"]["avif"]] == [64, 128]
    (src / "mascot-hello.png").unlink()                          # another computer: the originals are not in git
    assert mm.main(["--src", str(src), "--out", str(one)]) == 0
    assert sorted(f.name for f in one.iterdir()) == files
