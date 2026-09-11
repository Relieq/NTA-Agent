"""Schema-driven Protocol Buffers codec for the NTA game protocol.

The game speaks protobuf (protobuf.js). Rather than depend on protoc, we drive a
small pure-Python codec from `schema.json`, which is reconstructed from the
decrypted protobuf.js module by ``tools/re/parse_schema.py``. This keeps us
resilient to schema drift (unknown fields are skipped, not fatal) and needs no
build step.

Public API::

    codec = Codec.load()                 # loads schema.json next to this file
    body = codec.encode("GAME_HD_UPAREABUILD_C2S", {"index": 3, "uid": "..."})
    msg = codec.decode("LOBBY_HD_TRYLOGIN_S2C", body)
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).with_name("schema.json")

# proto type -> wire type
_WIRE = {
    "int32": 0, "int64": 0, "uint32": 0, "uint64": 0, "sint32": 0, "sint64": 0,
    "bool": 0, "enum": 0,
    "fixed64": 1, "sfixed64": 1, "double": 1,
    "string": 2, "bytes": 2, "message": 2,
    "fixed32": 5, "sfixed32": 5, "float": 5,
}


# --------------------------------------------------------------------------- #
# wire primitives
# --------------------------------------------------------------------------- #
def _enc_varint(n: int) -> bytes:
    if n < 0:
        n += 1 << 64  # two's complement for negative int32/int64
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _zigzag(n: int) -> int:
    return (n << 1) ^ (n >> 63) if n < 0 else (n << 1)


def _unzigzag(n: int) -> int:
    return (n >> 1) ^ -(n & 1)


class _Reader:
    __slots__ = ("buf", "n", "pos")

    def __init__(self, buf: bytes):
        self.buf = buf
        self.pos = 0
        self.n = len(buf)

    def varint(self) -> int:
        result = shift = 0
        while True:
            b = self.buf[self.pos]
            self.pos += 1
            result |= (b & 0x7F) << shift
            if not (b & 0x80):
                return result
            shift += 7

    def bytes_(self) -> bytes:
        ln = self.varint()
        b = self.buf[self.pos:self.pos + ln]
        self.pos += ln
        return b

    def fixed(self, size: int) -> bytes:
        b = self.buf[self.pos:self.pos + size]
        self.pos += size
        return b

    def skip(self, wire: int) -> None:
        if wire == 0:
            self.varint()
        elif wire == 1:
            self.pos += 8
        elif wire == 2:
            self.pos += self.varint()
        elif wire == 5:
            self.pos += 4
        else:
            raise ValueError("bad wire type %d" % wire)


def _as_signed(n: int, bits: int) -> int:
    if n >= (1 << (bits - 1)):
        n -= 1 << bits
    return n


# --------------------------------------------------------------------------- #
# codec
# --------------------------------------------------------------------------- #
class Codec:
    def __init__(self, schema: dict[str, Any]):
        self.schema = schema

    @classmethod
    def load(cls, path: Path | str | None = None) -> Codec:
        p = Path(path) if path else _SCHEMA_PATH
        if not p.exists():
            raise FileNotFoundError(
                "schema.json not found at %s — regenerate via tools/re/parse_schema.py" % p
            )
        return cls(json.loads(p.read_text(encoding="utf-8")))

    def has(self, msg: str) -> bool:
        return msg in self.schema

    def _fields(self, msg: str) -> list[dict]:
        try:
            return self.schema[msg]["fields"]
        except KeyError:
            raise KeyError("unknown message type: %s" % msg)

    # ---- encode ---------------------------------------------------------- #
    def encode(self, msg: str, data: dict[str, Any]) -> bytes:
        out = bytearray()
        for f in self._fields(msg):
            if f["name"] not in data or data[f["name"]] is None:
                continue
            val = data[f["name"]]
            self._encode_field(out, f, val)
        return bytes(out)

    def _tag(self, num: int, wire: int) -> bytes:
        return _enc_varint((num << 3) | wire)

    def _encode_scalar_value(self, out: bytearray, typ: str, val: Any) -> None:
        if typ in ("int32", "int64", "uint32", "uint64", "enum", "bool"):
            out += _enc_varint(int(val))
        elif typ in ("sint32", "sint64"):
            out += _enc_varint(_zigzag(int(val)))
        elif typ == "string":
            b = val.encode("utf-8") if isinstance(val, str) else bytes(val)
            out += _enc_varint(len(b)) + b
        elif typ == "bytes":
            b = bytes(val)
            out += _enc_varint(len(b)) + b
        elif typ in ("fixed32",):
            out += struct.pack("<I", int(val) & 0xFFFFFFFF)
        elif typ in ("sfixed32",):
            out += struct.pack("<i", int(val))
        elif typ == "float":
            out += struct.pack("<f", float(val))
        elif typ in ("fixed64",):
            out += struct.pack("<Q", int(val) & 0xFFFFFFFFFFFFFFFF)
        elif typ in ("sfixed64",):
            out += struct.pack("<q", int(val))
        elif typ == "double":
            out += struct.pack("<d", float(val))
        else:
            raise ValueError("cannot encode scalar type %s" % typ)

    def _encode_field(self, out: bytearray, f: dict, val: Any) -> None:
        typ, num, rule = f["type"], f["num"], f["rule"]
        if typ == "message":
            items = val if rule == "repeated" else [val]
            for item in items:
                body = self.encode(f["sub"], item)
                out += self._tag(num, 2) + _enc_varint(len(body)) + body
        elif typ == "map":
            for k, v in val.items():
                entry = bytearray()
                self._encode_field_kv(entry, 1, f["keytype"], k)
                if f["valtype"] == "message":
                    vb = self.encode(f["sub"], v)
                    entry += self._tag(2, 2) + _enc_varint(len(vb)) + vb
                else:
                    self._encode_field_kv(entry, 2, f["valtype"], v)
                out += self._tag(num, 2) + _enc_varint(len(entry)) + bytes(entry)
        elif rule == "repeated":
            wire = _WIRE[typ]
            if wire in (0, 1, 5):  # packed
                packed = bytearray()
                for item in val:
                    self._encode_scalar_value(packed, typ, item)
                out += self._tag(num, 2) + _enc_varint(len(packed)) + bytes(packed)
            else:  # repeated string/bytes are not packed
                for item in val:
                    out += self._tag(num, wire)
                    self._encode_scalar_value(out, typ, item)
        else:
            wire = _WIRE[typ]
            out += self._tag(num, wire)
            self._encode_scalar_value(out, typ, val)

    def _encode_field_kv(self, out: bytearray, num: int, typ: str, val: Any) -> None:
        wire = _WIRE[typ]
        out += self._tag(num, wire)
        self._encode_scalar_value(out, typ, val)

    # ---- decode ---------------------------------------------------------- #
    def decode(self, msg: str, buf: bytes) -> dict[str, Any]:
        by_num = {f["num"]: f for f in self._fields(msg)}
        r = _Reader(buf)
        result: dict[str, Any] = {}
        while r.pos < r.n:
            tag = r.varint()
            num, wire = tag >> 3, tag & 7
            f = by_num.get(num)
            if f is None:
                r.skip(wire)
                continue
            self._decode_field(r, f, wire, result)
        return result

    def _read_scalar(self, r: _Reader, typ: str) -> Any:
        if typ in ("int32", "int64", "uint32", "uint64", "enum"):
            v = r.varint()
            if typ == "int32":
                return _as_signed(v & 0xFFFFFFFF, 32)
            if typ == "int64":
                return _as_signed(v, 64)
            return v
        if typ == "bool":
            return bool(r.varint())
        if typ in ("sint32", "sint64"):
            return _unzigzag(r.varint())
        if typ == "string":
            return r.bytes_().decode("utf-8", "replace")
        if typ == "bytes":
            return r.bytes_()
        if typ == "fixed32":
            return struct.unpack("<I", r.fixed(4))[0]
        if typ == "sfixed32":
            return struct.unpack("<i", r.fixed(4))[0]
        if typ == "float":
            return struct.unpack("<f", r.fixed(4))[0]
        if typ == "fixed64":
            return struct.unpack("<Q", r.fixed(8))[0]
        if typ == "sfixed64":
            return struct.unpack("<q", r.fixed(8))[0]
        if typ == "double":
            return struct.unpack("<d", r.fixed(8))[0]
        raise ValueError("cannot decode scalar type %s" % typ)

    def _decode_field(self, r: _Reader, f: dict, wire: int, result: dict) -> None:
        typ, name, rule = f["type"], f["name"], f["rule"]
        if typ == "message":
            sub = self.decode(f["sub"], r.bytes_())
            if rule == "repeated":
                result.setdefault(name, []).append(sub)
            else:
                result[name] = sub
        elif typ == "map":
            entry = _Reader(r.bytes_())
            key = val = None
            while entry.pos < entry.n:
                t = entry.varint()
                fn, w = t >> 3, t & 7
                if fn == 1:
                    key = self._read_scalar(entry, f["keytype"])
                elif fn == 2:
                    if f["valtype"] == "message":
                        val = self.decode(f["sub"], entry.bytes_())
                    else:
                        val = self._read_scalar(entry, f["valtype"])
                else:
                    entry.skip(w)
            result.setdefault(name, {})[key] = val
        elif rule == "repeated":
            lst = result.setdefault(name, [])
            if wire == 2 and _WIRE[typ] != 2:  # packed
                packed = _Reader(r.bytes_())
                while packed.pos < packed.n:
                    lst.append(self._read_scalar(packed, typ))
            else:
                lst.append(self._read_scalar(r, typ))
        else:
            result[name] = self._read_scalar(r, typ)
