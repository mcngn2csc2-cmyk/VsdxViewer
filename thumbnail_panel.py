"""
thumbnail_panel.py — Scrollable page-thumbnail sidebar.

Each thumbnail is rendered from the raw SVG string using QSvgRenderer
and displayed in a QListWidget.  Clicking a thumbnail emits
``page_selected(int)`` with the zero-based page index.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from converter import PageInfo

THUMB_W = 160
THUMB_H = 120
THUMB_SIZE = QSize(THUMB_W, THUMB_H)
ICON_SIZE = QSize(THUMB_W - 8, THUMB_H - 8)

_PLACEHOLDER_COLOR = QColor("#dde3ec")
_BORDER_COLOR = QColor("#b0bec5")
_SELECTED_BORDER = QColor("#1976d2")


def _png_bytes_to_pixmap(png_bytes: bytes) -> QPixmap:
    """PNG画像バイト列をサムネイルサイズのQPixmapに変換する。"""
    pix = QPixmap()
    pix.loadFromData(png_bytes, "PNG")
    if pix.isNull():
        return _placeholder_pixmap("?")
    return pix.scaled(
        ICON_SIZE,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _render_svg_to_pixmap(svg_xml: str) -> QPixmap:
    """Rasterise *svg_xml* into a THUMB_W×THUMB_H pixmap (aspect-preserved)."""
    renderer = QSvgRenderer(QByteArray(svg_xml.encode()))
    if not renderer.isValid():
        return _placeholder_pixmap("?")

    vp = renderer.viewBoxF()
    if vp.isEmpty():
        vp = renderer.defaultSize().toSizeF()

    # Compute target rect that fits inside ICON_SIZE while keeping ratio
    vw, vh = vp.width() or 1.0, vp.height() or 1.0
    scale = min(ICON_SIZE.width() / vw, ICON_SIZE.height() / vh)
    tw, th = int(vw * scale), int(vh * scale)

    img = QImage(tw, th, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.white)
    painter = QPainter(img)
    renderer.render(painter)
    painter.end()

    return QPixmap.fromImage(img)


def _placeholder_pixmap(label: str = "") -> QPixmap:
    pix = QPixmap(ICON_SIZE)
    pix.fill(_PLACEHOLDER_COLOR)
    if label:
        painter = QPainter(pix)
        painter.setPen(_BORDER_COLOR)
        painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, label)
        painter.end()
    return pix


class ThumbnailPanel(QWidget):
    """Left-side panel showing one thumbnail per Visio page."""

    page_selected = Signal(int)   # zero-based page index

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumWidth(THUMB_W + 24)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        title = QLabel("Pages")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title.setStyleSheet("font-weight: bold; color: #37474f;")
        layout.addWidget(title)

        self._list = QListWidget()
        self._list.setIconSize(ICON_SIZE)
        self._list.setGridSize(THUMB_SIZE + QSize(8, 24))
        self._list.setViewMode(QListWidget.ViewMode.IconMode)
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setMovement(QListWidget.Movement.Static)
        self._list.setSpacing(4)
        self._list.setWordWrap(True)
        self._list.setStyleSheet("""
            QListWidget { background: #eceff1; border: none; }
            QListWidget::item { border: 2px solid transparent; border-radius: 4px; }
            QListWidget::item:selected { border: 2px solid #1976d2;
                                         background: #e3f2fd; }
            QListWidget::item:hover:!selected { border: 2px solid #90caf9; }
        """)
        self._list.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self._list)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clear(self) -> None:
        self._list.clear()

    def add_page(self, page: PageInfo) -> None:
        """ページのサムネイルを追加する（ページ到着時に呼ばれる）。"""
        if page.png_bytes:
            pix = _png_bytes_to_pixmap(page.png_bytes)
        else:
            pix = _render_svg_to_pixmap(page.svg)
        item = QListWidgetItem(pix, f"{page.index + 1}. {page.name}")
        item.setData(Qt.ItemDataRole.UserRole, page.index)
        item.setSizeHint(THUMB_SIZE + QSize(8, 24))
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)

        # 正しい位置に挿入
        self._list.insertItem(page.index, item)

        # 最初のページは自動選択
        if page.index == 0 and self._list.currentRow() < 0:
            self._list.setCurrentRow(0)

    def select_page(self, index: int) -> None:
        """Programmatically select page *index* without emitting signal."""
        self._list.blockSignals(True)
        self._list.setCurrentRow(index)
        self._list.blockSignals(False)

    def page_count(self) -> int:
        return self._list.count()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_row_changed(self, row: int) -> None:
        if row >= 0:
            item = self._list.item(row)
            if item is not None:
                idx = item.data(Qt.ItemDataRole.UserRole)
                if idx is not None:
                    self.page_selected.emit(int(idx))
