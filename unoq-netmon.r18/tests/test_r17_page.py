"""r17 dashboard: no domain names while locked, the 96 skins stay readable, no animation frames when idle.
Browser tests need Playwright and a Chrome/Chromium; they skip (not fail) when neither is available."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "src", "overheard", "web", "index.html")
PORT = 18084
sync_api = pytest.importorskip("playwright.sync_api", reason="playwright not installed")


def _chrome():
    for p in (os.environ.get("CHROME"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome", "/usr/bin/chromium", shutil.which("google-chrome") or "", shutil.which("chromium") or ""):
        if p and os.path.exists(p):
            return p
    return None


def _req(path, data=None, cookie=None):
    r = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), data, {"Cookie": cookie} if cookie else {}, method="POST" if data else "GET")
    if data:
        r.add_header("Content-Type", "application/json")
    return urllib.request.urlopen(r, timeout=5)


@pytest.fixture(scope="module")
def board():
    tmp = tempfile.mkdtemp()
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    p = subprocess.Popen([sys.executable, "-m", "overheard", "--demo", "--port", str(PORT), "--host", "127.0.0.1", "--no-auth", "--data-dir", tmp], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                _req("/api/health")
                break
            except OSError:
                time.sleep(0.1)
        time.sleep(6)
        secret = open(os.path.join(tmp, "unlock")).read().strip()
        ck = _req("/api/unlock", json.dumps({"secret": secret}).encode()).headers["Set-Cookie"].split(";")[0]
        yield {"cookie": ck, "tmp": tmp}
    finally:
        p.terminate()
        p.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as pw:
        try:
            exe = _chrome()
            b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        except Exception as e:   # no browser binary available
            pytest.skip("no Chrome/Chromium: %s" % str(e)[:80])
        yield b
        b.close()


def _fixture_domains(board):
    """Every domain the demo traffic can produce, plus what the unlocked API actually returned."""
    src = open(os.path.join(ROOT, "src", "overheard", "demo.py"), encoding="utf-8").read()
    doms = set(re.findall(r"\"([a-z0-9][a-z0-9.-]*\.[a-z]{2,})\"", src))
    st = json.loads(_req("/api/stats", cookie=board["cookie"]).read())
    doms |= {r["domain"] for r in st["recent"]}
    doms |= {e["domain"] for e in (st.get("now") or {}).get("evidence", [])}
    assert len(doms) > 15, "fixture produced too few domains to mean anything"
    return doms, st


def _assert_clean(text, doms, where):
    low = text.lower()
    leaked = sorted(d for d in doms if d.lower() in low)
    assert not leaked, "%s contains domain names: %s" % (where, leaked[:5])


def test_locked_page_has_no_domains(board, browser):
    doms, _ = _fixture_domains(board)
    pg = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    seen, bodies, errs = [], [], []
    pg.on("request", lambda r: seen.append(r.url + " " + (r.post_data or "")))
    pg.on("response", lambda r: bodies.append(r) if "/api/" in r.url else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:%d/" % PORT)
    pg.wait_for_timeout(4500)
    for n in pg.query_selector_all("#svg .dn"):    # open every map tooltip: they must not leak either
        n.hover()
        pg.wait_for_timeout(50)
        _assert_clean(pg.inner_html("#tip"), doms, "map tooltip")
    pg.hover("#c", position={"x": 20, "y": 20})
    _assert_clean(pg.content(), doms, "locked DOM")
    _assert_clean(pg.inner_text("body"), doms, "locked text")
    _assert_clean("\n".join(seen), doms, "locked requests")
    for r in bodies:
        _assert_clean(r.text(), doms, "locked response " + r.url)
    assert not any("/api/flagged" in u or "/api/profile" in u or "/api/unlock" in u for u in seen), "locked page asked for an admin endpoint"
    assert not errs, errs


def test_scrub_guard_strips_a_leaky_locked_response(board, browser):
    """Even if a locked reply carried domains (it never does), the page drops them."""
    doms, st = _fixture_domains(board)
    st["unlocked"] = False
    pg = browser.new_context().new_page()
    pg.route("**/api/stats", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(st)))
    pg.goto("http://127.0.0.1:%d/" % PORT)
    pg.wait_for_timeout(2500)
    _assert_clean(pg.content(), doms, "DOM after a leaky locked reply")


def test_admin_shows_feed_and_locking_clears_it(board, browser):
    doms, _ = _fixture_domains(board)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_cookies([{"name": board["cookie"].split("=")[0], "value": board["cookie"].split("=", 1)[1], "url": "http://127.0.0.1:%d/" % PORT}])
    pg = ctx.new_page()
    pg.goto("http://127.0.0.1:%d/" % PORT)
    pg.wait_for_timeout(4000)
    assert pg.is_visible("#feedP") and pg.query_selector_all("#feed .fl li"), "admin live feed is empty"
    assert pg.is_visible("#midLookups")
    for n in pg.query_selector_all("#svg .dn"):    # unlocked tooltips may name sites; locking must wipe them
        n.hover()
    pg.hover("#c", position={"x": 20, "y": 20})
    pg.evaluate("lock()")
    pg.wait_for_timeout(2500)
    assert not pg.is_visible("#feedP")
    _assert_clean(pg.inner_html("#tip"), doms, "tooltip after locking")
    _assert_clean(pg.inner_html("#feed"), doms, "feed after locking")
    assert pg.evaluate("JSON.stringify(FEED)") == "{}"
    _assert_clean(pg.content(), doms, "DOM after locking")


def test_idle_page_runs_no_animation_frames(board, browser):
    _, st = _fixture_domains(board)
    st["unlocked"] = False
    st["recent"] = []
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_init_script("window.__raf=0;const o=window.requestAnimationFrame.bind(window);window.requestAnimationFrame=f=>{window.__raf++;return o(f)}")
    pg = ctx.new_page()
    pg.route("**/api/stats", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(st)))
    pg.goto("http://127.0.0.1:%d/" % PORT)
    pg.wait_for_timeout(2500)
    pg.evaluate("window.__raf=0")
    pg.wait_for_timeout(3000)
    assert pg.evaluate("window.__raf") == 0, "frames were requested while nothing moved"


def test_layout_labels_and_no_scroll(board, browser):
    for w, h in ((1440, 900), (390, 844)):
        pg = browser.new_context(viewport={"width": w, "height": h}).new_page()
        pg.goto("http://127.0.0.1:%d/" % PORT)
        pg.wait_for_timeout(3500)
        assert pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth") <= 0, "horizontal scroll at %d" % w
        small = pg.evaluate("[...document.querySelectorAll('#svg text')].filter(t=>t.style.display!=='none'&&parseFloat(getComputedStyle(t).fontSize)<11).length")
        assert small == 0, "map labels under 11 px at %d" % w


def test_default_theme_has_no_blue_or_purple_pixels(board, browser):
    for mode in ("dark", "light"):
        pg = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        pg.goto("http://127.0.0.1:%d/?mode=%s" % (PORT, mode))
        pg.wait_for_timeout(3500)
        import base64
        b64 = base64.b64encode(pg.screenshot()).decode()
        n = pg.evaluate("""async b64=>{const i=new Image();i.src='data:image/png;base64,'+b64;await i.decode();const c=document.createElement('canvas');c.width=i.width;c.height=i.height;
          const x=c.getContext('2d');x.drawImage(i,0,0);const d=x.getImageData(0,0,c.width,c.height).data;let n=0;
          for(let k=0;k<d.length;k+=4){const r=d[k]/255,g=d[k+1]/255,b=d[k+2]/255,mx=Math.max(r,g,b),mn=Math.min(r,g,b),dl=mx-mn;if(dl<.12)continue;
            let h=mx===r?((g-b)/dl+6)%6:mx===g?(b-r)/dl+2:(r-g)/dl+4;h*=60;if(h>=200&&h<=310)n++}return n}""", b64)
        assert n == 0, "%d blue/purple pixels in the default theme (%s)" % (n, mode)


def test_all_96_skins_readable(board, browser):
    pg = browser.new_context().new_page()
    pg.goto("http://127.0.0.1:%d/" % PORT)
    pg.wait_for_timeout(1500)
    bad = pg.evaluate("""()=>{const out=[],L=a=>{const c=a.map(v=>{v/=255;return v<=.03928?v/12.92:Math.pow((v+.055)/1.055,2.4)});return .2126*c[0]+.7152*c[1]+.0722*c[2]},
      R=(a,b)=>{const x=L(a),y=L(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
      const pr=document.createElement('i');pr.style.cssText='position:absolute;visibility:hidden';document.body.appendChild(pr);
      const g=v=>{pr.style.color='var('+v+')';return rgbOf(getComputedStyle(pr).color)};
      for(const s of SKINS)for(const m of ['dark','light']){applySkin(s.id);document.documentElement.dataset.mode=m;
        [['--ink','--panel'],['--ink-2','--panel'],['--ink-2','--well'],['--ink','--raise'],['--accent','--panel'],['--on-accent','--accent'],['--accent','--well'],['--bad','--well'],['--ok','--well']]
        .forEach(([f,b])=>{const r=R(g(f),g(b));if(r<4.5)out.push(s.id+' '+m+' '+f+' on '+b+' '+r.toFixed(2))})}
      pr.remove();return [SKINS.length,out]}""")
    assert bad[0] == 48
    assert not bad[1], bad[1][:12]
