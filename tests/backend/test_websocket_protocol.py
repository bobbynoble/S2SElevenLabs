import pytest
from pydantic import ValidationError

from src.models import ClientMessageEnvelope


def test_join_message_parses():
    envelope = ClientMessageEnvelope.model_validate({"message": {"type": "join", "language": "pl"}})
    assert envelope.message.type == "join"
    assert envelope.message.language == "pl"


def test_control_messages_without_payload_parse():
    for msg_type in ("start_turn", "end_turn", "end_session"):
        envelope = ClientMessageEnvelope.model_validate({"message": {"type": msg_type}})
        assert envelope.message.type == msg_type


def test_unknown_type_is_rejected():
    with pytest.raises(ValidationError):
        ClientMessageEnvelope.model_validate({"message": {"type": "not_a_real_type"}})


def test_join_without_language_is_rejected():
    with pytest.raises(ValidationError):
        ClientMessageEnvelope.model_validate({"message": {"type": "join"}})
