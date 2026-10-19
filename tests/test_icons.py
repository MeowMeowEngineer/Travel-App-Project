"""The 3D picture registry (owner 2026-10-14: the whole site's generic glyph decorations become calm GPT-made 3D clay
pictures that belong with the mascot): one data-driven mapping (data/incheon/icons.json + pipeline/icons.py) from the
fixed IDs of docs/handover/gpt_image_prompts_3d_2026-10-14.md to the files tools/icon_media.py makes, and one macro
(templates/_pic.html.j2) that draws the picture when its files exist and the interim look when they do not. A tiny
generated PNG dropped in a tmp copy of incoming/icons/ turns into AVIF/WebP files, and the macro then uses them; a
missing or half-made picture falls back cleanly."""
import json
import re
from pathlib import Path

import pytest

from pipeline import icons
from pipeline.build import make_env
from tools import icon_media

ROOT = Path(__file__).resolve().parent.parent
IDS = ["icon-food", "icon-stay", "icon-sights", "icon-course", "icon-events", "icon-map", "icon-video", "icon-abroad",
       "icon-getting-here", "icon-ask", "fact-hours", "fact-closed", "fact-fee", "fact-parking", "fact-phone",
       "fact-menu", "fact-checkin", "kind-attraction", "kind-food", "kind-stay", "kind-cafe", "guide", "info-center",
       "transit-bus", "theme-modern-history", "theme-islands-sea", "theme-parks-nature", "theme-alleys-culture",
       "sit-rainy", "sit-kids", "sit-night", "sit-carfree", "sit-free", "sit-walk", "mascot-eat", "mascot-airport",
       "mascot-camera", "mascot-ferry",
       # the Incheon delivery (2026-10-19, docs/image_prompts_incheongak.md C·D·I and the seal holding a thing)
       "icon-cafe", "icon-plan", "kind-museum", "kind-experience", "kind-shopping", "kind-festival", "theme-sky-airport",
       "theme-tidal-flat", "transit-subway", "transit-ferry", "transit-plane", "mascot-cafe"]


@pytest.fixture
def tmp_assets(tmp_path, monkeypatch):
    out = tmp_path / "icons"
    monkeypatch.setattr(icons, "ASSETS", out)
    icons.reset()
    yield out
    icons.reset()


def pic():
    return make_env().get_template("_pic.html.j2").module.pic


def test_registry_holds_every_fixed_id_with_a_known_glyph():
    reg = json.loads(icons.REGISTRY.read_text("utf-8"))["icons"]
    assert set(IDS) <= set(reg)
    # (ported 2026-10-19: the check that the IDs are those of the Gunsan prompt document,
    # docs/handover/gpt_image_prompts_3d_2026-10-14.md, stayed with that document — tests/excluded_gunsan_tests.txt)
    ui = (ROOT / "templates" / "_ui.html.j2").read_text("utf-8")
    known = set(re.findall(r"name == '([a-z0-9-]+)'", ui)) | {"pin"}
    for pid, e in reg.items():
        assert e["glyph"] in known and e["label"], pid


def test_missing_files_fall_back_to_the_interim_look(tmp_assets):
    html = str(pic()("icon-food", "bowl", 56))
    assert html.startswith('<span class="pic pic-tmp" data-pic="icon-food" style="--pic:56px" aria-hidden="true"><svg')
    assert "<img" not in html and "/assets/icons/" not in html
    # no glyph given: the registry's
    assert 'class="icon pic-g"' in str(pic()("fact-hours", "", 32))
    # a picture that carries the meaning alone: role img with the illustration label
    assert 'role="img" aria-label="일러스트: 맛집"' in str(pic()("icon-food", "bowl", 56, "일러스트: 맛집"))


def test_a_dropped_png_becomes_files_and_the_page_uses_them(tmp_path, tmp_assets):
    from PIL import Image, features
    if not features.check("avif"):
        pytest.skip("Pillow without AVIF")
    src = tmp_path / "incoming"
    src.mkdir()
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    for x in range(50, 150):
        for y in range(60, 140):
            im.putpixel((x, y), (47, 116, 208, 255))
    im.save(src / "icon-food.png")
    Image.new("RGB", (100, 100), (255, 255, 255)).save(src / "not-an-id.png")   # unknown IDs are skipped
    r = icon_media.make(src, tmp_assets)
    assert r["made"] == ["icon-food"]
    for px in icon_media.SIZES:
        for fmt in ("avif", "webp"):
            f = tmp_assets / f"icon-food-{px}.{fmt}"
            assert f.is_file()
            with Image.open(f) as d:
                assert d.size == (px, px) and d.getchannel("A").getextrema()[0] == 0
    icons.reset()
    html = str(pic()("icon-food", "bowl", 56, "", False))
    assert html.startswith('<span class="pic pic-3d" data-pic="icon-food" style="--pic:56px"><picture>')
    assert '<source type="image/avif" srcset="/assets/icons/icon-food-64.avif 64w, /assets/icons/icon-food-128.avif 128w' in html
    assert 'width="56" height="56" alt="" loading="eager"' in html and 'sizes="56px"' in html
    # the other IDs still draw the interim look
    assert "pic-tmp" in str(pic()("icon-stay", "bed", 56))
    # a white-background original (the prompt's fallback) loses its background
    Image.new("RGB", (120, 120), (255, 255, 255)).save(src / "icon-stay.png")
    with Image.open(src / "icon-stay.png") as w:
        w2 = w.convert("RGB")
        for x in range(30, 90):
            w2.putpixel((x, 60), (40, 90, 200))
        w2.save(src / "icon-stay.png")
    icon_media.make(src, tmp_assets)
    with Image.open(tmp_assets / "icon-stay-64.webp") as d:
        assert d.getchannel("A").getextrema()[0] == 0
    # a half-made picture (a file gone) falls back cleanly
    (tmp_assets / "icon-food-128.webp").unlink()
    icons.reset()
    assert "pic-tmp" in str(pic()("icon-food", "bowl", 56))


def test_templates_never_name_icon_files():
    for f in (ROOT / "templates").rglob("*.j2"):
        assert "/assets/icons/" not in f.read_text("utf-8") or f.name == "_pic.html.j2", f


def test_the_delivered_pictures_have_their_files():
    """The Incheon delivery (2026-10-19): the 3D pictures of incoming/icons/ and the seal holding a thing
    (incoming/mascot/mascot-eat …, tools/icon_media.py ALSO_DIRS) are in the manifest with every size and format."""
    manifest = json.loads((ROOT / "templates" / "assets" / "icons" / "manifest.json").read_text("utf-8"))
    delivered = [i for i in IDS if not i.startswith(("fact-", "guide", "info-", "icon-abroad"))]
    for pid in delivered:
        assert pid in manifest, pid
        for fmt in ("avif", "webp"):
            assert [px for _, px in manifest[pid][fmt]] == list(icon_media.SIZES), (pid, fmt)
            for name, _ in manifest[pid][fmt]:
                assert (ROOT / "templates" / "assets" / "icons" / name).is_file(), name
    assert icon_media.ALSO_DIRS == (ROOT / "incoming" / "mascot",)
