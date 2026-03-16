"""
web_viewer.py — QWebEngineView-based SVG page viewer.

Displays a single Visio page (SVG) with:
  • Smooth pan (click-drag) and zoom (Ctrl+scroll or toolbar buttons)
  • "Fit page" reset
  • Chromium-quality rendering via QtWebEngine
"""

from __future__ import annotations

import html
import json

from PySide6.QtCore import QUrl, Qt
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QSizePolicy

# ---------------------------------------------------------------------------
# HTML template that hosts the SVG with pan/zoom via vanilla JS
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{
    width: 100%; height: 100%;
    background: #f5f5f5;
    overflow: hidden;
    user-select: none;
  }}
  #viewport {{
    width: 100%; height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    cursor: grab;
  }}
  #viewport.dragging {{ cursor: grabbing; }}
  #canvas {{
    transform-origin: 0 0;
    /* transition: transform 0.05s ease-out; */
  }}
  #canvas svg {{
    display: block;
    background: white;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
  }}
</style>
</head>
<body>
<div id="viewport">
  <div id="canvas">
    {svg_content}
  </div>
</div>
<script>
(function () {{
  "use strict";

  const viewport = document.getElementById("viewport");
  const canvas   = document.getElementById("canvas");

  let scale = 1.0;
  let tx = 0, ty = 0;   // translation (px in screen space)
  let drag = false;
  let startX = 0, startY = 0, startTx = 0, startTy = 0;

  // ------------------------------------------------------------------
  // Fit the SVG into the viewport on load
  // ------------------------------------------------------------------
  function fitPage() {{
    const vw = viewport.clientWidth  || window.innerWidth;
    const vh = viewport.clientHeight || window.innerHeight;
    const svgEl = canvas.querySelector("svg");
    let svgW, svgH;
    if (svgEl) {{
      const vb = svgEl.viewBox && svgEl.viewBox.baseVal;
      if (vb && vb.width > 0 && vb.height > 0) {{
        svgW = vb.width; svgH = vb.height;
      }} else {{
        svgW = svgEl.clientWidth  || parseFloat(svgEl.getAttribute("width"))  || vw;
        svgH = svgEl.clientHeight || parseFloat(svgEl.getAttribute("height")) || vh;
      }}
    }} else {{
      svgW = vw; svgH = vh;
    }}
    const padding = 0.92;
    scale = Math.min(vw / svgW, vh / svgH) * padding;
    tx = (vw - svgW * scale) / 2;
    ty = (vh - svgH * scale) / 2;
    applyTransform();
  }}

  function applyTransform() {{
    canvas.style.transform = `translate(${{tx}}px, ${{ty}}px) scale(${{scale}})`;
  }}

  // ------------------------------------------------------------------
  // Mouse pan
  // ------------------------------------------------------------------
  viewport.addEventListener("mousedown", (e) => {{
    if (e.button !== 0) return;
    drag = true;
    startX = e.clientX; startY = e.clientY;
    startTx = tx; startTy = ty;
    viewport.classList.add("dragging");
    e.preventDefault();
  }});
  window.addEventListener("mousemove", (e) => {{
    if (!drag) return;
    tx = startTx + (e.clientX - startX);
    ty = startTy + (e.clientY - startY);
    applyTransform();
  }});
  window.addEventListener("mouseup", () => {{
    drag = false;
    viewport.classList.remove("dragging");
  }});

  // ------------------------------------------------------------------
  // Wheel zoom (Ctrl held = zoom, plain scroll = pan vertically)
  // ------------------------------------------------------------------
  viewport.addEventListener("wheel", (e) => {{
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {{
      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      const mx = e.clientX, my = e.clientY;
      // Zoom toward cursor
      tx = mx - (mx - tx) * factor;
      ty = my - (my - ty) * factor;
      scale *= factor;
      scale = Math.max(0.05, Math.min(scale, 32));
    }} else {{
      tx -= e.deltaX;
      ty -= e.deltaY;
    }}
    applyTransform();
  }}, {{ passive: false }});

  // ------------------------------------------------------------------
  // Touch pan / pinch-zoom
  // ------------------------------------------------------------------
  let touches = [];
  let touchTx0 = 0, touchTy0 = 0, touchScale0 = 1, touchDist0 = 0;

  viewport.addEventListener("touchstart", (e) => {{
    e.preventDefault();
    touches = Array.from(e.touches);
    touchTx0 = tx; touchTy0 = ty; touchScale0 = scale;
    if (touches.length === 2) {{
      touchDist0 = Math.hypot(
        touches[1].clientX - touches[0].clientX,
        touches[1].clientY - touches[0].clientY
      );
    }}
  }}, {{ passive: false }});

  viewport.addEventListener("touchmove", (e) => {{
    e.preventDefault();
    const cur = Array.from(e.touches);
    if (cur.length === 1 && touches.length === 1) {{
      tx = touchTx0 + (cur[0].clientX - touches[0].clientX);
      ty = touchTy0 + (cur[0].clientY - touches[0].clientY);
    }} else if (cur.length === 2 && touches.length >= 2) {{
      const dist = Math.hypot(
        cur[1].clientX - cur[0].clientX,
        cur[1].clientY - cur[0].clientY
      );
      const factor = dist / (touchDist0 || 1);
      const cx = (cur[0].clientX + cur[1].clientX) / 2;
      const cy = (cur[0].clientY + cur[1].clientY) / 2;
      const cx0 = (touches[0].clientX + touches[1].clientX) / 2;
      const cy0 = (touches[0].clientY + touches[1].clientY) / 2;
      scale = Math.max(0.05, Math.min(touchScale0 * factor, 32));
      tx = cx - (cx0 - touchTx0) - (cx0 - (touchTx0 + cx0)) * factor;
      ty = cy - (cy0 - touchTy0) - (cy0 - (touchTy0 + cy0)) * factor;
    }}
    applyTransform();
  }}, {{ passive: false }});

  // ------------------------------------------------------------------
  // Public API called from Python via runJavaScript
  // ------------------------------------------------------------------
  window._viewer = {{
    zoomIn:  () => {{ scale = Math.min(scale * 1.25, 32); applyTransform(); }},
    zoomOut: () => {{ scale = Math.max(scale / 1.25, 0.05); applyTransform(); }},
    fitPage: fitPage,
    zoom100: () => {{ scale = 1.0; tx = 0; ty = 0; applyTransform(); }},
    setZoom: (s) => {{ scale = s; applyTransform(); }},
  }};

  // Initial fit after first paint
  window.addEventListener("load", fitPage);
  // Also fit when the window is resized
  window.addEventListener("resize", fitPage);

  // Fit immediately in case load already fired
  if (document.readyState === "complete") {{ fitPage(); }}
}})();
</script>
</body>
</html>
"""

_LOADING_HTML = """\
<!DOCTYPE html><html><body style="margin:0;background:#f5f5f5;
  display:flex;align-items:center;justify-content:center;height:100vh;">
