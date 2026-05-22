"""Render the Mermaid architecture diagram to a high-DPI PNG via Playwright.

Inlines the .mmd source into the HTML (file:// fetch is CORS-blocked).
"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

MMD = (Path(__file__).parent / "architecture.mmd").read_text(encoding="utf-8")
OUT = Path(__file__).parent.parent / "architecture.png"
TMP_HTML = Path(__file__).parent / "_render_tmp.html"

HTML = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<style>
  body { margin:0; padding:40px; background:white;
         font-family:-apple-system,"Segoe UI","Noto Sans KR",sans-serif; }
  .container { max-width:1700px; margin:0 auto; }
  h1 { text-align:center; color:#0F172A; font-weight:700; letter-spacing:-0.02em; margin:0 0 24px; }
  .mermaid { background:white; text-align:center; }
  .mermaid svg { max-width:100%; height:auto; }
</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
</head><body>
<div class="container">
  <h1>🧪 LLM Studio — Architecture</h1>
  <pre class="mermaid" id="diagram"></pre>
</div>
<script>
  // Inject source via textContent so <br/> etc. are preserved as raw text.
  document.getElementById("diagram").textContent = __MMD_JSON__;
  mermaid.initialize({
    startOnLoad: false,
    theme: "default",
    themeVariables: {
      fontFamily: '-apple-system, "Segoe UI", "Noto Sans KR", sans-serif',
      fontSize: "14px", lineColor: "#64748B",
    },
    flowchart: { curve:"basis", padding:18, nodeSpacing:48, rankSpacing:64, htmlLabels:true },
  });
  mermaid.run().then(() => { window.__mermaidReady = true; })
               .catch(e => { window.__mermaidError = (e && e.message) ? e.message : String(e); });
</script>
</body></html>"""

TMP_HTML.write_text(HTML.replace("__MMD_JSON__", json.dumps(MMD)), encoding="utf-8")

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1800, "height": 2600}, device_scale_factor=2)
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(TMP_HTML.as_uri(), wait_until="networkidle", timeout=30_000)
    try:
        page.wait_for_function(
            "window.__mermaidReady === true || window.__mermaidError",
            timeout=30_000,
        )
    except Exception as e:
        print(f"wait failed: {e}")
    err = page.evaluate("window.__mermaidError || null")
    if err:
        print(f"✗ mermaid error: {err}")
    page.wait_for_selector("svg", timeout=10_000)
    time.sleep(1.5)
    el = page.query_selector(".mermaid svg") or page.query_selector(".container")
    el.screenshot(path=str(OUT))
    browser.close()

print(f"✓ saved {OUT} ({OUT.stat().st_size//1024} KB)")
