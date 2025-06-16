FROM python:3.10-slim

# Instala dependencias del sistema
RUN apt-get update && \
    apt-get install -y \
    libportaudio2 \
    espeak \
    ffmpeg \
    git && \
    rm -rf /var/lib/apt/lists/*

# Primero copia solo requirements.txt
WORKDIR /app
COPY requirements.txt .

# Instala dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Luego copia el resto del código
COPY . .

CMD ["python", "controlador.py"]