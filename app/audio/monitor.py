import numpy as np
import sounddevice as sd
from typing import Optional, Callable


class LiveMonitor:
    """Live audio monitor using sounddevice InputStream.

    Calls on_data(list[int]) when a new frame is available.
    """

    def __init__(self, samplerate: int, on_data: Callable[[list[int]], None], on_raw: Optional[Callable[[np.ndarray], None]] = None):
        self.samplerate = samplerate
        self.on_data = on_data
        self.on_raw = on_raw
        self.stream: Optional[sd.InputStream] = None
        self.active = False

    def _callback(self, indata, frames, time_info, status):
        if not self.active:
            return
        try:
            data = indata
            if data.ndim == 2 and data.shape[1] > 1:
                data = data.mean(axis=1)
            else:
                data = data.reshape(-1)

            # emit raw mono float32 frame for RT transcription
            if self.on_raw is not None:
                try:
                    self.on_raw(np.copy(data))
                except Exception:
                    pass

            N = 512
            if data.shape[0] > N:
                step = data.shape[0] / N
                idx = (np.arange(N) * step).astype(np.int32)
                data = data[idx]
            data = np.clip(data, -1.0, 1.0)
            buf = (data * 32767.0).astype(np.int16).tolist()
            self.on_data(buf)
        except Exception:
            pass

    def start(self):
        if self.stream is not None:
            return
        self.active = True
        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
            callback=self._callback,
            blocksize=512,
        )
        self.stream.start()

    def stop(self):
        self.active = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
