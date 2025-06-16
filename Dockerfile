FROM python:3.9-slim

# Instala dependencias del sistema (espeak + mpg123 si usas gTTS)
RUN apt-get update && apt-get install -y \
    espeak \
    mpg123 \  # Solo necesario si usas gTTS
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "controlador.py"]