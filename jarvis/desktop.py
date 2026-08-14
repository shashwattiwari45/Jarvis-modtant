"""Desktop-control facade backed by jarvis.core."""
from .core import (
    open_application, close_app_by_name, list_running_apps, open_website, web_search,
    type_text, take_screenshot, control_zoom, control_chrome, control_volume, control_media,
    control_brightness, get_time, get_weather, system_status, system_diagnostics,
    click_on_text, click_ui_target, ocr_screen_layout, read_screen_text, analyze_screen,
)
