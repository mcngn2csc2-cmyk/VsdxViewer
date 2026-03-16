"""
worker.py — QThread-based asynchronous VSDX conversion worker.

Signals
-------
progress(int)
    0-100 percentage (emitted before and after conversion).
page_ready(object)
    PageInfo — emitted for each converted page.
finished(list)
    Full list of PageInfo once all pages are done.
error(str)
    Human-readable error message if conversion fails.
"""

from __future__ import annotations

from typing import List

from PySide6.QtCore import QThread, Signal

from converter import PageInfo, convert_vsdx


class ConversionWorker(QThread):
    """Run :func:`convert_vsdx` off the main thread."""

    progress = Signal(int)       # 0-100
    page_ready = Signal(object)  # PageInfo
    finished = Signal(list)      # list[PageInfo]
    error = Signal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path
        self._pages: List[PageInfo] = []

    # ------------------------------------------------------------------
    # QThread interface
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            self.progress.emit(5)
            pages: List[PageInfo] = convert_vsdx(self._path)
            total = max(len(pages), 1)
            for page in pages:
                if self.isInterruptionRequested():
                    return
                self._pages.append(page)
                self.page_ready.emit(page)
                pct = 5 + int(90 * (page.index + 1) / total)
                self.progress.emit(pct)
            self.progress.emit(100)
            self.finished.emit(list(self._pages))
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def stop(self) -> None:
        """Request cancellation and wait for the thread to finish."""
        self.requestInterruption()
        self.wait(3000)
