import os
import subprocess
import signal
import tempfile
import uuid
import logging
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
        logging.debug(f"[RECORDER] Iniciando grabación: {self.filename}")
        logging.debug(f"[RECORDER] Comando ffmpeg: {' '.join(cmd)}")
        try:
            self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logging.info(f"[RECORDER] Grabación iniciada (PID: {self.proc.pid})")
        except Exception as e:
            logging.error(f"[RECORDER] Error al iniciar ffmpeg: {e}")
            raise
        return self.filename

    def stop(self, timeout: int = 5) -> Optional[str]:
        if not self.proc:
            logging.warning("[RECORDER] stop() llamado sin proceso activo")
            return None
        logging.debug(f"[RECORDER] Deteniendo grabación (PID: {self.proc.pid})")
        try:
            self.proc.send_signal(signal.SIGINT)
            self.proc.wait(timeout=timeout)
            logging.debug(f"[RECORDER] Proceso ffmpeg terminado correctamente")
        except subprocess.TimeoutExpired:
            logging.warning(f"[RECORDER] Timeout esperando ffmpeg, forzando kill")
            self.proc.kill()
            self.proc.wait()
        finally:
            self.proc = None
        
        if self.filename and os.path.exists(self.filename):
            file_size = os.path.getsize(self.filename)
            logging.info(f"[RECORDER] Archivo guardado: {self.filename} ({file_size} bytes)")
            return self.filename
        else:
            logging.error(f"[RECORDER] Archivo no existe o es inválido: {self.filename}")
            return None
