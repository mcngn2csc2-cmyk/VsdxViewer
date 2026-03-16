"""
main.py — Visio (.vsdx) viewer built with PySide6 + QtWebEngine.

Layout
------
┌─────────────────────────────────────────────┐
│  Menu bar                                   │
├──────────┬──────────────────────────────────┤
│Thumbnails│                                  │
│  panel   │        WebViewer                 │
│(left)    │   (QWebEngineView / Chromium)    │
│          │                                  │
├──────────┴──────────────────────────────────┤
│  Status bar  [progress bar]   zoom buttons  │
└─────────────────────────────────────────────┘

Drag & drop a .vsdx (or .vsd) file anywhere onto the window to open it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolBar,
    QWidget,
)

from converter import PageInfo
from thumbnail_panel import ThumbnailPanel
from web_viewer import WebViewer
from worker import ConversionWorker

_APP_NAME = "VsdxViewer"
_SUPPORTED = "Visio Files (*.vsdx *.vsd);;All Files (*)"
_RECENT_MAX = 10


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(_APP_NAME)
        self.resize(1280, 800)
        self.setAcceptDrops(True)

        self._pages: List[PageInfo] = []
        self._current_page: int = 0
        self._worker: Optional[ConversionWorker] = None
        self._recent: List[str] = []

        self._build_ui()
        self._build_menu()
        self._build_toolbar()
        self._build_statusbar()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._thumbnail_panel = ThumbnailPanel()
        self._web_viewer = WebViewer()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._thumbnail_panel)
        splitter.addWidget(self._web_viewer)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([180, 1100])
        splitter.setChildrenCollapsible(False)

        self.setCentralWidget(splitter)

        self._thumbnail_panel.page_selected.connect(self._on_page_selected)

    def _build_menu(self) -> None:
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu("&File")

        open_act = QAction("&Open…", self)
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        open_act.triggered.connect(self._open_dialog)
        file_menu.addAction(open_act)

        self._recent_menu = file_menu.addMenu("Open &Recent")
        self._recent_menu.setEnabled(False)

        file_menu.addSeparator()

        close_act = QAction("&Close", self)
        close_act.setShortcut(QKeySequence("Ctrl+W"))
        close_act.triggered.connect(self._close_file)
        file_menu.addAction(close_act)

        file_menu.addSeparator()

        quit_act = QAction("&Quit", self)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        # View
        view_menu = mb.addMenu("&View")

        zoom_in_act = QAction("Zoom &In", self)
        zoom_in_act.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zoom_in_act.triggered.connect(self._web_viewer.zoom_in)
        view_menu.addAction(zoom_in_act)

        zoom_out_act = QAction("Zoom &Out", self)
        zoom_out_act.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zoom_out_act.triggered.connect(self._web_viewer.zoom_out)
        view_menu.addAction(zoom_out_act)

        fit_act = QAction("&Fit Page", self)
        fit_act.setShortcut(QKeySequence("Ctrl+0"))
        fit_act.triggered.connect(self._web_viewer.fit_page)
        view_menu.addAction(fit_act)

        actual_act = QAction("&Actual Size (100%)", self)
        actual_act.setShortcut(QKeySequence("Ctrl+1"))
        actual_act.triggered.connect(self._web_viewer.zoom_100)
        view_menu.addAction(actual_act)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Navigation")
        tb.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        open_btn = QPushButton("Open")
        open_btn.clicked.connect(self._open_dialog)
        tb.addWidget(open_btn)

        tb.addSeparator()

        self._prev_btn = QPushButton("◀ Prev")
        self._prev_btn.setEnabled(False)
        self._prev_btn.clicked.connect(self._prev_page)
        tb.addWidget(self._prev_btn)

        self._page_label = QLabel("  —  ")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_label.setMinimumWidth(80)
        tb.addWidget(self._page_label)

        self._next_btn = QPushButton("Next ▶")
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self._next_page)
        tb.addWidget(self._next_btn)

        tb.addSeparator()

        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedWidth(32)
        zoom_out_btn.clicked.connect(self._web_viewer.zoom_out)
        tb.addWidget(zoom_out_btn)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedWidth(32)
        zoom_in_btn.clicked.connect(self._web_viewer.zoom_in)
        tb.addWidget(zoom_in_btn)

        fit_btn = QPushButton("Fit")
        fit_btn.clicked.connect(self._web_viewer.fit_page)
        tb.addWidget(fit_btn)

        actual_btn = QPushButton("100%")
        actual_btn.clicked.connect(self._web_viewer.zoom_100)
        tb.addWidget(actual_btn)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)

        self._status_label = QLabel("Ready")
        sb.addWidget(self._status_label, 1)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedWidth(200)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setVisible(False)
        sb.addPermanentWidget(self._progress_bar)

    # ------------------------------------------------------------------
    # File opening
    # ------------------------------------------------------------------

    def _open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Visio File", "", _SUPPORTED
        )
        if path:
            self.open_file(path)

    def open_file(self, path: str) -> None:
        path = os.path.normpath(path)
        if not os.path.exists(path):
            QMessageBox.warning(self, "File Not Found", f"Cannot find:\n{path}")
            return

        self._close_file()
        self.setWindowTitle(f"{Path(path).name} — {_APP_NAME}")
        self._status_label.setText(f"Converting {Path(path).name}…")
        self._web_viewer.show_loading()
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)

        self._worker = ConversionWorker(path, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.page_ready.connect(self._on_page_ready)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

        self._add_to_recent(path)

    def _close_file(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker = None
        self._pages.clear()
        self._current_page = 0
        self._thumbnail_panel.clear()
        self._web_viewer._show_empty()
        self._update_nav_controls()
        self.setWindowTitle(_APP_NAME)
        self._status_label.setText("Ready")
        self._progress_bar.setVisible(False)

    # ------------------------------------------------------------------
    # Worker slots
    # ------------------------------------------------------------------

    def _on_progress(self, pct: int) -> None:
        self._progress_bar.setValue(pct)

    def _on_page_ready(self, index: int, name: str, svg: str) -> None:
        self._thumbnail_panel.add_page(index, name, svg)
        if index == 0:
            # Show first page immediately as it arrives
            self._show_page_svg(svg, index)

    def _on_finished(self, pages: list) -> None:
        self._pages = pages
        self._progress_bar.setVisible(False)
        total = len(pages)
        self._status_label.setText(
            f"Loaded {total} page{'s' if total != 1 else ''}"
        )
        self._update_nav_controls()
        # Ensure first page is visible
        if self._pages:
            self._show_page(0)

    def _on_error(self, msg: str) -> None:
        self._progress_bar.setVisible(False)
        self._status_label.setText("Conversion failed")
        QMessageBox.critical(
            self,
            "Conversion Error",
            f"Failed to convert the file:\n\n{msg}",
        )
        self._web_viewer._show_empty()

    # ------------------------------------------------------------------
    # Page navigation
    # ------------------------------------------------------------------

    def _show_page(self, index: int) -> None:
        if 0 <= index < len(self._pages):
            self._current_page = index
            self._show_page_svg(self._pages[index].svg, index)
            self._thumbnail_panel.select_page(index)
            self._update_nav_controls()

    def _show_page_svg(self, svg: str, index: int) -> None:
        self._web_viewer.load_page(svg)
        total = max(len(self._pages), self._thumbnail_panel.page_count())
        if total > 0:
            self._page_label.setText(f"  {index + 1} / {total}  ")

    def _on_page_selected(self, index: int) -> None:
        if 0 <= index < len(self._pages):
            self._current_page = index
            self._show_page_svg(self._pages[index].svg, index)
            self._update_nav_controls()

    def _prev_page(self) -> None:
        self._show_page(self._current_page - 1)

    def _next_page(self) -> None:
        self._show_page(self._current_page + 1)

    def _update_nav_controls(self) -> None:
        total = len(self._pages)
        has_pages = total > 0
        self._prev_btn.setEnabled(has_pages and self._current_page > 0)
        self._next_btn.setEnabled(has_pages and self._current_page < total - 1)
        if has_pages:
            self._page_label.setText(f"  {self._current_page + 1} / {total}  ")
        else:
            self._page_label.setText("  —  ")

    # ------------------------------------------------------------------
    # Drag & drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(
                u.toLocalFile().lower().endswith((".vsdx", ".vsd"))
                for u in urls
            ):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local.lower().endswith((".vsdx", ".vsd")):
                self.open_file(local)
                break
        event.acceptProposedAction()

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
            self._prev_page()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_PageDown):
            self._next_page()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Recent files
    # ------------------------------------------------------------------

    def _add_to_recent(self, path: str) -> None:
        if path in self._recent:
            self._recent.remove(path)
        self._recent.insert(0, path)
        self._recent = self._recent[:_RECENT_MAX]
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self) -> None:
        self._recent_menu.clear()
        self._recent_menu.setEnabled(bool(self._recent))
        for path in self._recent:
            act = QAction(Path(path).name, self)
            act.setToolTip(path)
            act.setData(path)
            act.triggered.connect(self._open_recent)
            self._recent_menu.addAction(act)

    def _open_recent(self) -> None:
        act = self.sender()
        if act:
            self.open_file(act.data())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Required before QApplication for WebEngine on some platforms
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

    app = QApplication(sys.argv)
    app.setApplicationName(_APP_NAME)
    app.setOrganizationName("mcngn2csc2-cmyk")

    win = MainWindow()
    win.show()

    # Open file passed on the command line
    if len(sys.argv) > 1:
        QTimer.singleShot(100, lambda: win.open_file(sys.argv[1]))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
