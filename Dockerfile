FROM python:3.10-slim

# Instala dependencias del sistema
RUN apt-get update && \
    apt-get install -y \
    libportaudio2 \
    espeak \           # Motor de síntesis de voz para Linux
    ffmpeg \           # Para procesamiento de audio
    git && \           # Para instalar whisper desde GitHub
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Instala dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "controlador.py"]