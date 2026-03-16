"""
converter.py — VSDX → SVG conversion using libvisio-ng.

Returns a list of PageInfo named-tuples:
    PageInfo(index: int, name: str, svg: str)

libvisio-ng exposes either:
  • libvisio_ng.convert(path) -> list[tuple[str, str]]   (name, svg_xml)
  • libvisio_ng.Converter().run(path) -> same
We try both signatures and fall back with a clear error.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class PageInfo:
    index: int
    name: str
    svg: str = ""            # SVG文字列（SVG変換モード）
    png_bytes: bytes = b""   # PNG画像データ（Visio COMモード）


def convert_vsdx(path: str | os.PathLike) -> List[PageInfo]:
    """Convert *path* (.vsdx) and return one :class:`PageInfo` per page.

    Visio COM（win32com + PyMuPDF）が利用可能な場合は印刷範囲に忠実な
    PDF→PNG変換を優先する。利用不可の場合は libvisio-ng によるSVG変換に
    フォールバックする。

    Raises
    ------
    ImportError
        If libvisio-ng is not installed and Visio COM is unavailable.
    RuntimeError
        If the file cannot be converted.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() not in (".vsdx", ".vsd"):
        raise ValueError(f"Unsupported file type: {path.suffix}")

    # Visio COM経由の高品質変換を優先
    try:
        from pdf_converter import convert_vsdx_via_visio  # noqa: PLC0415
        return convert_vsdx_via_visio(path)
    except Exception:
        pass

    # フォールバック: libvisio-ng によるSVG変換
    raw_pages = _run_libvisio_ng(path)
    return [
        PageInfo(index=i, name=name or f"Page {i + 1}", svg=svg)
        for i, (name, svg) in enumerate(raw_pages)
    ]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_libvisio_ng(path: Path):
    """Call libvisio-ng and return [(name, svg_xml), ...]."""
    try:
        import libvisio_ng  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "libvisio-ng is not installed. "
            "Run: pip install 'libvisio-ng>=0.6.0'"
        ) from exc

    # Try the functional API first (most common in >=0.6.0)
    if hasattr(libvisio_ng, "convert"):
        result = libvisio_ng.convert(str(path))
        return _normalise_result(result)

    # Try the class-based API
    if hasattr(libvisio_ng, "Converter"):
        converter = libvisio_ng.Converter()
        run_fn = getattr(converter, "run", None) or getattr(converter, "convert", None)
        if run_fn is not None:
            result = run_fn(str(path))
            return _normalise_result(result)

    # Try convert_file
    if hasattr(libvisio_ng, "convert_file"):
        result = libvisio_ng.convert_file(str(path))
        return _normalise_result(result)

    raise RuntimeError(
        "libvisio-ng is installed but no recognised API was found. "
        "Please check the package version."
    )


def _normalise_result(result) -> list[tuple[str, str]]:
    """Accept the various shapes libvisio-ng may return.

    Accepted forms:
    - list of (name, svg_str) tuples/lists
    - list of svg strings (page names assigned automatically)
    - single svg string (single page)
    - dict like {name: svg_str}
    """
    if result is None:
        raise RuntimeError("libvisio-ng returned None — conversion failed.")

    if isinstance(result, str):
        # Single-page result
        return [("Page 1", result)]

    if isinstance(result, dict):
        return list(result.items())

    pages = list(result)
    if not pages:
        raise RuntimeError("libvisio-ng returned no pages.")

    first = pages[0]
    if isinstance(first, str):
        # Plain list of SVG strings
        return [(f"Page {i + 1}", svg) for i, svg in enumerate(pages)]

    if isinstance(first, (list, tuple)) and len(first) >= 2:
        # Already (name, svg) pairs
        return [(str(p[0]), str(p[1])) for p in pages]

    # Last resort: treat each element as SVG
    return [(f"Page {i + 1}", str(p)) for i, p in enumerate(pages)]
