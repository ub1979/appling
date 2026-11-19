# Optional WhatsApp phone bridge

This local Node.js sidecar connects Appling to the user's **Message yourself**
chat through WhatsApp Linked Devices. It uses the upstream
[WhiskeySockets/Baileys](https://github.com/WhiskeySockets/Baileys) package,
`baileys`, pinned to `7.0.0-rc14`. Baileys is an independent, unofficial project,
not Meta's WhatsApp Business API. Connection changes may require reconnection.

## Install and pair

From the `appling_c` checkout:

```bash
cd bridge/whatsapp
npm install
```

The initial dependency install requires network access. This development
environment could not resolve the npm registry, so an actual Baileys install,
transitive lockfile and authenticated WhatsApp connection have not been verified.
The install command creates the real lockfile; no generated or invented lockfile
is supplied. Node.js 20 or newer is required.

1. In Appling Settings, choose **WhatsApp → Pair phone**.
2. On the phone, open **WhatsApp → Settings → Linked devices → Link a device**
   and scan the QR code displayed by Appling.
3. Open **Message yourself** and send `/pair CODE`, using the one-time code
   displayed in Settings. Codes expire after ten minutes.
4. Appling confirms the pairing. Its questions will now appear in that chat.

Only messages sent by the linked owner inside their self-chat are accepted.
Messages from contacts and groups are ignored. Appling does not ingest unrelated
WhatsApp chats or send messages to contacts. A successful device link alone does
not authorize project approvals: the second pairing step is required.

## Answering

Reply to the exact question message, or send `/reply REQUEST_CODE your answer`.
Use `/approve REQUEST_CODE` for an offered approval, or
`/deny REQUEST_CODE your feedback` to decline/request changes. These commands
call the same workflow controller used by the desktop interface. Closed
requests, unknown codes, modified reviewed artifacts and duplicate approvals
are rejected. A bare "yes" does not approve anything.

Requirements and plan reviews include their text. The prototype remains local
to the PC; inspect it in Appling before approving. Phone pairing does not expose
the local preview or API to the internet.

The computer must stay awake, online and running Appling. Authentication state
is saved under the private `.appling_c/phone/whatsapp/` directory (owner-only
permissions); it must never be committed. Disconnect in Settings revokes the
Appling pairing, attempts WhatsApp logout, and removes the local linked-device
credentials. If the internet is unavailable, remove the device in WhatsApp's
Linked devices screen as well.

The stdio bridge exposes no HTTP port. It receives only send/logout commands
and returns connection state, QR codes and owner-self-chat replies. It receives
no AI provider credentials. Request routing and delivery tracking are durable
in Appling's existing store. A crash during transmission can repeat a
notification, but repeated responses cannot approve an already closed request.

## Local checks without WhatsApp access

```bash
npm run check
npm test
```

These check parsing/filtering of self-chat messages and exact quoted-message
routing. They do not establish an authenticated WhatsApp session or certify
compatibility with WhatsApp's live service.
