# Dictáfono con pywebview + ffmpeg + whisper-cli (whisper.cpp)

Aplicación de dictado para Linux (probado en Manjaro) que:
- Muestra un wavebar flotante y transparente al mantener Ctrl+Alt (no roba foco).
- Graba audio con ffmpeg mientras mantienes la combinación de teclas (push‑to‑talk) y visualiza el nivel con sounddevice.
- Al soltar, transcribe el archivo completo con `whisper-cli` (whisper.cpp) e inserta el texto en la app con foco mediante portapapeles (Ctrl+V / Ctrl+Shift+V / Shift+Insert o clic medio/PRIMARY); si no es posible, hace fallback a tipeo humano.

## Requisitos

- Python 3.13+
- ffmpeg instalado
- whisper.cpp compilado y `whisper-cli` disponible en PATH (enlace a `main` de whisper.cpp)
- (Recomendado) Herramientas para pegado/ventanas según entorno:
  - X11: `xdotool`, `xprop`, y opcionalmente `xclip`/`xsel` (PRIMARY)
  - Wayland: `wl-copy`/`wl-paste` (wl-clipboard) y opcionalmente `wtype`
- Dependencias Python (uv):
  - pywebview (Qt backend), qtpy, PyQt6, PyQt6-WebEngine
  - sounddevice, numpy
  - pynput, pyperclip

Instalación rápida (con uv):

```bash
uv sync
```

## Uso

Por defecto, el programa se ejecuta en segundo plano (desacoplado de la terminal):

```bash
uv run main_desktop_gui.py
```

Para ejecutar en primer plano (útil para debugging):

```bash
uv run main_desktop_gui.py --no-detach
# o
uv run main_desktop_gui.py --foreground
# o
uv run main_desktop_gui.py -f
```

Para ver todas las opciones:

```bash
uv run main_desktop_gui.py --help
```

### Funcionamiento

- El programa se inicia en segundo plano y aparece un icono en la bandeja del sistema (system tray)
- Por defecto, el atajo está **desactivado**. Actívalo desde el menú del icono de bandeja (clic derecho → "Activar atajo")
- Una vez activado, mantén Ctrl+Alt para empezar a grabar y ver el wavebar (no roba foco)
- Suelta para detener, transcribir el archivo completo, eliminar el archivo temporal y pegar el resultado en la app con foco (Ctrl+V/Ctrl+Shift+V/Shift+Insert/PRIMARY); si falla, se tipea a velocidad humana. Durante el pegado se desactiva temporalmente el atajo global para evitar bucles (p. ej., en terminales como Rio)
- Para salir: clic derecho en el icono de bandeja → "Salir"

### Verificar que el proceso está corriendo

```bash
ps aux | grep main_desktop_gui | grep -v grep
```

### Ver logs en tiempo real

```bash
tail -f ~/.local/share/audio-record/dictafono.log
```

### Detener el proceso manualmente

```bash
pkill -f 'python.*main_desktop_gui'
```

### Configuración

**Importante**: Debes descargar y colocar el modelo de IA antes de usar la aplicación.

Por defecto, la aplicación busca el modelo en `~/.models/ggml-small.bin`. Puedes:
1. Descargar el modelo y colocarlo en esa ubicación:
   ```bash
   mkdir -p ~/.models
   # Descarga el modelo desde https://huggingface.co/ggerganov/whisper.cpp
   # y colócalo en ~/.models/ggml-small.bin
   ```
2. O editar `app/config.py` → `WhisperConfig` → `model_path` para apuntar a otra ubicación.

Otras opciones configurables:
- `language`: `"es"` por defecto.
- Los campos `rt_backend` y `stream_*` se ignoran en el modo diferido actual.

Adicional:
- Puedes definir la variable de entorno `WHISPER_CLI` para apuntar al binario. Si el binario no está en PATH, se intentan también rutas locales del repo.
- En modo detach, la app se lanza con el directorio del proyecto como CWD para que funcionen rutas relativas; `model_path` se normaliza a ruta absoluta automáticamente.

Si `whisper-cli` no está en PATH, crea un alias o symlink apuntando al binario `main` de whisper.cpp.

## Notas

- Los archivos de audio se guardan temporalmente en la carpeta del sistema y se eliminan automáticamente tras la transcripción para evitar acumulación de archivos.
- En Wayland, la inyección de teclas/pegado puede requerir herramientas específicas (wl-clipboard) o ajustes del compositor.
- En Qt/Linux, la transparencia está soportada; en otros entornos puede variar.
- La velocidad de tipeo (fallback) puede ajustarse en `app/insertion.py` (`type_text_human`, parámetros `min_delay` y `max_delay`).
- En terminales (p. ej., Rio), el pegado usa primero Ctrl+Shift+V, luego Shift+Insert y como alternativa PRIMARY (clic medio).
