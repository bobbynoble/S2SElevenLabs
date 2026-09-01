from src.qr import build_join_url, generate_qr_png


def test_build_join_url_embeds_token():
    url = build_join_url("abc123")
    assert url.endswith("/join/abc123")


def test_generate_qr_png_returns_valid_png_bytes():
    png_bytes = generate_qr_png("https://example.com/join/abc123")
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png_bytes) > 100
