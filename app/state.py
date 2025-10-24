from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AppState:
    recording: bool = False
    audio_buffer: List[int] = field(default_factory=list)
    current_file: Optional[str] = None
    window: Optional[object] = None  # pywebview Window
    rt_text: str = ""  # real-time transcription aggregate
    rt_committed: str = ""  # text already inserted into focused app
    active_window_id: Optional[str] = None
