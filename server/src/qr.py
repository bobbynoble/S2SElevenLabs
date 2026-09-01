"""Join-URL and QR PNG generation. Kept server-side so the frontend needs no QR dependency."""

from __future__ import annotations

import io
import os

import qrcode

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")


def build_join_url(token: str) -> str:
    return f"{FRONTEND_ORIGIN}/join/{token}"


def generate_qr_png(url: str) -> bytes:
    img = qrcode.make(url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
