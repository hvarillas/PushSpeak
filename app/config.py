from dataclasses import dataclass


@dataclass(frozen=True)
class AudioConfig:
    sample_rate: int = 48000
    channels: int = 2
    codec: str = "pcm_s16le"
    output_format: str = "wav"
    input_device: str = "default"
    device_system: str = "pulse"  # or 'alsa'


@dataclass(frozen=True)
class WhisperConfig:
    model_path: str = "~/.models/ggml-small.bin"
    language: str = "es"
    auto_transcribe: bool = True
    rt_chunk_seconds: float = 1.5
    stream_insert: bool = True
    rt_backend: str = "whisper_stream"  # options: "whisper_stream", "cli"
    stream_model: str = "small"  # faster-whisper model size or path
    stream_sample_rate: int = 16000
    stream_device: str = "cuda"  # "auto" | "cuda" | "cpu"
    stream_compute_type: str = "float16"  # gpu: float16/int8_float16, cpu: int8/float32


@dataclass(frozen=True)
class UIConfig:
    width: int = 500
    height: int = 150  # Increased to accommodate 3D effect (reduced from doubled glow)
    bottom_margin: int = 60
    transparent: bool = True
    frameless: bool = True
    easy_drag: bool = True


COMBO_RECORD = {"ctrl", "alt"}
INSERT_TRAILING = " "
