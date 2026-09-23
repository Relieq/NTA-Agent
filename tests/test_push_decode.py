"""Pushes arrive as a SINGLE On*InfoNotify item, not the {list:[...]} wrapper.

Regression with real bytes captured live 2026-09-23: decoding them as the
GAME_ON*_NOTIFY wrapper failed (IndexError) or mis-parsed (lost `type`), so the
agent applied NO push at all — resources, build queue/levels, marches, capture.
"""
from nta_agent.io.api.protocol import Codec
from nta_agent.io.api.session import decode_push

C = Codec.load()


def test_player_output_push_single_item():
    raw = bytes.fromhex("0801120b0a0105320608980d108b02")
    d = decode_push(C, "GAME_ONUPDATEPLAYERINFO_NOTIFY", raw)
    item = d["list"][0]
    assert item["type"] == 1
    assert item["data_1"]["flags"] == [5]                      # Stone flag
    assert item["data_1"]["stone"] == {"value": 1688, "opHour": 267}


def test_world_push_single_item_keeps_type():
    d = decode_push(C, "GAME_ONUPDATEWORLDINFO_NOTIFY",
                    bytes.fromhex("0811320e08ccd80612083238313130343032"))
    assert d["list"][0]["type"] == 17
    assert d["list"][0]["data_17"] == {"index": 109644, "uids": ["28110402"]}
    d2 = decode_push(C, "GAME_ONUPDATEWORLDINFO_NOTIFY",
                     bytes.fromhex("081b520f08adc90e10b6101880897a2080897a"))
    assert d2["list"][0]["type"] == 27 and d2["list"][0]["data_27"]["id"] == 2102


def test_list_wrapped_payload_still_supported():
    wrapped = C.encode("GAME_ONUPDATEPLAYERINFO_NOTIFY",
                       {"list": [{"type": 1, "data_1": {"flags": [3], "cereal": {"value": 9}}}]})
    d = decode_push(C, "GAME_ONUPDATEPLAYERINFO_NOTIFY", wrapped)
    assert d["list"][0]["type"] == 1 and d["list"][0]["data_1"]["cereal"] == {"value": 9}


def test_area_push_is_already_an_item():
    raw = C.encode("GAME_ONUPDATEAREAINFO_NOTIFY",
                   {"type": 5, "index": 71372, "data_5": {"uid": "h", "id": 2001, "lv": 8}})
    d = decode_push(C, "GAME_ONUPDATEAREAINFO_NOTIFY", raw)
    assert d["type"] == 5 and d["data_5"]["lv"] == 8
