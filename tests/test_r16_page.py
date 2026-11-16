"""Guards for the dashboard page. smoke.py never loads index.html, so a broken script used to pass CI."""
import glob
import os
import re
import shutil
import subprocess

import pytest

WEB = os.path.join(os.path.dirname(__file__), "..", "src", "overheard", "web")
PAGES = sorted(glob.glob(os.path.join(WEB, "*.html")))
SCRIPT = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script>", re.S | re.I)


def _inline_scripts(path):
    text = open(path, encoding="utf-8").read()
    out = []
    for m in SCRIPT.finditer(text):
        attrs = m.group("attrs")
        if "src=" in attrs.lower() or not m.group("body").strip():
            continue
        t = re.search(r"type\s*=\s*[\"']?([^\"'\s>]+)", attrs, re.I)
        if t and t.group(1).lower() not in ("text/javascript", "application/javascript", "module"):
            continue
        out.append((text.count("\n", 0, m.start("body")) + 1, m.group("body"), bool(t and t.group(1).lower() == "module")))
    return out


def test_pages_exist():
    assert PAGES, "no html pages under src/overheard/web"


def test_inline_scripts_parse(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found: install Node.js to syntax-check the dashboard scripts (CI installs it)")
    errors = []
    for page in PAGES:
        for i, (line, body, module) in enumerate(_inline_scripts(page)):
            f = tmp_path / ("%s.%d.%s" % (os.path.basename(page), i, "mjs" if module else "js"))
            f.write_text(body, encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
            if r.returncode:
                errors.append("%s (script starting at line %d):\n%s" % (os.path.basename(page), line, r.stderr.strip()))
    assert not errors, "\n\n".join(errors)


def test_no_client_side_only_unlock():
    """Hiding the DOM is not access control: the access token cookie is the only gate."""
    for path in PAGES + glob.glob(os.path.join(WEB, "*.js")):
        text = open(path, encoding="utf-8").read()
        assert not re.search(r"""sessionStorage[^;\n]*ov_dev|ov_dev[^;\n]*sessionStorage""", text), os.path.basename(path)
        assert "ov_dev" not in text, "%s still references the client-side unlock key ov_dev" % os.path.basename(path)
