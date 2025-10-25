#!/usr/bin/env python3
"""
Script para verificar y diagnosticar problemas con el modelo de whisper.cpp
"""
import os
import sys
from pathlib import Path

def check_model(model_path: str):
    """Verifica si un modelo de whisper.cpp es válido"""
    print(f"🔍 Verificando modelo: {model_path}")
    print("-" * 60)
    
    # Expandir ~ si está presente
    model_path = os.path.expanduser(model_path)
    
    # Verificar existencia
    if not os.path.exists(model_path):
        print(f"❌ ERROR: El archivo no existe")
        print(f"   Ruta buscada: {model_path}")
        return False
    
    print(f"✅ Archivo existe")
    
    # Verificar tamaño
    size = os.path.getsize(model_path)
    size_mb = size / 1024 / 1024
    print(f"📦 Tamaño: {size:,} bytes ({size_mb:.2f} MB)")
    
    if size < 1024 * 1024:  # menos de 1 MB
        print(f"❌ ERROR: El archivo es demasiado pequeño (< 1 MB)")
        print(f"   Probablemente esté corrupto o incompleto")
        return False
    
    # Verificar magic bytes
    try:
        with open(model_path, 'rb') as f:
            magic = f.read(6)
            magic_hex = magic.hex()
            magic_str = magic.decode('ascii', errors='ignore')
            
            print(f"🔢 Magic bytes: {magic_hex} ({repr(magic_str)})")
            
            if magic.startswith(b'ggml'):
                print(f"✅ Formato GGML detectado (whisper.cpp antiguo)")
                return True
            elif magic.startswith(b'ggjt'):
                print(f"✅ Formato GGJT detectado (whisper.cpp nuevo)")
                return True
            else:
                print(f"❌ ERROR: Magic bytes no reconocidos")
                print(f"   Esperado: 'ggml' o 'ggjt'")
                print(f"   Encontrado: {magic[:4]}")
                print()
                print(f"⚠️  Este archivo NO es un modelo válido de whisper.cpp")
                return False
    except Exception as e:
        print(f"❌ ERROR leyendo archivo: {e}")
        return False

def print_download_instructions():
    """Imprime instrucciones para descargar modelos correctos"""
    print()
    print("=" * 60)
    print("📥 CÓMO DESCARGAR MODELOS CORRECTOS")
    print("=" * 60)
    print()
    print("Los modelos de whisper.cpp están disponibles en:")
    print("  https://huggingface.co/ggerganov/whisper.cpp/tree/main")
    print()
    print("Modelos recomendados (español):")
    print()
    print("  • tiny (75 MB)   - Rápido, menor precisión")
    print("    wget https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin")
    print()
    print("  • base (142 MB)  - Balance velocidad/precisión")
    print("    wget https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin")
    print()
    print("  • small (466 MB) - Buena precisión (RECOMENDADO)")
    print("    wget https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin")
    print()
    print("  • medium (1.5 GB) - Muy buena precisión")
    print("    wget https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin")
    print()
    print("Ejemplo de descarga:")
    print("  mkdir -p ~/.models")
    print("  cd ~/.models")
    print("  wget https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin")
    print()
    print("Luego actualiza la ruta en app/config.py:")
    print("  model_path: str = \"~/.models/ggml-small.bin\"")
    print()

def main():
    if len(sys.argv) < 2:
        print("Uso: python check_model.py <ruta_al_modelo>")
        print()
        print("Ejemplo:")
        print("  python check_model.py ~/.models/ggml-small.bin")
        print()
        
        # Intentar verificar el modelo por defecto
        default_model = "~/.models/ggml-small.bin"
        print(f"Intentando verificar modelo por defecto: {default_model}")
        print()
        is_valid = check_model(default_model)
    else:
        model_path = sys.argv[1]
        is_valid = check_model(model_path)
    
    if not is_valid:
        print_download_instructions()
        sys.exit(1)
    else:
        print()
        print("✅ El modelo parece válido y compatible con whisper.cpp")
        sys.exit(0)

if __name__ == "__main__":
    main()
