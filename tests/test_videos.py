"""YouTube videos: only checked entries, linked from places, all on /videos/, nothing loaded before play."""
import json
import shutil
from pathlib import Path

from pipeline.build import build
from pipeline.validate import validate

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample"


def test_videos_page_place_block_and_facade(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    videos = [
        {"youtube_id": "dBTZVpcDnw0", "title": "철길마을 걷기", "channel": "군산시 공식채널", "channel_kind": "official",
         "url": "https://www.youtube.com/watch?v=dBTZVpcDnw0", "place_slugs": ["gyeongam-railroad-village"],
         "topics": ["근대문화"], "checked_at": "2026-10-08", "verified_by": "YouTube oEmbed",
         "thumbnail": {"url": "https://i.ytimg.com/vi/dBTZVpcDnw0/mqdefault.jpg", "width": 320, "height": 180}},
        {"youtube_id": "17KwFK9VnEs", "title": "확인 안 된 영상", "url": "https://www.youtube.com/watch?v=17KwFK9VnEs",
         "place_slugs": ["gyeongam-railroad-village"], "topics": ["축제"]},  # no verified_by: never shown
    ]
    (data / "videos.json").write_text(json.dumps(videos, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "sample")
    page = (out / "videos" / "index.html").read_text("utf-8")
    assert "철길마을 걷기" in page and "확인 안 된 영상" not in page
    assert "youtube-nocookie.com/embed" not in page  # facade only: the player is created on click
    assert 'data-yt="dBTZVpcDnw0"' in page and "https://www.youtube.com/watch?v=dBTZVpcDnw0" in page
    assert '<script src="/assets/site.js"' in page  # the play buttons need it
    assert 'src="https://i.ytimg.com/vi/dBTZVpcDnw0/mqdefault.jpg"' in page and 'loading="lazy"' in page
    place = (out / "places" / "gyeongam-railroad-village" / "index.html").read_text("utf-8")
    assert 'data-yt="dBTZVpcDnw0"' in place and 'href="/videos/"' in place and "/assets/site.js" in place
    topic = (out / "videos" / "근대문화" / "index.html").read_text("utf-8")  # one page per topic
    assert "철길마을 걷기" in topic and "확인 안 된 영상" not in topic
    assert validate(data, out, "sample")[0] == []
