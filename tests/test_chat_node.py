"""The site assistant's server tests (tests/js/*.test.js, node --test) — run when Node.js is installed. The tests
inject a fake client: no API key, no network.

Ported 2026-10-19: the Gunsan repository ran this with CHAT_KB_DIR = the knowledge exported from data/gunsan, so the
'real knowledge' checks of chat.test.js (written for Gunsan pages) also ran; this site has no data of its own yet, so
CHAT_KB_DIR is left unset and those checks skip as designed (tests/excluded_gunsan_tests.txt). Once data/incheon has
pages, export it here again with Incheon checks in chat.test.js."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
def test_node_server_tests():
    files = sorted(str(p) for p in (ROOT / "tests" / "js").glob("*.test.js"))
    assert files
    env = {k: v for k, v in os.environ.items() if k not in ("CHAT_KB_DIR", "ANTHROPIC_API_KEY")}
    r = subprocess.run([NODE, "--test", *files], cwd=ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    assert r.returncode == 0, (r.stdout[-6000:] + "\n" + r.stderr[-3000:])
    assert "# fail 0" in r.stdout or "ℹ fail 0" in r.stdout, r.stdout[-2000:]
