"""
preview_extractor.py — VSDXの内蔵プレビュー画像を抽出してPNGに変換。

VSDXはZIPアーカイブ。プレビュー画像の格納場所:
  - visio/pages/page{N}.emf  : ページ個別プレビュー（Visio 2013+）
  - docProps/thumbnail.emf   : ドキュメント全体サムネイル（フォールバック）

EMF → PNG 変換は Windows GDI32 (ctypes) を使用。追加依存なし。

制限:
  - Windows専用（GDI32依存）
  - ページ個別プレビューはVisio 2013+で保存された場合のみ存在
  - docProps/thumbnail.emf のみの場合は1枚の低解像度サムネイルになる
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import io
import struct
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path
from typing import List, Optional, Tuple


def extract_preview_pages(path) -> List[Tuple[str, bytes]]:
    """VSDXからプレビュー画像を抽出し、(page_name, png_bytes) のリストを返す。

    Raises
    ------
    RuntimeError : プレビュー画像が見つからない、またはOS非対応
    """
    import sys
    if sys.platform != "win32":
        raise RuntimeError("プレビュー抽出はWindowsのみ対応しています。")

    with zipfile.ZipFile(Path(path), "r") as z:
        names = set(z.namelist())
        page_names = _get_page_names(z)

        # ページ個別のEMFプレビューを探す
        page_emfs = _find_page_emfs(z, names)
        if page_emfs:
            results = []
            for i, emf_data in enumerate(page_emfs):
                name = page_names[i] if i < len(page_names) else f"ページ {i + 1}"
                png = _emf_to_png(emf_data)
                results.append((name, png))
            return results

        # フォールバック: ドキュメントサムネイル
        for thumbnail_path in ("docProps/thumbnail.emf", "docProps/thumbnail.wmf"):
            if thumbnail_path in names:
                emf_data = z.read(thumbnail_path)
                name = page_names[0] if page_names else "Page 1"
                png = _emf_to_png(emf_data)
                return [(name, png)]

    raise RuntimeError(
        "VSDXファイルにプレビュー画像が見つかりませんでした。\n"
        "このファイルはVisio 2013以前で作成されているか、"
        "プレビュー画像が保存されていない可能性があります。"
    )


# ---------------------------------------------------------------------------
# VSDX 内部パース
# ---------------------------------------------------------------------------

def _find_page_emfs(z: zipfile.ZipFile, names: set) -> List[bytes]:
    """visio/pages/page{N}.emf を順番に読み込む。"""
    results = []
    i = 1
    while True:
        emf_path = f"visio/pages/page{i}.emf"
        if emf_path not in names:
            break
        results.append(z.read(emf_path))
        i += 1
    return results


def _get_page_names(z: zipfile.ZipFile) -> List[str]:
    """visio/document.xml からページ名リストを取得する。失敗時は空リストを返す。"""
    try:
        xml_data = z.read("visio/document.xml")
    except KeyError:
        return []

    try:
        root = ET.fromstring(xml_data)
        # Visio XMLの名前空間
        ns = {"v": "http://schemas.microsoft.com/office/visio/2012/main"}
        pages = root.find(".//v:Pages", ns)
        if pages is None:
            # 名前空間なしで再試行
            pages = root.find(".//Pages")
        if pages is None:
            return []

        names = []
        for page in pages:
            name = page.get("Name") or page.get("NameU") or ""
            names.append(name)
        return names
    except Exception:
        return []


# ---------------------------------------------------------------------------
# EMF → PNG 変換（Windows GDI32）
# ---------------------------------------------------------------------------

class _RECTL(ctypes.Structure):
    _fields_ = [
        ("left", wt.LONG),
        ("top", wt.LONG),
        ("right", wt.LONG),
        ("bottom", wt.LONG),
    ]


class _SIZEL(ctypes.Structure):
    _fields_ = [("cx", wt.LONG), ("cy", wt.LONG)]


class _ENHMETAHEADER(ctypes.Structure):
    _fields_ = [
        ("iType", wt.DWORD),
        ("nSize", wt.DWORD),
        ("rclBounds", _RECTL),
        ("rclFrame", _RECTL),   # 0.01mm単位
        ("dSignature", wt.DWORD),
        ("nVersion", wt.DWORD),
        ("nBytes", wt.DWORD),
        ("nRecords", wt.DWORD),
        ("nHandles", wt.WORD),
        ("sReserved", wt.WORD),
        ("nDescription", wt.DWORD),
        ("offDescription", wt.DWORD),
        ("nPalEntries", wt.DWORD),
        ("szlDevice", _SIZEL),
        ("szlMillimeters", _SIZEL),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", wt.LONG),
        ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD),
        ("biBitCount", wt.WORD),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


def _emf_to_png(emf_data: bytes, dpi: int = 150) -> bytes:
    """Windows GDI32 APIを使ってEMFバイト列をPNGに変換する。"""
    gdi32 = ctypes.windll.gdi32
    user32 = ctypes.windll.user32

    # EMFをメモリからロード
    hemf = gdi32.SetEnhMetaFileBits(len(emf_data), emf_data)
    if not hemf:
        raise RuntimeError("SetEnhMetaFileBits に失敗しました（不正なEMFデータの可能性）。")

    try:
        width_px, height_px = _get_emf_size_px(gdi32, hemf, dpi)
        return _render_emf(gdi32, user32, hemf, width_px, height_px)
    finally:
        gdi32.DeleteEnhMetaFile(hemf)


def _get_emf_size_px(gdi32, hemf, dpi: int) -> Tuple[int, int]:
    """EMFヘッダからピクセルサイズを計算する。"""
    header = _ENHMETAHEADER()
    size = gdi32.GetEnhMetaFileHeader(hemf, ctypes.sizeof(header), ctypes.byref(header))
    if size == 0:
        return (800, 600)

    # rclFrame は 0.01mm 単位
    w_mm = (header.rclFrame.right - header.rclFrame.left) / 100.0
    h_mm = (header.rclFrame.bottom - header.rclFrame.top) / 100.0

    if w_mm > 0 and h_mm > 0:
        w_px = int(w_mm * dpi / 25.4)
        h_px = int(h_mm * dpi / 25.4)
    else:
        # rclBoundsから推定（ピクセル単位だが解像度不明）
        w_px = abs(header.rclBounds.right - header.rclBounds.left)
        h_px = abs(header.rclBounds.bottom - header.rclBounds.top)

    # 極端に小さい・大きいサイズをクランプ
    MAX_PX = 4096
    w_px = max(100, min(w_px, MAX_PX))
    h_px = max(100, min(h_px, MAX_PX))
    return (w_px, h_px)


def _render_emf(gdi32, user32, hemf, width_px: int, height_px: int) -> bytes:
    """EMFをメモリDCにレンダリングし、PNG bytes を返す。"""
    # スクリーンDCを参照用に取得
    hdc_screen = user32.GetDC(None)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)

    # 24bit DIBSectionを作成
    bmi = _BITMAPINFOHEADER(
        biSize=ctypes.sizeof(_BITMAPINFOHEADER),
        biWidth=width_px,
        biHeight=-height_px,   # 負 = トップダウン
        biPlanes=1,
        biBitCount=24,
        biCompression=0,       # BI_RGB
    )
    ppv_bits = ctypes.c_void_p()
    hbm = gdi32.CreateDIBSection(
        hdc_mem,
        ctypes.byref(bmi),
        0,                     # DIB_RGB_COLORS
        ctypes.byref(ppv_bits),
        None,
        0,
    )

    if not hbm:
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)
        raise RuntimeError("CreateDIBSection に失敗しました。")

    old_bm = gdi32.SelectObject(hdc_mem, hbm)

    # 白背景で塗りつぶし（GetStockObject(0) = WHITE_BRUSH）
    white_brush = gdi32.GetStockObject(0)
    bg_rect = _RECTL(0, 0, width_px, height_px)
    user32.FillRect(hdc_mem, ctypes.byref(bg_rect), white_brush)

    # EMFを描画
    play_rect = _RECTL(0, 0, width_px, height_px)
    gdi32.PlayEnhMetaFile(hdc_mem, hemf, ctypes.byref(play_rect))

    # ビットマップデータを取得
    stride = ((width_px * 3 + 3) // 4) * 4   # 4バイトアライン
    buf_size = stride * height_px
    raw = (ctypes.c_ubyte * buf_size).from_address(ppv_bits.value)
    raw_bytes = bytes(raw)

    # クリーンアップ
    gdi32.SelectObject(hdc_mem, old_bm)
    gdi32.DeleteObject(hbm)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(None, hdc_screen)

    return _bgr24_to_png(raw_bytes, width_px, height_px, stride)


# ---------------------------------------------------------------------------
# 純Python PNG エンコーダ（追加依存なし）
# ---------------------------------------------------------------------------

def _bgr24_to_png(raw: bytes, width: int, height: int, stride: int) -> bytes:
    """BGR24 DIBデータをPNGバイト列に変換する（純Python、依存なし）。"""

    def make_chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    # IHDR: width, height, bit_depth=8, color_type=2(RGB), compress=0, filter=0, interlace=0
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)

    # 各行を BGR → RGB 変換しフィルタバイト0を付ける
    rows = bytearray()
    for row_idx in range(height):
        rows.append(0)  # filter = None
        offset = row_idx * stride
        row_bgr = bytearray(raw[offset: offset + width * 3])
        row_rgb = bytearray(width * 3)
        row_rgb[0::3] = row_bgr[2::3]   # R
        row_rgb[1::3] = row_bgr[1::3]   # G
        row_rgb[2::3] = row_bgr[0::3]   # B
        rows += row_rgb

    idat = zlib.compress(bytes(rows), 6)

    return (
        b"\x89PNG\r\n\x1a\n"
        + make_chunk(b"IHDR", ihdr)
        + make_chunk(b"IDAT", idat)
        + make_chunk(b"IEND", b"")
    )
