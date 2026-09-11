"""Parse the decrypted protobuf.js static module (msg.js) into a compact schema.

protobuf.js `decode` functions have a very regular shape we can parse without a
JS engine. The accumulator variable differs per message (i/u/...), so we detect
it from `<var> = new o.proto.<Msg>()`.

Field patterns handled:
    <acc>.F = e.TYPE();                                  singular scalar
    <acc>.F = o.proto.SUB.decode(e, e.uint32());         singular message
    ... <acc>.F.push(e.TYPE())                            repeated scalar
    ... <acc>.F.push(o.proto.SUB.decode(...))             repeated message
    <acc>.F === r.emptyObject && (<acc>.F = {}); ...      map<key,value>

Output: schema.json = { MsgName: {"fields": [ {num,name,type,rule,sub,...} ]} }
  type: scalar name | "message" | "map" | "unknown"
  rule: "single" | "repeated"
  sub:  nested message type when type/valtype == "message"
  keytype/valtype: for maps
"""
from __future__ import annotations

import json
import re
import sys
from itertools import pairwise
from pathlib import Path

SCALAR = {"int32", "uint32", "sint32", "int64", "uint64", "sint64", "bool",
          "string", "bytes", "float", "double", "fixed32", "fixed64",
          "sfixed32", "sfixed64"}

MSG_RE = re.compile(r"i\.([A-Za-z_]\w*) = function\(\)")
# The inner class var varies per message (i/r/u/...), so match any "<var>.decode".
DECODE_RE = re.compile(r"\w+\.decode = function\(e, n\) \{(.*?)\n\};", re.DOTALL)
CASE_RE = re.compile(r"case (\d+):(.*?)(?=case \d+:|default:|\Z)", re.DOTALL)


def parse_case(num, body, acc):
    v = re.escape(acc)
    # map: <acc>.NAME === r.emptyObject && (<acc>.NAME = {}); key=e.KT(); value...
    m = re.search(v + r"\.(\w+) === r\.emptyObject", body)
    if m:
        name = m.group(1)
        kt = re.search(r"= e\.(\w+)\(\)", body)
        keyt = kt.group(1) if kt else "string"
        vm = re.search(r"o\.proto\.([A-Za-z_]\w*)\.decode\(", body)
        if vm:
            return dict(num=num, name=name, type="map", rule="single",
                        keytype=keyt, valtype="message", sub=vm.group(1))
        vt = re.findall(r"= e\.(\w+)\(\)", body)
        valt = vt[1] if len(vt) > 1 else "string"
        return dict(num=num, name=name, type="map", rule="single",
                    keytype=keyt, valtype=valt, sub=None)
    # repeated message
    m = re.search(r"\.push\(o\.proto\.([A-Za-z_]\w*)\.decode\(", body)
    if m:
        nm = re.search(v + r"\.(\w+)", body)
        return dict(num=num, name=nm.group(1) if nm else "f%d" % num,
                    type="message", rule="repeated", sub=m.group(1))
    # singular message
    m = re.search(v + r"\.(\w+) = o\.proto\.([A-Za-z_]\w*)\.decode\(", body)
    if m:
        return dict(num=num, name=m.group(1), type="message", rule="single", sub=m.group(2))
    # repeated scalar
    m = re.search(v + r"\.(\w+).*?\.push\(e\.(\w+)\(\)\)", body, re.DOTALL)
    if m and m.group(2) in SCALAR:
        return dict(num=num, name=m.group(1), type=m.group(2), rule="repeated", sub=None)
    # singular scalar
    m = re.search(v + r"\.(\w+) = e\.(\w+)\(\)", body)
    if m and m.group(2) in SCALAR:
        return dict(num=num, name=m.group(1), type=m.group(2), rule="single", sub=None)
    m = re.search(v + r"\.(\w+)", body)
    return dict(num=num, name=m.group(1) if m else "f%d" % num,
                type="unknown", rule="single", sub=None, raw=body.strip()[:90])


def main():
    src = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore")
    out = {}
    marks = [(m.start(), m.group(1)) for m in MSG_RE.finditer(src)]
    marks.append((len(src), None))
    unknown = 0
    for (start, name), (end, _) in pairwise(marks):
        if name is None:
            continue
        seg = src[start:end]
        dm = DECODE_RE.search(seg)
        if not dm:
            continue
        body = dm.group(1)
        accm = re.search(r"(\w+) = new o\.proto\." + re.escape(name) + r"\(\)", body)
        acc = accm.group(1) if accm else "i"
        fields = []
        for cm in CASE_RE.finditer(body):
            f = parse_case(int(cm.group(1)), cm.group(2), acc)
            if f["type"] == "unknown":
                unknown += 1
            fields.append(f)
        # Keep every message that has a decode function, including empty ones
        # (e.g. parameterless requests like GAME_HD_GETMARCHS_C2S).
        out[name] = {"fields": fields}
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("schema.json")
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print("[+] %d messages -> %s  (%d unknown fields)" % (len(out), dst, unknown))


if __name__ == "__main__":
    main()
