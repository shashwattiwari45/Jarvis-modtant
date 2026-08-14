"""Memory facade backed by jarvis.core."""
from .core import (
    remember_fact, recall_fact, remember_personal_context, add_task_memory,
    continue_last_task, set_quiet_mode, set_proactive_frequency,
    load_memory, save_memory, MEMORY_DATA, SESSION_MEMORY,
)
