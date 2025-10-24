"""App package for the dictation recorder.

Modules:
- config: constants and tunables
- state: shared application state dataclass
- audio.recorder: ffmpeg-based recording
- audio.monitor: live audio visualization via sounddevice
- ui.window: pywebview window and JS bridge
- transcribe: whisper-cli integration
- insertion: paste/type text into the active application
"""
