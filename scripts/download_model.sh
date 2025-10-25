#!/bin/bash
# Script para descargar modelos de whisper.cpp

set -e

MODELS_DIR="${HOME}/.models"
REPO_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main"

echo "=================================================="
echo "  Descargador de Modelos whisper.cpp"
echo "=================================================="
echo ""

# Crear directorio si no existe
mkdir -p "$MODELS_DIR"
echo "📁 Directorio de modelos: $MODELS_DIR"
echo ""

# Menú de selección
echo "Selecciona el modelo a descargar:"
echo ""
echo "  1) tiny   (75 MB)   - Rápido, menor precisión"
echo "  2) base   (142 MB)  - Balance velocidad/precisión"
echo "  3) small  (466 MB)  - Buena precisión (RECOMENDADO)"
echo "  4) medium (1.5 GB)  - Muy buena precisión"
echo "  5) large  (2.9 GB)  - Máxima precisión (muy lento)"
echo ""
read -p "Opción [3]: " choice
choice=${choice:-3}

case $choice in
    1)
        MODEL="ggml-tiny.bin"
        ;;
    2)
        MODEL="ggml-base.bin"
        ;;
    3)
        MODEL="ggml-small.bin"
        ;;
    4)
        MODEL="ggml-medium.bin"
        ;;
    5)
        MODEL="ggml-large-v3.bin"
        ;;
    *)
        echo "❌ Opción inválida"
        exit 1
        ;;
esac

MODEL_PATH="${MODELS_DIR}/${MODEL}"
MODEL_URL="${REPO_URL}/${MODEL}"

# Verificar si ya existe
if [ -f "$MODEL_PATH" ]; then
    echo "⚠️  El archivo ya existe: $MODEL_PATH"
    read -p "¿Descargar de nuevo? [s/N]: " overwrite
    if [[ ! "$overwrite" =~ ^[sS]$ ]]; then
        echo "✅ Usando modelo existente"
        exit 0
    fi
    echo "🗑️  Eliminando archivo anterior..."
    rm -f "$MODEL_PATH"
fi

echo ""
echo "📥 Descargando: $MODEL"
echo "    Desde: $MODEL_URL"
echo "    Hacia: $MODEL_PATH"
echo ""

# Descargar con wget o curl
if command -v wget &> /dev/null; then
    wget --progress=bar:force -O "$MODEL_PATH" "$MODEL_URL"
elif command -v curl &> /dev/null; then
    curl -L --progress-bar -o "$MODEL_PATH" "$MODEL_URL"
else
    echo "❌ ERROR: Se requiere wget o curl para descargar"
    exit 1
fi

# Verificar descarga
if [ -f "$MODEL_PATH" ]; then
    SIZE=$(stat -f%z "$MODEL_PATH" 2>/dev/null || stat -c%s "$MODEL_PATH" 2>/dev/null)
    SIZE_MB=$((SIZE / 1024 / 1024))
    echo ""
    echo "✅ Descarga completada: $SIZE_MB MB"
    
    # Verificar magic bytes
    MAGIC=$(xxd -l 4 -p "$MODEL_PATH")
    if [[ "$MAGIC" == "67676d6c" ]] || [[ "$MAGIC" == "67676a74" ]]; then
        echo "✅ Modelo válido (magic bytes correctos)"
    else
        echo "⚠️  Advertencia: Magic bytes no reconocidos: $MAGIC"
    fi
    
    echo ""
    echo "=================================================="
    echo "  ✅ MODELO LISTO PARA USAR"
    echo "=================================================="
    echo ""
    echo "Ruta del modelo: $MODEL_PATH"
    echo ""
    echo "Actualiza app/config.py con:"
    echo "  model_path: str = \"$MODEL_PATH\""
    echo ""
else
    echo "❌ ERROR: La descarga falló"
    exit 1
fi
