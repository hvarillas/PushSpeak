import os
import subprocess
import signal
import tempfile
import uuid
from dataclasses import dataclass
from typing import Optional


@dataclass
class RecorderConfig:
    device_system: str = "pulse"  # or 'alsa'
    input_device: str = "default"
    sample_rate: int = 48000
    channels: int = 2
    codec: str = "pcm_s16le"
    output_format: str = "wav"


class Recorder:
    def __init__(self, cfg: RecorderConfig):
        self.cfg = cfg
        self.proc: Optional[subprocess.Popen] = None
        self.filename: Optional[str] = None

    def start(self) -> str:
        self.filename = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex}.{self.cfg.output_format}")
        cmd = [
            "ffmpeg",
            "-f", self.cfg.device_system,
            "-i", self.cfg.input_device,
            "-ar", str(self.cfg.sample_rate),
            "-ac", str(self.cfg.channels),
            "-acodec", self.cfg.codec,
            "-y",
            self.filename,
        ]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self.filename

    def stop(self, timeout: int = 5) -> Optional[str]:
        if not self.proc:
            return None
        try:
            self.proc.send_signal(signal.SIGINT)
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        finally:
            self.proc = None
        return self.filename if self.filename and os.path.exists(self.filename) else None
