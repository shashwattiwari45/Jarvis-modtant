# Phone Jarvis

Private Android-side Jarvis companion.

## Design boundary

- The phone Jarvis is the private command center for the owner.
- Instagram is treated as a separate anonymous public operation.
- The phone can privately request audience metrics, recent performance, today's planned content, rationale, format, and production quality.
- Public Instagram responses/posts must never reveal the owner's identity or private account relationship.
- No Instagram publishing logic is duplicated here; the cloud/social agent remains responsible for the account operation.

## Current stage

This package provides the cloud client and private Instagram briefing contract. The Android UI/voice layer can call these interfaces without changing the existing desktop Jarvis engine.

Required environment values:

```text
JARVIS_CLOUD_URL=https://your-service.onrender.com
JARVIS_CLOUD_SECRET=your_phone_scoped_secret
JARVIS_DEVICE_ID=android-phone
```

The phone should eventually use a device-specific credential and permissions instead of sharing the PC's credential.
