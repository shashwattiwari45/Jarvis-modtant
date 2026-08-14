"""Social-media facade backed by jarvis.core plus the autonomous Instagram engine."""
from .core import (
    social_config, set_social_mode, analyze_instagram_performance,
    create_instagram_post, publish_instagram_media, show_social_history,
    generate_social_reply, send_whatsapp_message, change_instagram_bio,
)
try:
    from instagram_autonomous import autonomous_post, get_status as instagram_status
except ImportError:
    autonomous_post = None
    instagram_status = None
