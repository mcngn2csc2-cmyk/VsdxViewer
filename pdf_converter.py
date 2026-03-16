"""
pdf_converter.py — Visio COM + PyMuPDF でVSDXをページ画像に変換。

Visio (win32com) でPDFに書き出し、PyMuPDF (fitz) で各ページをPNG画像に
レンダリングする。印刷範囲がそのまま画像サイズになるため、SVG変換での
表示崩れを回避できる。

Requirements:
    pip install pywin32 PyMuPDF
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from converter import PageInfo


def convert_vsdx_via_visio(path: str | os.PathLike) -> List["PageInfo"]:
    """Visio COM経由でVSDXを変換し、ページごとのPNG画像を持つPageInfoリストを返す。

    Raises
    ------
    ImportError  : win32com または PyMuPDF が未インストール
    RuntimeError : Visioが起動できない、またはPDF変換に失敗
    """
    try:
        import win32com.client  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "pywin32 が未インストールです。pip install pywin32 を実行してください。"
        ) from exc

    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError as exc:
        raise ImportError(
            "PyMuPDF が未インストールです。pip install PyMuPDF を実行してください。"
        ) from exc

    abs_path = str(Path(path).resolve())

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "output.pdf")
        page_names = _export_pdf_via_visio(win32com, abs_path, pdf_path)
        return _render_pdf_pages(fitz, pdf_path, page_names)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _export_pdf_via_visio(win32com, vsdx_path: str, pdf_path: str) -> List[str]:
    """VisioのCOMオートメーションでPDFに書き出し、ページ名リストを返す。"""
    try:
        visio = win32com.client.Dispatch("Visio.Application")
    except Exception as exc:
        raise RuntimeError(
            f"Microsoft Visio を起動できませんでした: {exc}"
        ) from exc

    visio.Visible = False
    try:
        doc = visio.Documents.Open(vsdx_path)
        try:
            # ページ名を取得（Visio COMは1-indexed）
            page_count = doc.Pages.Count
            page_names = [doc.Pages[i + 1].Name for i in range(page_count)]

            # ExportAsFixedFormat(Format, OutputPath, Intent, PrintRange)
            #   visFixedFormatPDF=1, visFixedFormatIntentPrint=1, visPrintAll=0
            doc.ExportAsFixedFormat(1, pdf_path, 1, 0)
            return page_names
        finally:
            doc.Close(False)  # False = 変更を保存しない
    finally:
        visio.Quit()


def _render_pdf_pages(fitz, pdf_path: str, page_names: List[str]) -> List["PageInfo"]:
    """PyMuPDFで各ページを高解像度PNG画像にレンダリングしてPageInfoリストを返す。"""
    # ここで循環インポートを避けるためにローカルインポート
    from converter import PageInfo  # noqa: PLC0415

    pdf_doc = fitz.open(pdf_path)
    pages: List[PageInfo] = []
    mat = fitz.Matrix(150 / 72, 150 / 72)  # 150 DPI

    for i in range(len(pdf_doc)):
        pix = pdf_doc[i].get_pixmap(matrix=mat, alpha=False)
        png_bytes = pix.tobytes("png")
        name = page_names[i] if i < len(page_names) else f"ページ {i + 1}"
        pages.append(PageInfo(index=i, name=name, png_bytes=png_bytes))

    pdf_doc.close()
    return pages
