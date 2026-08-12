# Autonomous Instagram integration

The new `instagram_autonomous.py` adds the missing production pipeline:

`strategy -> image quality selection -> OpenAI image generation -> public media hosting -> Meta Graph publish -> audit/history`

## Add to `jarvisvav1.py`

After the existing imports/configuration, add:

```python
from instagram_autonomous import autonomous_post, get_status as instagram_autonomous_status
```

Inside the existing `create_instagram_post()` function, after `strategy = generate_social_strategy(request)`, the autonomous path can be routed through the new pipeline:

```python
if publish and mode == "AUTONOMOUS" and not image_url:
    try:
        result = autonomous_post(generate_social_strategy, request=request, force_publish=True)
        return f"Published autonomous Instagram post {result['id']} using {result['quality']} image quality."
    except Exception as e:
        social_audit("instagram_autonomous_failed", {"error": str(e)})
        return f"Autonomous Instagram post failed: {e}"
```

Keep the existing manual/approval path unchanged.

## Environment variables

```text
OPENAI_API_KEY=...
OPENAI_IMAGE_MODEL=gpt-image-1.5
INSTAGRAM_ACCESS_TOKEN=...
INSTAGRAM_ACCOUNT_ID=...
META_GRAPH_API_VERSION=v20.0
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```

Optional quality mix:

```text
JARVIS_INSTAGRAM_HIGH_QUALITY_RATE=0.15
JARVIS_INSTAGRAM_MEDIUM_QUALITY_RATE=0.65
JARVIS_INSTAGRAM_LOW_QUALITY_RATE=0.20
```

The module also treats `flagship`, `hero`, `campaign`, `important`, `announcement`, and `milestone` strategy terms as premium-image triggers.

## Important

Meta's publishing flow requires a publicly reachable media URL. The module uses Cloudinary for that URL. It does not use browser automation or private Instagram endpoints.

DM/comment autonomy still requires the Meta webhook/messaging layer; this module deliberately does not fake polling or browser automation for Instagram DMs.
