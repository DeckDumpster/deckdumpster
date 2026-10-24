"""Stream the members of one top-level object out of a large JSON document.

MTGJSON's AllPrintings and AllPricesToday are single objects of the shape
``{"meta": {...}, "data": {<key>: <value>, ...}}``. ``json.load`` materialises
the whole thing, which put the price import at 12.5 GB RSS. This yields one
``(key, value)`` member of ``data`` at a time, so memory is bounded by the
largest single member (one set, one uuid's price history), not the document.
"""

import json
from json import JSONDecodeError

_DECODER = json.JSONDecoder()
_WS = " \t\r\n"
_CHUNK = 1 << 20


class _Reader:
    def __init__(self, f):
        self.f = f
        self.buf = ""
        self.pos = 0
        self.eof = False

    def fill(self, want=_CHUNK):
        if self.eof:
            return False
        chunk = self.f.read(max(want, _CHUNK))
        if not chunk:
            self.eof = True
            return False
        self.buf = self.buf[self.pos:] + chunk
        self.pos = 0
        return True

    def skip_ws(self):
        while True:
            while self.pos < len(self.buf) and self.buf[self.pos] in _WS:
                self.pos += 1
            if self.pos < len(self.buf):
                return
            if not self.fill():
                raise JSONDecodeError("unexpected end of document", self.buf, self.pos)

    def peek(self):
        self.skip_ws()
        return self.buf[self.pos]

    def expect(self, ch):
        if self.peek() != ch:
            raise JSONDecodeError(f"expected {ch!r}", self.buf, self.pos)
        self.pos += 1

    def value(self):
        """Decode the next JSON value, reading more input until it is whole."""
        self.skip_ws()
        want = _CHUNK
        while True:
            try:
                val, end = _DECODER.raw_decode(self.buf, self.pos)
            except JSONDecodeError:
                if not self.fill(want):
                    raise
                want = len(self.buf)
                continue
            # A bare number at the end of the buffer may be cut short.
            if end == len(self.buf) and self.buf[self.pos] not in '{["' and self.fill(want):
                continue
            self.pos = end
            return val


def iter_object_members(f, key):
    """Yield ``(k, v)`` for each member of the top-level object's ``key`` member.

    Other top-level members are decoded and discarded one at a time.
    """
    r = _Reader(f)
    r.expect("{")
    if r.peek() == "}":
        return
    while True:
        name = r.value()
        r.expect(":")
        if name == key:
            r.expect("{")
            if r.peek() == "}":
                r.pos += 1
            else:
                while True:
                    k = r.value()
                    r.expect(":")
                    yield k, r.value()
                    if r.peek() == ",":
                        r.pos += 1
                        continue
                    r.expect("}")
                    break
        else:
            r.value()
        if r.peek() == ",":
            r.pos += 1
            continue
        r.expect("}")
        return