<p style="font-family:sans-serif;color:#78909c;font-size:18px;">
  Converting…
</p></body></html>
"""

_EMPTY_HTML = """\
<!DOCTYPE html><html><body style="margin:0;background:#f5f5f5;
  display:flex;flex-direction:column;align-items:center;
  justify-content:center;height:100vh;gap:12px;">
<p style="font-family:sans-serif;color:#90a4ae;font-size:22px;">
  No file open
</p>
<p style="font-family:sans-serif;color:#b0bec5;font-size:14px;">
  Drag &amp; drop a .vsdx file or use File → Open
</p>
</body></html>
"""


class WebViewer(QWebEngineView):
    """QWebEngineView that renders a Visio page given as an SVG string."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(False)  # parent window handles drops
        self._current_svg: str | None = None
        self._show_empty()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_loading(self) -> None:
        self.setHtml(_LOADING_HTML)

    def load_page(self, svg_xml: str) -> None:
        """Display *svg_xml* in the viewer."""
        self._current_svg = svg_xml
        # Inline the SVG directly — no encoding round-trip issues
        page_html = _HTML_TEMPLATE.format(svg_content=svg_xml)
        self.setHtml(page_html, QUrl("about:blank"))

    def zoom_in(self) -> None:
        self.page().runJavaScript("window._viewer && window._viewer.zoomIn();")

    def zoom_out(self) -> None:
        self.page().runJavaScript("window._viewer && window._viewer.zoomOut();")

    def fit_page(self) -> None:
        self.page().runJavaScript("window._viewer && window._viewer.fitPage();")

    def zoom_100(self) -> None:
        self.page().runJavaScript("window._viewer && window._viewer.zoom100();")

    def current_svg(self) -> str | None:
        return self._current_svg

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _show_empty(self) -> None:
        self.setHtml(_EMPTY_HTML)
