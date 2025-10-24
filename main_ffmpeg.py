import subprocess
from pynput import keyboard
import signal
import sys
import os
import time
import uuid

FRECUENCIA_MUESTREO = 48000
CANALES = 2
CODEC_AUDIO = "pcm_s16le"
FORMATO_SALIDA = "wav"
nombre_archivo = ""
COMBINACION_GRABAR = {keyboard.Key.ctrl, keyboard.Key.shift}

WHISPER_MODEL = "whisper.cpp/models/ggml-small.bin"
WHISPER_IDIOMA = "es"
TRANSCRIBIR_AUTO = True

DISPOSITIVO_AUDIO = "pulse"
INPUT_DEVICE = "default"
teclas_presionadas = set()
grabacion_activa = False
proceso_ffmpeg = None
listener_activo = None


def iniciar_grabacion():
    """Inicia la grabación de audio usando ffmpeg."""
    global proceso_ffmpeg, grabacion_activa, nombre_archivo

    nombre_archivo = f"{uuid.uuid4().hex}.wav"

    print("[REC] Grabando! Suelta las teclas para detener...")

    comando = [
        "ffmpeg",
        "-f",
        DISPOSITIVO_AUDIO,
        "-i",
        INPUT_DEVICE,
        "-ar",
        str(FRECUENCIA_MUESTREO),
        "-ac",
        str(CANALES),
        "-acodec",
        CODEC_AUDIO,
        "-y",
        nombre_archivo,
    ]

    try:
        proceso_ffmpeg = subprocess.Popen(
            comando, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        grabacion_activa = True

    except FileNotFoundError:
        print("[ERROR] ffmpeg no esta instalado o no esta en el PATH")
        grabacion_activa = False
    except Exception as e:
        print(f"[ERROR] Error al iniciar grabacion: {e}")
        grabacion_activa = False


def detener_y_guardar_grabacion():
    """Detiene la grabación enviando señal SIGINT a ffmpeg."""
    global grabacion_activa, proceso_ffmpeg

    if grabacion_activa and proceso_ffmpeg:
        print("[STOP] Deteniendo grabacion...")
        grabacion_activa = False

        try:
            proceso_ffmpeg.send_signal(signal.SIGINT)

            proceso_ffmpeg.wait(timeout=5)

            if os.path.exists(nombre_archivo):
                tamanio = os.path.getsize(nombre_archivo)
                print(f"[OK] Grabacion guardada! ({tamanio} bytes)")
                
                if TRANSCRIBIR_AUTO:
                    transcripcion = transcribir_audio(nombre_archivo)
                    if transcripcion:
                        print(f"\n--- Transcripcion:\n{transcripcion}\n")
            else:
                print("[WARNING] Grabacion detenida pero no se encontro el archivo")

        except subprocess.TimeoutExpired:
            print("[WARNING] Forzando cierre de ffmpeg...")
            proceso_ffmpeg.kill()
            proceso_ffmpeg.wait()
        except Exception as e:
            print(f"[ERROR] Error al detener grabacion: {e}")

        proceso_ffmpeg = None


def al_presionar(key):
    """Callback para cuando una tecla es presionada."""
    global grabacion_activa

    if key in COMBINACION_GRABAR and not grabacion_activa:
        teclas_presionadas.add(key)
        if teclas_presionadas == COMBINACION_GRABAR:
            iniciar_grabacion()


def al_soltar(key):
    """Callback para cuando una tecla es soltada."""
    if key == keyboard.Key.esc:
        salir_programa()
        return False

    if key in COMBINACION_GRABAR:
        try:
            teclas_presionadas.remove(key)
        except KeyError:
            pass

        detener_y_guardar_grabacion()


def salir_programa():
    """Limpia recursos y sale del programa."""
    global listener_activo
    print("\n[EXIT] Saliendo del programa...")

    if grabacion_activa:
        detener_y_guardar_grabacion()

    if listener_activo:
        listener_activo.stop()

    sys.exit(0)


def manejador_sigint(sig, frame):
    """Manejador para CTRL + C."""
    salir_programa()


def verificar_ffmpeg():
    """Verifica que ffmpeg esté instalado y funcional."""
    try:
        resultado = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3,
        )
        return resultado.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def transcribir_audio(ruta_audio, modelo=None, idioma=None):
    """Transcribe un archivo de audio usando whisper-cli.
    
    Args:
        ruta_audio: Ruta del archivo de audio a transcribir
        modelo: Ruta al modelo de whisper (opcional, usa WHISPER_MODEL por defecto)
        idioma: Código del idioma (opcional, usa WHISPER_IDIOMA por defecto)
    
    Returns:
        str: Texto transcrito o None si hay error
    """
    if modelo is None:
        modelo = WHISPER_MODEL
    if idioma is None:
        idioma = WHISPER_IDIOMA
    
    if not os.path.exists(ruta_audio):
        print(f"[ERROR] El archivo {ruta_audio} no existe")
        return None
    
    if not os.path.exists(modelo):
        print(f"[ERROR] Modelo de whisper no encontrado en {modelo}")
        return None
    
    print("[*] Transcribiendo audio...")
    
    comando = [
        "whisper-cli",
        "-m", modelo,
        "-f", ruta_audio,
        "-l", idioma,
        "-nt"
    ]
    
    try:
        resultado = subprocess.run(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            text=True
        )
        
        if resultado.returncode == 0:
            texto = resultado.stdout.strip()
            return texto if texto else None
        else:
            print(f"[ERROR] Error en whisper-cli: {resultado.stderr}")
            return None
            
    except FileNotFoundError:
        print("[ERROR] whisper-cli no esta instalado o no esta en el PATH")
        return None
    except subprocess.TimeoutExpired:
        print("[ERROR] La transcripcion tardo demasiado (timeout)")
        return None
    except Exception as e:
        print(f"[ERROR] Error al transcribir: {e}")
        return None


