"""Decode (and, for synthetic data, encode) the `attributedBody` column of chat.db.

Since macOS Ventura, many messages have `text = NULL` and keep their text only in
`attributedBody`: an NSAttributedString serialized with NSArchiver's "typedstream"
format. The fast path below pulls the NSString payload out directly; if that fails we
fall back to a full typedstream parser (pytypedstream).
"""

from __future__ import annotations

# typedstream tags
_TAG_INT16 = 0x81
_TAG_INT32 = 0x82

# "+" is the type encoding typedstream uses for the raw string bytes inside NSString.
_STRING_BYTES_TYPE = b"\x84\x01+"


def _read_int(blob: bytes, pos: int) -> tuple[int, int]:
    """Read a typedstream integer at `pos`. Returns (value, next_pos)."""
    head = blob[pos]
    if head == _TAG_INT16:
        return int.from_bytes(blob[pos + 1 : pos + 3], "little", signed=True), pos + 3
    if head == _TAG_INT32:
        return int.from_bytes(blob[pos + 1 : pos + 5], "little", signed=True), pos + 5
    return head, pos + 1


def _write_int(n: int) -> bytes:
    if 0 <= n < 0x80:
        return bytes([n])
    if -0x8000 <= n < 0x8000:
        return bytes([_TAG_INT16]) + n.to_bytes(2, "little", signed=True)
    return bytes([_TAG_INT32]) + n.to_bytes(4, "little", signed=True)


def _decode_fast(blob: bytes) -> str | None:
    start = blob.find(b"NSString")
    if start < 0:
        start = blob.find(b"NSMutableString")
    if start < 0:
        return None
    marker = blob.find(_STRING_BYTES_TYPE, start)
    if marker < 0:
        return None
    length, pos = _read_int(blob, marker + len(_STRING_BYTES_TYPE))
    if length < 0 or pos + length > len(blob):
        return None
    return blob[pos : pos + length].decode("utf-8")


def _decode_typedstream(blob: bytes) -> str | None:
    try:
        import typedstream
    except ImportError:
        return None
    try:
        obj = typedstream.unarchive_from_data(blob)
    except Exception:
        return None
    for item in getattr(obj, "contents", []):
        value = getattr(item, "value", None)
        if type(value).__name__ in ("NSString", "NSMutableString"):
            return value.value
    return None


def decode(blob: bytes | None) -> tuple[str | None, str]:
    """Return (text, method) where method is 'fast', 'typedstream', or 'failed'."""
    if not blob:
        return None, "failed"
    try:
        text = _decode_fast(blob)
    except (UnicodeDecodeError, IndexError):
        text = None
    if text is not None:
        return text, "fast"
    text = _decode_typedstream(blob)
    if text is not None:
        return text, "typedstream"
    return None, "failed"


def encode(text: str) -> bytes:
    """Build an attributedBody blob shaped like the ones Messages writes (synthetic data only)."""
    raw = text.encode("utf-8")
    utf16_len = len(text.encode("utf-16-le")) // 2
    return b"".join(
        [
            b"\x04\x0bstreamtyped\x81\xe8\x03",
            b"\x84\x01@\x84\x84\x84\x12NSAttributedString\x00",
            b"\x84\x84\x08NSObject\x00\x85\x92",
            b"\x84\x84\x84\x08NSString\x01\x94",
            _STRING_BYTES_TYPE,
            _write_int(len(raw)),
            raw,
            b"\x86\x84\x02iI\x01",
            _write_int(utf16_len),
            b"\x92\x84\x84\x84\x0cNSDictionary\x00\x94\x84\x01i\x01\x92\x84\x96\x96",
            b"\x1d__kIMMessagePartAttributeName\x86\x92",
            b"\x84\x84\x84\x08NSNumber\x00\x84\x84\x07NSValue\x00\x94\x84\x01*\x84\x99\x99\x00",
            b"\x86\x86\x86",
        ]
    )
