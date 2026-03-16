"""
web_viewer.py — QWebEngineView-based page viewer.

SVG文字列またはPNG画像バイト列を受け取り、パン・ズーム付きで表示する。
  • パン: クリックドラッグ
  • ズーム: Ctrl+スクロール またはツールバーボタン
  • フィットページ: ページ全体をビューポートに収める
"""

from __future__ import annotations

import base64

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QSizePolicy

# ---------------------------------------------------------------------------
# HTML template — SVG / <img> どちらのコンテンツでも動作する
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
  }}
  #canvas svg, #canvas img {{
    display: block;
    background: white;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
  }}
</style>
</head>
<body>
<div id="viewport">
  <div id="canvas">
    {content}
  </div>
</div>
<script>
(function () {{
  "use strict";

  const viewport = document.getElementById("viewport");
  const canvas   = document.getElementById("canvas");

  let scale = 1.0;
  let tx = 0, ty = 0;
  let drag = false;
  let startX = 0, startY = 0, startTx = 0, startTy = 0;

  // ------------------------------------------------------------------
  // コンテンツ（SVG or img）の固有サイズを取得
  // ------------------------------------------------------------------
  function getContentSize() {{
    const vw = viewport.clientWidth  || window.innerWidth;
    const vh = viewport.clientHeight || window.innerHeight;
    const svgEl = canvas.querySelector("svg");
    const imgEl = canvas.querySelector("img");
    if (svgEl) {{
      const vb = svgEl.viewBox && svgEl.viewBox.baseVal;
      if (vb && vb.width > 0 && vb.height > 0) {{
        return {{ w: vb.width, h: vb.height }};
      }}
      return {{
        w: svgEl.clientWidth  || parseFloat(svgEl.getAttribute("width"))  || vw,
        h: svgEl.clientHeight || parseFloat(svgEl.getAttribute("height")) || vh,
      }};
    }}
    if (imgEl) {{
      if (imgEl.naturalWidth > 0) {{
        return {{ w: imgEl.naturalWidth, h: imgEl.naturalHeight }};
      }}
      return {{ w: imgEl.width || vw, h: imgEl.height || vh }};
    }}
    return {{ w: vw, h: vh }};
  }}

  // ------------------------------------------------------------------
  // ページをビューポートにフィット
  // ------------------------------------------------------------------
  function fitPage() {{
    const vw = viewport.clientWidth  || window.innerWidth;
    const vh = viewport.clientHeight || window.innerHeight;
    const {{ w: cw, h: ch }} = getContentSize();
    const padding = 0.92;
    scale = Math.min(vw / cw, vh / ch) * padding;
    tx = (vw - cw * scale) / 2;
    ty = (vh - ch * scale) / 2;
    applyTransform();
  }}

  function applyTransform() {{
    canvas.style.transform = `translate(${{tx}}px, ${{ty}}px) scale(${{scale}})`;
  }}

  // ------------------------------------------------------------------
  // マウスパン
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
  // ホイールズーム（Ctrl押下でズーム、それ以外は縦パン）
  // ------------------------------------------------------------------
  viewport.addEventListener("wheel", (e) => {{
    e.preventDefault();
    if (e.ctrlKey || e.metaKey) {{
      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      const mx = e.clientX, my = e.clientY;
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
  // タッチパン / ピンチズーム
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
  // Python から runJavaScript で呼び出される公開API
  // ------------------------------------------------------------------
  window._viewer = {{
    zoomIn:  () => {{ scale = Math.min(scale * 1.25, 32); applyTransform(); }},
    zoomOut: () => {{ scale = Math.max(scale / 1.25, 0.05); applyTransform(); }},
    fitPage: fitPage,
    zoom100: () => {{ scale = 1.0; tx = 0; ty = 0; applyTransform(); }},
    setZoom: (s) => {{ scale = s; applyTransform(); }},
  }};

  // ------------------------------------------------------------------
  // 初期フィット（img は onload でも呼ばれるので二重でも問題なし）
  // ------------------------------------------------------------------
  window.addEventListener("load", fitPage);
  window.addEventListener("resize", fitPage);
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
    """QWebEngineView で Visio ページを表示するビューア。

    SVG文字列（load_page）またはPNG画像バイト列（load_page_image）に対応。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(False)
        self._show_empty()

    # ------------------------------------------------------------------
    # 公開API
    # ------------------------------------------------------------------

    def show_loading(self) -> None:
        self.setHtml(_LOADING_HTML)

    def load_page(self, svg_xml: str) -> None:
        """SVG文字列を表示する（libvisio-ng SVGモード）。"""
        page_html = _HTML_TEMPLATE.format(content=svg_xml)
        self.setHtml(page_html, QUrl("about:blank"))

    def load_page_image(self, png_bytes: bytes) -> None:
        """PNG画像バイト列を表示する（Visio COM PDFモード）。"""
        b64 = base64.b64encode(png_bytes).decode("ascii")
        img_tag = (
            '<img src="data:image/png;base64,' + b64 + '" '
            'onload="fitPage()" '
            'style="display:block;">'
        )
        page_html = _HTML_TEMPLATE.format(content=img_tag)
        self.setHtml(page_html, QUrl("about:blank"))

    def zoom_in(self) -> None:
        self.page().runJavaScript("window._viewer && window._viewer.zoomIn();")

    def zoom_out(self) -> None:
        self.page().runJavaScript("window._viewer && window._viewer.zoomOut();")

    def fit_page(self) -> None:
        self.page().runJavaScript("window._viewer && window._viewer.fitPage();")

    def zoom_100(self) -> None:
        self.page().runJavaScript("window._viewer && window._viewer.zoom100();")

    # ------------------------------------------------------------------
    # 非公開
    # ------------------------------------------------------------------

    def _show_empty(self) -> None:
        self.setHtml(_EMPTY_HTML)
