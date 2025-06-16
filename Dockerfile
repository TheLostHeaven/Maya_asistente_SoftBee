FROM python:3.10-slim

# Instala dependencias del sistema (Git + PortAudio)
RUN apt-get update && \
    apt-get install -y git libportaudio2 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Instala dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "controlador.py"]