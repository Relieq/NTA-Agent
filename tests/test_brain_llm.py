import json

from nta_agent.brain.llm import BrainUnavailable, default_chat, propose
from nta_agent.execution.profile import load_profile


def test_propose_builds_messages_and_parses_json():
    seen = {}

    def fake_chat(messages):
        seen["messages"] = messages
        return "```json\n" + json.dumps({"occupy": {"max_loss": 5}, "rationale": "safer"}) + "\n```"

    out = propose({"resources": {"cereal": 1}}, load_profile("none"), chat=fake_chat)
    assert out["occupy"]["max_loss"] == 5 and out["rationale"] == "safer"
    blob = " ".join(m["content"] for m in seen["messages"])
    assert "max_loss" in blob and "cereal" in blob   # schema + digest present


def test_malformed_response_is_empty():
    assert propose({}, load_profile("none"), chat=lambda m: "not json at all") == {}


def test_default_chat_without_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    try:
        default_chat()
        raise AssertionError("expected BrainUnavailable")
    except BrainUnavailable:
        pass
