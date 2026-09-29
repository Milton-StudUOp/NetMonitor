import httpx
import pytest

from app.services.notification.channels import whatsapp_api_payload, safe_delivery_error
from app.services.notification.channels import validate_integration, NotificationConfigurationError
from app.schemas.platform import NotificationIntegrationInput
from pydantic import ValidationError


def test_meta_uses_cloud_api_text_contract():
    payload = whatsapp_api_payload({"api_url": "https://graph.facebook.com/v23.0/123/messages"}, "258841234567", "Test")
    assert payload == {"messaging_product": "whatsapp", "recipient_type": "individual",
                       "to": "258841234567", "type": "text",
                       "text": {"preview_url": False, "body": "Test"}}


def test_removed_qr_mode_is_rejected_in_saved_records_and_api_input():
    with pytest.raises(NotificationConfigurationError, match="removed"):
        validate_integration("WHATSAPP", {"mode": "WEBJS"}, {})
    with pytest.raises(ValidationError, match="HTTP_API only"):
        NotificationIntegrationInput(provider="WHATSAPP", name="WhatsApp", config={"mode": "WEBJS"})


def test_existing_api_configuration_without_mode_defaults_to_http():
    value = NotificationIntegrationInput(provider="WHATSAPP", name="WhatsApp", config={"api_url": "https://provider.example/messages"})
    assert value.config["mode"] == "HTTP_API"


def test_custom_provider_contract_preserved():
    assert whatsapp_api_payload({"api_url": "https://provider.example/messages", "sender_id": "sender"}, "target", "Test") == {
        "sender": "sender", "recipient": "target", "message": "Test"}


def test_meta_unsupported_post_identifies_endpoint_error():
    request = httpx.Request("POST", "https://graph.facebook.com/v25.0/123/messages")
    response = httpx.Response(400, request=request, json={"error": {
        "code": 100, "message": "Unsupported request - method type: post"}})
    error = httpx.HTTPStatusError("rejected", request=request, response=response)
    assert "Meta rejected POST on this endpoint" in safe_delivery_error(error)


@pytest.mark.parametrize("code,expected", [(190, "expired"), (131030, "allowed list"), (131047, "24-hour")])
def test_meta_error_feedback_is_actionable_without_exposing_response(code, expected):
    request = httpx.Request("POST", "https://graph.facebook.com/v23.0/123/messages")
    response = httpx.Response(400, request=request, json={"error": {"code": code, "message": "private token and phone"}})
    error = httpx.HTTPStatusError("private", request=request, response=response)
    message = safe_delivery_error(error)
    assert expected in message
    assert "private" not in message
