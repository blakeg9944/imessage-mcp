import pytest

from imessage_mcp import attributed_body as ab

# A blob in exactly the shape Messages writes, for the text "Hello".
REAL_SHAPE = bytes.fromhex(
    "040B73747265616D747970656481E803840140848484124E5341747472696275746564537472696E67008484084E534F"
    "626A65637400859284848408"
    "4E53537472696E67019484012B0548656C6C6F8684026949010592848484"
    "0C4E5344696374696F6E617279009484016901928496961D5F5F6B494D4D6573736167655061727441747472696275"
    "74654E616D658692848484084E534E756D626572008484074E5356616C7565009484012A849999008686 86".replace(" ", "")
)


def test_decodes_real_shaped_blob():
    assert ab.decode(REAL_SHAPE) == ("Hello", "fast")


@pytest.mark.parametrize("text", ["", "hi", "wifi BlueHeron_2291 😂", "é" * 300, "x" * 40000, "line1\nline2"])
def test_round_trip_matches_full_parser(text):
    blob = ab.encode(text)
    assert ab._decode_fast(blob) == text
    assert ab._decode_typedstream(blob) == text  # independent typedstream parser agrees


def test_falls_back_when_fast_path_fails(monkeypatch):
    monkeypatch.setattr(ab, "_decode_fast", lambda blob: None)
    assert ab.decode(ab.encode("fallback works")) == ("fallback works", "typedstream")


def test_garbage_and_empty():
    assert ab.decode(None) == (None, "failed")
    assert ab.decode(b"\x00\x01garbage")[1] == "failed"
