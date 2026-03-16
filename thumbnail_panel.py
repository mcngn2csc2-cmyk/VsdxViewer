"""
thumbnail_panel.py — Scrollable page-thumbnail sidebar.

Each thumbnail is rendered from the raw SVG string using QSvgRenderer
and displayed in a QListWidget.  Clicking a thumbnail emits
``page_selected(int)`` with the zero-based page index.
"""

from __future__ import annotations

from typing import List

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

THUMB_W = 160
THUMB_H = 120
THUMB_SIZE = QSize(THUMB_W, THUMB_H)
ICON_SIZE = QSize(THUMB_W - 8, THUMB_H - 8)

_PLACEHOLDER_COLOR = QColor("#dde3ec")
_BORDER_COLOR = QColor("#b0bec5")
_SELECTED_BORDER = QColor("#1976d2")


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
        self._pages: List[str] = []   # svg strings indexed by page number

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
        self._pages.clear()
        self._list.clear()

    def add_page(self, index: int, name: str, svg_xml: str) -> None:
        """Append thumbnail for page *index* (called as pages arrive)."""
        # Grow the list to accommodate out-of-order arrivals
        while len(self._pages) <= index:
            self._pages.append("")
        self._pages[index] = svg_xml

        pix = _render_svg_to_pixmap(svg_xml)
        item = QListWidgetItem(pix, f"{index + 1}. {name}")
        item.setData(Qt.ItemDataRole.UserRole, index)
        item.setSizeHint(THUMB_SIZE + QSize(8, 24))
        item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)

        # Insert at correct position
        self._list.insertItem(index, item)

        # Select first page automatically
        if index == 0 and self._list.currentRow() < 0:
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
