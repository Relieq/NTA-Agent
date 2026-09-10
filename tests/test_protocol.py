"""Codec tests: exact wire vectors + roundtrips against the real game schema."""

import pytest

from nta_agent.io.api.protocol import Codec

pytestmark = pytest.mark.skipif(
    not (Codec.__module__ and __import__("pathlib").Path(
        __import__("nta_agent.io.api.protocol", fromlist=["_SCHEMA_PATH"])._SCHEMA_PATH
    ).exists()),
    reason="schema.json not present (regenerate via tools/re/parse_schema.py)",
)


@pytest.fixture(scope="module")
def codec() -> Codec:
    return Codec.load()


def test_known_vector_scalar_and_string(codec: Codec):
    # GAME_HD_UPAREABUILD_C2S { index:int32=1, uid:string=2 }
    # field1 varint 3 -> 08 03 ; field2 "abc" -> 12 03 61 62 63
    body = codec.encode("GAME_HD_UPAREABUILD_C2S", {"index": 3, "uid": "abc"})
    assert body == bytes([0x08, 0x03, 0x12, 0x03, 0x61, 0x62, 0x63])


def test_roundtrip_trylogin(codec: Codec):
    src = {
        "accountToken": "tok123",
        "distinctId": "d-1",
        "os": "android",
        "lang": "en",
        "platform": "google",
    }
    body = codec.encode("LOBBY_HD_TRYLOGIN_C2S", src)
    back = codec.decode("LOBBY_HD_TRYLOGIN_C2S", body)
    assert back == src


def test_envelope_s2c_result(codec: Codec):
    body = codec.encode("S2C_RESULT", {"data": b"\x01\x02", "error": "oops"})
    back = codec.decode("S2C_RESULT", body)
    assert back == {"data": b"\x01\x02", "error": "oops"}


def test_omitted_fields_are_absent(codec: Codec):
    body = codec.encode("LOBBY_HD_TRYLOGIN_C2S", {"accountToken": "x"})
    back = codec.decode("LOBBY_HD_TRYLOGIN_C2S", body)
    assert back == {"accountToken": "x"}


def test_unknown_fields_are_skipped(codec: Codec):
    # extra field #15 varint appended -> must be ignored, known field still read
    body = codec.encode("GAME_HD_UPAREABUILD_C2S", {"index": 7})
    body += bytes([(15 << 3) | 0, 0x2A])  # field 15 varint 42
    back = codec.decode("GAME_HD_UPAREABUILD_C2S", body)
    assert back == {"index": 7}


def test_repeated_and_nested_roundtrip(codec: Codec):
    # ArmyData { name:string=1, pawns: repeated NovicePawnData=2 }
    if not (codec.has("ArmyData") and codec.has("NovicePawnData")):
        pytest.skip("ArmyData/NovicePawnData not in schema")
    pawn_fields = {f["name"] for f in codec.schema["NovicePawnData"]["fields"]}
    pawn = {}  # empty nested message is a valid, minimal case
    src = {"name": "1st Legion", "pawns": [pawn, pawn]}
    body = codec.encode("ArmyData", src)
    back = codec.decode("ArmyData", body)
    assert back["name"] == "1st Legion"
    assert isinstance(back["pawns"], list) and len(back["pawns"]) == 2
    assert pawn_fields  # sanity: schema really has the nested type


def test_negative_int32_roundtrip(codec: Codec):
    # find a message with an int32 field and roundtrip a negative value
    body = codec.encode("LOBBY_HD_TRYLOGIN_S2C", {"banAccountType": -5})
    back = codec.decode("LOBBY_HD_TRYLOGIN_S2C", body)
    assert back["banAccountType"] == -5


def test_empty_message_roundtrips(codec: Codec):
    # Parameterless requests (e.g. GAME_HD_GETMARCHS_C2S) must exist and encode
    # to zero bytes — regression for the parser dropping empty messages.
    assert codec.has("GAME_HD_GETMARCHS_C2S")
    assert codec.encode("GAME_HD_GETMARCHS_C2S", {}) == b""
    assert codec.decode("GAME_HD_GETMARCHS_C2S", b"") == {}
