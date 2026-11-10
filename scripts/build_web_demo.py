"""Build index.html: the live demo that runs entirely in the visitor's browser.

It uses stlite (Streamlit compiled to WebAssembly via Pyodide), so the app
needs no server: GitHub Pages serves the files and Python runs client-side.

Run after changing any app file:  python scripts/build_web_demo.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STLITE = "1.11.0"

PATTERNS = ["app.py", "triage/*.py", "templates/*.j2", "data/sample_labels.csv", "data/sample_inbox/*.eml"]

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Inbox Triage Workflow - live demo</title>
  <meta name="description" content="End-to-end email triage workflow running in your browser." />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@stlite/browser@__V__/build/stlite.css" />
  <style>
    #loading { font-family: system-ui, sans-serif; max-width: 560px; margin: 18vh auto; padding: 0 16px;
               color: #334155; text-align: center; line-height: 1.5; }
    #loading .bar { height: 4px; background: #e2e8f0; border-radius: 2px; overflow: hidden; margin: 20px 0; }
    #loading .bar i { display: block; height: 100%; width: 40%; background: #6366f1; animation: slide 1.4s infinite; }
    @keyframes slide { from { margin-left: -40%; } to { margin-left: 100%; } }
  </style>
</head>
<body>
  <div id="loading">
    <h2>Inbox Triage Workflow</h2>
    <div class="bar"><i></i></div>
    <p>Loading Python in your browser. The first visit takes about 20-40 seconds;
       after that it is cached.</p>
    <p style="font-size: 0.9em; color: #64748b">Nothing is sent to a server: the whole workflow runs on your device.
       Source code: <a href="https://github.com/MrunalKulkarni082/inbox-triage">GitHub</a></p>
  </div>
  <div id="root"></div>
  <script type="module">
    import { mount } from "https://cdn.jsdelivr.net/npm/@stlite/browser@__V__/build/stlite.js";
    const files = __FILES__;
    const spec = {};
    for (const f of files) spec[f] = { url: "./" + f };
    mount({ requirements: ["pydantic", "jinja2", "sqlite3"], entrypoint: "app.py", files: spec },
          document.getElementById("root"));
    const hide = new MutationObserver(() => {
      if (document.querySelector("#root [data-testid]")) {
        document.getElementById("loading").remove(); hide.disconnect();
      }
    });
    hide.observe(document.getElementById("root"), { childList: true, subtree: true });
  </script>
</body>
</html>
"""


def main() -> None:
    files = sorted({p.relative_to(ROOT).as_posix() for pat in PATTERNS for p in ROOT.glob(pat)})
    html = TEMPLATE.replace("__V__", STLITE).replace("__FILES__", json.dumps(files))
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    (ROOT / ".nojekyll").write_text("", encoding="utf-8")  # serve files as-is on GitHub Pages
    print(f"index.html written with {len(files)} files")


if __name__ == "__main__":
    main()
