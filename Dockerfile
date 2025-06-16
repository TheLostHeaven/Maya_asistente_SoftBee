FROM python:3.10-slim  # Usa una versión compatible (3.9-3.11)

# Instala PortAudio y otras dependencias del sistema
RUN apt-get update && apt-get install -y libportaudio2

# Copia el proyecto e instala dependencias de Python
WORKDIR /app
COPY . .
RUN pip install poetry && poetry install

CMD ["poetry", "run", "python", "controlador.py"]