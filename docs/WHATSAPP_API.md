# WhatsApp API notifications

WhatsApp notifications use an HTTP API. QR linking, the Node.js bridge, Puppeteer,
and Chromium are no longer part of the application.

## Meta Cloud API setup

In **Settings → Notifications → WhatsApp**, enable the integration and enter:

1. The complete messages URL from your working Meta request:
   `https://graph.facebook.com/v<VERSION>/<PHONE_NUMBER_ID>/messages`.
   Use the sending phone number ID, not the WhatsApp Business Account ID.
   Match the version used in your verified request; versions are not hardcoded.
2. The access token only. The backend adds `Authorization: Bearer` automatically.
   A blank token field preserves the previously saved encrypted credential.
3. Recipient numbers including country code, with digits only. Separate multiple
   recipients with commas, semicolons, or line breaks.

Sender ID is unnecessary for Meta: the URL identifies the sending number.
Use **Save & Test**, then verify receipt on the phone. API acceptance alone is
not proof of delivery. Enable the relevant notification rule and its recovery
option to receive both outage and recovery messages.

The Meta request is JSON:

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "<RECIPIENT_NUMBER>",
  "type": "text",
  "text": {"preview_url": false, "body": "<NOTIFICATION_TEXT>"}
}
```

The integration sends text, not approved templates. Free-form text requires an
open customer service window. Outside that window, an approved template is
required by Meta; template sending and delivery-status webhooks are not currently
implemented. Meta test numbers also require allowed recipients.

Custom HTTP providers must accept the existing `sender`, `recipient`, `message`
JSON contract and bearer authentication. Provider-specific APIs with other
contracts require their own adapter.

## Troubleshooting

- HTTP 400/code 100: compare the exact URL, version, phone number ID and payload
  with the successful Graph Explorer request. An unsupported POST error is an
  endpoint rejection, not evidence of invalid message formatting.
- Code 190: check token validity and expiry.
- Code 131030: add the recipient to the test number's allowed recipients.
- Code 131047: the customer service window has closed.
- After changing configuration outside the UI, reload Settings before saving:
  **Save & Test** persists the fields currently displayed in the browser.

Tokens and raw provider error bodies are not included in user-facing errors.
Configuration and encrypted credentials use the active primary database.

## Upgrade from QR linking

- Configure HTTP API credentials and save the integration. Old QR-mode records
  require reconfiguration; runtime delivery rejects unsupported modes explicitly.
- Stop and disable any previously deployed bridge process or service. Removing
  the Compose service definition does not stop an already running container.
- Revoke the old linked device in WhatsApp on the phone.
- Remove unused bridge environment variables from your deployment configuration.
- Existing local session directories and Docker volumes are preserved. Review
  and remove them separately according to your retention policy.

Reference: [Meta's official text-message example](https://www.postman.com/meta/whatsapp-business-platform/request/73yi2uj/send-reply-to-text-message).
