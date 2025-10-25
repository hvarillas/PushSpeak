import os
import shutil
import subprocess
import tempfile
import threading
import queue
import wave
import time
import re
import math
import logging
from typing import Optional
from pathlib import Path

# Optional global cache for faster-whisper model (used by streaming backend)
try:
    from faster_whisper import WhisperModel as _FWWhisperModel  # type: ignore
except Exception:  # pragma: no cover
    _FWWhisperModel = None  # type: ignore

_FW_MODEL = None
_FW_MODEL_ID = None


def ensure_fw_model_preloaded(model_size: str, device: str = "auto", compute_type: str = "float16") -> bool:
    """Preload and cache a faster-whisper model only once or when config changes.

    Returns True if the model is available (loaded or reused), False otherwise.
    """
    global _FW_MODEL, _FW_MODEL_ID
    if _FWWhisperModel is None:
        return False
    dev = (device or "auto").lower()
    ct = (compute_type or "float16").lower()
    model_id = f"{model_size}|{dev}|{ct}"
    if _FW_MODEL is not None and _FW_MODEL_ID == model_id:
        return True
    try:
        if dev == "auto":
            try:
                _FW_MODEL = _FWWhisperModel(model_size, device="cuda", compute_type=ct)
            except Exception:
                try:
                    _FW_MODEL = _FWWhisperModel(model_size, device="cpu", compute_type=("int8" if ct != "float32" else "float32"))
                except Exception:
                    _FW_MODEL = _FWWhisperModel(model_size, device="cpu", compute_type="float32")
        elif dev == "cuda":
            _FW_MODEL = _FWWhisperModel(model_size, device="cuda", compute_type=ct)
        else:
            _FW_MODEL = _FWWhisperModel(model_size, device="cpu", compute_type=(ct if ct in ("int8", "float32") else "int8"))
        _FW_MODEL_ID = model_id
        return True
    except Exception:
        _FW_MODEL = None
        _FW_MODEL_ID = None
        return False