def verificar_whisper():
    """Verifica que whisper-cli esté instalado."""
    try:
        resultado = subprocess.run(
            ["whisper-cli", "-h"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3
        )
        return resultado.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def detectar_sistema_audio():
    """Detecta el sistema de audio disponible."""
    global DISPOSITIVO_AUDIO, INPUT_DEVICE

    try:
        resultado = subprocess.run(
            ["pactl", "info"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2
        )
        if resultado.returncode == 0:
            DISPOSITIVO_AUDIO = "pulse"
            INPUT_DEVICE = "default"
            return "PulseAudio"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    DISPOSITIVO_AUDIO = "alsa"
    INPUT_DEVICE = "default"
    return "ALSA"


if __name__ == "__main__":
    signal.signal(signal.SIGINT, manejador_sigint)

    if not verificar_ffmpeg():
        print("[ERROR] ffmpeg no esta instalado")
        print("Instalalo con: sudo pacman -S ffmpeg  (en Manjaro/Arch)")
        sys.exit(1)

    sistema_audio = detectar_sistema_audio()
    
    whisper_disponible = False
    if TRANSCRIBIR_AUTO:
        whisper_disponible = verificar_whisper()
        if not whisper_disponible:
            print("[WARNING] whisper-cli no esta disponible. Transcripcion deshabilitada.")
            TRANSCRIBIR_AUTO = False

    print(f"*** Grabador de Audio FFmpeg - {FRECUENCIA_MUESTREO}Hz Estereo ***")
    print(f"[AUDIO] Sistema de audio: {sistema_audio}")
    if TRANSCRIBIR_AUTO:
        print(f"[AI] Transcripcion automatica: Activada (idioma: {WHISPER_IDIOMA})")
    print("Manten presionado Ctrl + Shift para grabar.")
    print("Presiona Esc o Ctrl + C para salir del programa.")

    with keyboard.Listener(on_press=al_presionar, on_release=al_soltar) as listener:
        listener_activo = listener
        listener.join()