def verify_whisper() -> bool:
    cli = resolve_whisper_cli()
    if not cli:
        logging.error("[WHISPER] No se encontró whisper-cli")
        return False
    logging.debug(f"[WHISPER] Verificando whisper-cli: {cli}")
    try:
        resultado = subprocess.run([cli, "-h"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
        if resultado.returncode == 0:
            logging.info(f"[WHISPER] whisper-cli verificado correctamente: {cli}")
            return True
        else:
            logging.error(f"[WHISPER] whisper-cli retornó código {resultado.returncode}")
            return False
    except FileNotFoundError:
        logging.error(f"[WHISPER] whisper-cli no encontrado: {cli}")
        return False
    except subprocess.TimeoutExpired:
        logging.error(f"[WHISPER] Timeout verificando whisper-cli")
        return False


_BRACKET_TOKEN_RE = re.compile(r"\s*\[[A-ZÁÉÍÓÚÜÑ_ ]+\]\s*", flags=re.UNICODE)
_DUP_WORD_RE = re.compile(r"(\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b)(?:\s+\1\b)+", re.IGNORECASE | re.UNICODE)


def _clean_text(text: str) -> str:
    if not text:
        return text
    text = _BRACKET_TOKEN_RE.sub(" ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    # collapse repeated words
    text = _DUP_WORD_RE.sub(r"\1", text)
    return text


def merge_with_overlap(prev: str, new: str, max_overlap_words: int = 15) -> str:
    """Merge new partial text into prev by removing overlapping prefix/suffix.
    Uses word-based overlap to avoid duplicates across chunk boundaries.
    """
    prev = prev or ""
    new = new or ""
    if not prev:
        return new
    if not new:
        return prev
    pw = prev.split()
    nw = new.split()
    m = min(len(pw), len(nw), max_overlap_words)
    overlap = 0
    for k in range(m, 0, -1):
        if pw[-k:] == nw[:k]:
            overlap = k
            break
    if overlap > 0:
        add = " ".join(nw[overlap:])
    else:
        add = new
    add = add.strip()
    if not add:
        return prev
    if prev.endswith(" ") or not prev:
        return (prev + add).strip()
    return (prev + " " + add).strip()


def transcribe_audio(path: str, model: str, language: str, prompt: Optional[str] = None) -> Optional[str]:
    logging.debug(f"[TRANSCRIBE] Iniciando transcripción de: {path}")
    
    if not os.path.exists(path):
        logging.error(f"[TRANSCRIBE] Archivo no existe: {path}")
        return None
    
    file_size = os.path.getsize(path)
    logging.debug(f"[TRANSCRIBE] Tamaño del archivo: {file_size} bytes")
    
    if file_size == 0:
        logging.error(f"[TRANSCRIBE] Archivo vacío: {path}")
        return None

    cli = resolve_whisper_cli()
    if not cli:
        logging.error("[TRANSCRIBE] whisper-cli no disponible")
        return None

    # resolve model path relative to project root if not absolute
    try:
        if model and not os.path.isabs(model):
            root = Path(__file__).resolve().parents[1]
            model = str((root / model).resolve())
    except Exception as e:
        logging.warning(f"[TRANSCRIBE] Error resolviendo ruta del modelo: {e}")
        pass
    
    logging.debug(f"[TRANSCRIBE] Modelo: {model}")
    logging.debug(f"[TRANSCRIBE] Idioma: {language}")
    
    if not os.path.exists(model):
        logging.error(f"[TRANSCRIBE] Modelo no existe: {model}")
        return None
    
    # Validar el archivo del modelo
    try:
        model_size = os.path.getsize(model)
        logging.debug(f"[TRANSCRIBE] Tamaño del modelo: {model_size} bytes ({model_size / 1024 / 1024:.2f} MB)")
        
        if model_size < 1024 * 1024:  # menos de 1 MB es sospechoso
            logging.error(f"[TRANSCRIBE] El modelo parece demasiado pequeño ({model_size} bytes). Puede estar corrupto.")
            return None
        
        # Verificar que es un archivo binario de whisper (magic bytes)
        with open(model, 'rb') as f:
            magic = f.read(6)
            logging.debug(f"[TRANSCRIBE] Magic bytes del modelo: {magic.hex() if magic else 'vacío'}")
            # Los modelos GGML de whisper.cpp empiezan con 'ggml' o 'ggjt'
            # Algunos modelos pueden tener variantes (little-endian, etc.)
            if magic and not (magic.startswith(b'ggml') or magic.startswith(b'ggjt') or magic.startswith(b'lmgg')):
                logging.warning(f"[TRANSCRIBE] Magic bytes no reconocidos: {magic[:4].hex()}")
                logging.warning(f"[TRANSCRIBE] Esperado: 'ggml', 'ggjt' o 'lmgg'")
                logging.warning(f"[TRANSCRIBE] Intentando continuar de todas formas...")
            else:
                logging.debug(f"[TRANSCRIBE] Formato del modelo reconocido")
    except Exception as e:
        logging.error(f"[TRANSCRIBE] Error validando archivo del modelo: {e}")
        return None

    comando = [
        cli,
        "-m", model,
        "-f", path,
        "-l", language,
        "-nt",
        "-sns",
        "-sow",
        "-nf",
    ]
    if prompt:
        # keep prompt short (e.g., last 24 words)
        comando += ["--prompt", prompt]
    
    logging.debug(f"[TRANSCRIBE] Ejecutando: {' '.join(comando)}")
    
    try:
        resultado = subprocess.run(
            comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=60, text=True
        )
        
        logging.debug(f"[TRANSCRIBE] Código de retorno: {resultado.returncode}")
        
        if resultado.stderr:
            logging.debug(f"[TRANSCRIBE] stderr: {resultado.stderr[:500]}")
        
        if resultado.returncode == 0:
            raw_output = resultado.stdout.strip()
            logging.debug(f"[TRANSCRIBE] Salida cruda (primeros 200 chars): {raw_output[:200]}")
            text = _clean_text(raw_output)
            if text:
                logging.info(f"[TRANSCRIBE] Transcripción exitosa: {len(text)} caracteres")
                logging.debug(f"[TRANSCRIBE] Texto: {text[:100]}...")
                return text
            else:
                logging.warning("[TRANSCRIBE] Transcripción vacía después de limpiar")
                return None
        else:
            logging.error(f"[TRANSCRIBE] whisper-cli falló con código {resultado.returncode}")
            if resultado.stderr:
                logging.error(f"[TRANSCRIBE] Error: {resultado.stderr[:500]}")
            return None
    except FileNotFoundError as e:
        logging.error(f"[TRANSCRIBE] Comando no encontrado: {e}")
        return None
    except subprocess.TimeoutExpired:
        logging.error("[TRANSCRIBE] Timeout (>60s) esperando transcripción")
        return None
    except Exception as e:
        logging.error(f"[TRANSCRIBE] Error inesperado: {e}")
        return None


def resolve_whisper_cli() -> Optional[str]:
    """Find whisper-cli binary across common locations.

    Order:
    - env WHISPER_CLI
    - PATH (shutil.which)
    - project-local fallbacks: ./whisper-cli, whisper.cpp/main, typical build/bin paths
    """
    # env override
    p = os.environ.get("WHISPER_CLI")
    if p and os.path.isfile(p) and os.access(p, os.X_OK):
        logging.debug(f"[WHISPER] Usando WHISPER_CLI de env: {p}")
        return p
    # PATH
    p2 = shutil.which("whisper-cli")
    if p2:
        logging.debug(f"[WHISPER] Encontrado whisper-cli en PATH: {p2}")
        return p2
    # local repo candidates
    try:
        root = Path(__file__).resolve().parents[1]
        candidates = [
            root / "whisper-cli",
            root / "whisper.cpp" / "main",
            root / "whisper.cpp" / "build" / "bin" / "whisper-cli",
            root / "whisper.cpp" / "build" / "bin" / "main",
            root / "whisper.cpp" / "bin" / "whisper-cli",
            root / "whisper.cpp" / "bin" / "main",
        ]
        logging.debug(f"[WHISPER] Buscando en candidatos locales...")
        for c in candidates:
            try:
                if c.exists() and os.access(str(c), os.X_OK):
                    logging.debug(f"[WHISPER] Encontrado en: {c}")
                    return str(c)
            except Exception:
                continue
    except Exception as e:
        logging.debug(f"[WHISPER] Error buscando candidatos locales: {e}")
        pass
    logging.warning("[WHISPER] No se encontró whisper-cli en ninguna ubicación")
    return None


def _tokenize_words(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"\w+", text, flags=re.UNICODE)]


def _drop_first_k_words(text: str, k: int) -> str:
    if k <= 0:
        return text
    it = list(re.finditer(r"\w+", text, flags=re.UNICODE))
    if len(it) <= k:
        return ""
    s = it[k].start()
    out = text[s:]
    out = re.sub(r"^[\s\.,;:!\?\-–—\"'»«¡¿\)\]]+", "", out)
    return out


class RealTimeTranscriber:
    """Chunked real-time transcription using whisper-cli.

    Feeds float32 mono frames ([-1,1]) via add_frame(). Internally batches
    ~chunk_seconds of audio, writes a temporary WAV and runs whisper-cli to
    obtain incremental text. Aggregated text is available in .text.
    """

    def __init__(self, model: str, language: str, sample_rate: int, chunk_seconds: float = 1.0, flush_interval: Optional[float] = None):
        self.model = model
        self.language = language
        self.sample_rate = sample_rate
        self.chunk_seconds = max(0.5, float(chunk_seconds))
        self._samples_needed = int(self.sample_rate * self.chunk_seconds)
        self._q: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=128)
        self._buf = bytearray()
        self._thr: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.text = ""
        self._last_flush = time.time()
        self._flush_interval = max(0.4, float(flush_interval)) if flush_interval else self.chunk_seconds

    def start(self):
        if self._thr and self._thr.is_alive():
            return
        self._stop.clear()
        self._thr = threading.Thread(target=self._run, daemon=True)
        self._thr.start()

    def stop(self) -> str:
        try:
            self._stop.set()
            self._q.put(None)
            if self._thr:
                self._thr.join(timeout=3)
        except Exception:
            pass
        return self.text

    def add_frame(self, frame_f32_mono):
        """Accept numpy float32 mono array in [-1,1]."""
        try:
            import numpy as np  # local import to avoid hard dep elsewhere
            x = np.clip(frame_f32_mono, -1.0, 1.0)
            pcm16 = (x * 32767.0).astype(np.int16).tobytes()
            self._q.put(pcm16, timeout=0.1)
        except Exception:
            pass


class WhisperStreamTranscriber:
    """Real-time transcription using ufal/whisper_streaming (faster-whisper backend).

    Requires: faster-whisper installed. Optionally whisper_streaming's whisper_online
    module must be importable. Processes mono float32 frames at arbitrary samplerate,
    resampling to 16 kHz and using OnlineASRProcessor to emit stable commits.
    """

    def __init__(self, model_size: str, language: str, chunk_seconds: float = 1.0, target_sr: int = 16000, device: str = "auto", compute_type: str = "float16"):
        self.model_size = model_size
        self.language = language
        self.chunk_seconds = max(0.5, float(chunk_seconds))
        self.target_sr = target_sr
        self.device = device
        self.compute_type = compute_type
        self.text = ""
        self._thr: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._q: "queue.Queue[Optional[tuple[bytes,int]]]" = queue.Queue(maxsize=256)
        self._online = None
        self._need_init = True
        self._last_feed = 0.0
        self._prev_words_text: list[str] = []
        self._committed_count: int = 0

    def preload(self):
        """Load the faster-whisper model without starting processing (cached)."""
        from app.transcribe import ensure_fw_model_preloaded  # self-import safe
        ok = ensure_fw_model_preloaded(self.model_size, self.device, self.compute_type)
        if not ok:
            raise ImportError("faster-whisper is required")
        # attach cached model reference
        try:
            from app.transcribe import _FW_MODEL  # type: ignore
            self._model = _FW_MODEL
        except Exception:
            self._model = None

        # init commit tracking
        self._prev_words_text = []
        self._committed_count = 0

    def reset(self):
        """Reset internal streaming state to start a fresh session without reloading the model."""
        # Ensure previous worker is fully stopped
        try:
            if hasattr(self, "_thr") and self._thr and self._thr.is_alive():
                try:
                    self._stop.set()
                except Exception:
                    pass
                try:
                    self._q.put(None, timeout=0.1)
                except Exception:
                    pass
                try:
                    self._thr.join(timeout=2)
                except Exception:
                    pass
        except Exception:
            pass

        # Clear text and committed state
        self.text = ""
        # Reinitialize commit tracking
        self._prev_words_text = []
        self._committed_count = 0

        # Drain/replace queue after thread is stopped
        try:
            import queue as _qmod
            self._q = _qmod.Queue(maxsize=256)
        except Exception:
            pass

        # Reuse the existing stop event object; just clear it
        try:
            self._stop.clear()
        except Exception:
            # if not present yet, create it
            import threading as _tmod
            self._stop = _tmod.Event()

        # Allow a new worker thread to be started later
        self._thr = None

    def start(self):
        if self._thr and self._thr.is_alive():
            return
        # ensure model is loaded
        if not hasattr(self, "_model") or self._model is None:
            self.preload()
        self._stop.clear()
        self._thr = threading.Thread(target=self._run, daemon=True)
        self._thr.start()

    def stop(self) -> str:
        try:
            self._stop.set()
            self._q.put(None)
            if self._thr:
                self._thr.join(timeout=3)
        except Exception:
            pass
        # commit remaining words not yet committed
        try:
            rem = []
            if getattr(self, "_prev_words_text", None) is not None:
                rem = self._prev_words_text[self._committed_count:]
            if rem:
                add = _clean_text(" ".join(rem))
                if add:
                    self.text = (self.text + (" " if self.text and not self.text.endswith(" ") else "") + add).strip()
        except Exception:
            pass
        return self.text

    def add_frame(self, frame_f32_mono, in_sr: int):
        # resample to target_sr and enqueue
        try:
            import numpy as np
            from scipy.signal import resample_poly
            if in_sr != self.target_sr:
                g = math.gcd(in_sr, self.target_sr)
                up = self.target_sr // g
                down = in_sr // g
                res = resample_poly(frame_f32_mono, up, down).astype(np.float32)
            else:
                res = frame_f32_mono.astype(np.float32)
            self._q.put((res.tobytes(), len(res)), timeout=0.1)
        except Exception:
            pass

    def _run(self):
        import numpy as np
        buf = bytearray()
        while not self._stop.is_set():
            item = self._q.get()
            if item is None:
                break
            chunk_bytes, n = item
            buf.extend(chunk_bytes)
            # process when enough seconds accumulated
            need = int(self.chunk_seconds * self.target_sr) * 4  # float32 bytes
            if len(buf) >= need:
                try:
                    # always transcribe the last window of size `need`
                    arr = np.frombuffer(bytes(buf[-need:]), dtype=np.float32)
                    # transcribe current buffer
                    prompt = self._tail_prompt_words()
                    segments, _ = self._model.transcribe(
                        arr,
                        language=self.language,
                        beam_size=5,
                        word_timestamps=True,
                        condition_on_previous_text=True,
                        initial_prompt=prompt,
                    )
                    new_words_text: list[str] = []
                    for seg in segments:
                        # if available, filter segments with high no_speech_prob
                        try:
                            if getattr(seg, "no_speech_prob", 0.0) > 0.9:
                                continue
                        except Exception:
                            pass
                        for w in getattr(seg, "words", []) or []:
                            txt = getattr(w, "word", "")
                            if txt:
                                new_words_text.append(txt.strip())

                    # Merge full-window hypothesis into running text using overlap-aware merge
                    new_str = _clean_text(" ".join(new_words_text)) if new_words_text else ""
                    if new_str:
                        self.text = merge_with_overlap(self.text, new_str, max_overlap_words=15)

                    # keep last window in buffer
                    buf = bytearray(buf[-need:])
                except Exception:
                    pass

    def _tail_prompt_words(self, max_words: int = 24) -> str:
        toks = re.findall(r"\w+", self.text, flags=re.UNICODE)
        if not toks:
            return ""
        return " ".join(toks[-max_words:])

