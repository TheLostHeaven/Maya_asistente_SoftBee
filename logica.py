import os
import whisper
import sounddevice as sd
import numpy as np
import pyttsx3
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv
import re
import warnings
from mysql.connector import Error
import json
import pygame  # 👈 Reemplazamos winsound por pygame.mixer
import threading
from fuzzywuzzy import fuzz
from pathlib import Path
from modelo import DatabaseModel

# Configuración inicial
load_dotenv()
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")

# Inicialización de componentes de audio
model = whisper.load_model("small")
engine = pyttsx3.init()
engine.setProperty('rate', 180)
engine.setProperty('voice', 'spanish')

# Inicializar pygame.mixer (requiere un archivo WAV para el pitido)
pygame.mixer.init()
BEEP_SOUND = pygame.mixer.Sound("beep.wav")  # 👈 Necesitas un archivo beep.wav

class Logica:
    # Variables de clase compartidas
    model = model
    engine = engine

    @staticmethod
    def es_dispositivo_movil():
        """Determina si el código se ejecuta en un dispositivo móvil"""
        try:
            # Para Android
            if 'ANDROID_STORAGE' in os.environ:
                return True
            # Para iOS (aproximación)
            if 'HOME' in os.environ and 'Mobile' in os.environ['HOME']:
                return True
            return False
        except:
            return False

    @staticmethod
    def cargar_monitoreos_pendientes():
        """Carga todos los monitoreos pendientes de sincronizar desde archivos JSON"""
        try:
            temp_dir = Path("monitoreos_temp")
            if not temp_dir.exists():
                return []
                
            monitoreos = []
            for archivo in temp_dir.glob("monitoreo_*.json"):
                try:
                    with open(archivo, 'r', encoding='utf-8') as f:
                        datos = json.load(f)
                        datos['_archivo'] = str(archivo)
                        monitoreos.append(datos)
                except json.JSONDecodeError as e:
                    print(f"Error al leer archivo {archivo}: {e}")
                    continue
                    
            return monitoreos
        except Exception as e:
            print(f"Error al cargar monitoreos pendientes: {e}")
            return []

    @staticmethod
    def guardar_monitoreo_temp(datos):
        """Guarda los datos de monitoreo en un archivo temporal JSON"""
        try:
            temp_dir = Path("monitoreos_temp")
            temp_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = temp_dir / f"monitoreo_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)
                
            return True
        except Exception as e:
            print(f"Error al guardar temporalmente: {e}")
            return False

    @staticmethod
    def palabras_a_numero(texto):
        """Convierte palabras de números en español a valores numéricos"""
        if not texto:
            return None
            
        texto = re.sub(r'[^a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]', '', texto.lower()).strip()
        
        numeros = {
            'cero': 0, 'sero': 0, 'xero': 0,
            'uno': 1, 'un': 1, 'una': 1, 'primero': 1, 'primer': 1, 'úno': 1, 'ino': 1,
            'dos': 2, 'segundo': 2, 'dós': 2, 'tres': 3, 'tercero': 3, 'tercer': 3, 'trés': 3,
            'cuatro': 4, 'cuarto': 4, 'kuatro': 4, 'quatro': 4,
            'cinco': 5, 'quinto': 5, 'sinko': 5, 'zinko': 5,
            'seis': 6, 'sexto': 6, 'séis': 6, 'seyis': 6,
            'siete': 7, 'séptimo': 7, 'síete': 7, 'ciete': 7,
            'ocho': 8, 'octavo': 8, 'ócho': 8, 'otcho': 8,
            'nueve': 9, 'noveno': 9, 'nuéve': 9, 'nuebe': 9,
            'diez': 10, 'décimo': 10, 'diéz': 10, 'dies': 10,
            'once': 11, 'undécimo': 11, 'ónce': 11, 'onse': 11,
            'doce': 12, 'duodécimo': 12, 'dóce': 12, 'dose': 12,
            'trece': 13, 'tréce': 13, 'trese': 13,
            'catorce': 14, 'katorce': 14,
            'quince': 15, 'kinse': 15,
            'dieciseis': 16, 'dieciséis': 16, 'diez y seis': 16,
            'diecisiete': 17, 'diez y siete': 17,
            'dieciocho': 18, 'diez y ocho': 18,
            'diecinueve': 19, 'diez y nueve': 19,
            'veinte': 20, 'veintiuno': 21, 'veintiún': 21, 'veintiuna': 21,
            'veintidós': 22, 'veintitrés': 23, 'veinticuatro': 24,
            'veinticinco': 25, 'veintiséis': 26, 'veintisiete': 27,
            'veintiocho': 28, 'veintinueve': 29,
            'treinta': 30, 'cuarenta': 40, 'cincuenta': 50,
            'sesenta': 60, 'setenta': 70, 'ochenta': 80,
            'noventa': 90, 'cien': 100, 'ciento': 100,
            'doscientos': 200, 'trescientos': 300, 'cuatrocientos': 400,
            'quinientos': 500, 'seiscientos': 600, 'setecientos': 700,
            'ochocientos': 800, 'novecientos': 900, 'mil': 1000
        }
        
        if texto in numeros:
            return numeros[texto]
        
        for palabra, num in numeros.items():
            if fuzz.ratio(texto, palabra) > 80:
                return num
        
        if 'y' in texto:
            partes = [p.strip() for p in texto.split('y')]
            if len(partes) == 2:
                num1 = numeros.get(partes[0], 0)
                num2 = numeros.get(partes[1], 0)
                return num1 + num2
        
        return None

    @staticmethod
    def confirmacion_reconocida(respuesta, palabra_clave):
        """Reconoce confirmaciones con tolerancia a errores"""
        umbral_similitud = 70
        
        variaciones = {
            'confirmar': ['confirmar', 'confirma', 'confirmo', 'confirmado', 'confirmad', 'conforme', 'confirmas'],
            'cancelar': ['cancelar', 'cancela', 'cancelado', 'cancelo', 'cancelad', 'cancelen']
        }
        
        respuesta = respuesta.lower().strip()
        
        if palabra_clave in respuesta:
            return True
        
        if any(v in respuesta for v in variaciones.get(palabra_clave, [])):
            return True
        
        if fuzz.ratio(respuesta, palabra_clave) > umbral_similitud:
            return True
        
        for variacion in variaciones.get(palabra_clave, []):
            if fuzz.ratio(respuesta, variacion) > umbral_similitud:
                return True
        
        return False

    @staticmethod
    def procesar_respuesta_pregunta(pregunta, respuesta, intentos, respuestas):
        """Procesa la respuesta a una pregunta específica"""
        pregunta_respondida = False
        
        if pregunta['tipo'] == 'opcion':
            respuesta = respuesta.lower()
            
            # Primero intentar reconocer números (1, 2, 3...)
            numero_opcion = None
            try:
                numero_opcion = int(respuesta)
            except ValueError:
                numero_opcion = Logica.palabras_a_numero(respuesta)
            
            if numero_opcion is not None and 1 <= numero_opcion <= len(pregunta['opciones']):
                respuestas[pregunta['id']] = pregunta['opciones'][numero_opcion-1]
                pregunta_respondida = True
            else:
                # Búsqueda por texto como respaldo
                opciones = [o.lower() for o in pregunta['opciones']]
                for i, op in enumerate(opciones):
                    if op in respuesta or any(palabra in op for palabra in respuesta.split()):
                        respuestas[pregunta['id']] = pregunta['opciones'][i]
                        pregunta_respondida = True
                        break
            
            if not pregunta_respondida and intentos < 2:
                opciones_numeradas = [f"{n+1} para {o}" for n, o in enumerate(pregunta['opciones'])]
                return False, f"Opción no reconocida. Por favor diga el número de la opción: {', '.join(opciones_numeradas)}"
                
        elif pregunta['tipo'] == 'numero':
            try:
                num = int(respuesta)
                min_val = pregunta.get('min', 0)
                max_val = pregunta.get('max', 100)
                if min_val <= num <= max_val:
                    respuestas[pregunta['id']] = num
                    pregunta_respondida = True
                else:
                    if intentos < 2:
                        return False, f"El valor debe estar entre {min_val} y {max_val}"
            except ValueError:
                num = Logica.palabras_a_numero(respuesta)
                if num is not None and pregunta.get('min', 0) <= num <= pregunta.get('max', 100):
                    respuestas[pregunta['id']] = num
                    pregunta_respondida = True
                else:
                    if intentos < 2:
                        return False, "No entendí el número. Por favor responda con un valor numérico."
        else:  # Tipo texto
            respuestas[pregunta['id']] = respuesta
            pregunta_respondida = True
        
        return pregunta_respondida, ""

    @staticmethod
    def sincronizar_monitoreos_pendientes():
        """Sincroniza todos los monitoreos pendientes con la base de datos"""
        if not Logica.es_dispositivo_movil():
            print("La sincronización solo está disponible en dispositivos móviles")
            return False
            
        monitoreos = Logica.cargar_monitoreos_pendientes()
        if not monitoreos:
            print("No hay monitoreos pendientes por sincronizar")
            return True
            
        print(f"\nHay {len(monitoreos)} monitoreos pendientes por sincronizar")
        
        for i, monitoreo in enumerate(monitoreos, 1):
            archivo = monitoreo.pop('_archivo')  # Eliminamos la ruta del archivo
            print(f"\nSincronizando monitoreo {i}/{len(monitoreos)}...")
            
            # Usamos la función de guardado del modelo
            if DatabaseModel.guardar_respuestas(monitoreo):
                # Si se guardó correctamente, eliminamos el archivo temporal
                try:
                    os.remove(archivo)
                    print("✓ Sincronizado correctamente")
                except Exception as e:
                    print(f"✓ Sincronizado pero error al borrar temporal: {e}")
            else:
                print("✗ Error al sincronizar este monitoreo")
                return False
                
        return True

    @staticmethod
    def emitir_pitido(frecuencia=1000, duracion=200):
        """Emite un pitido usando pygame.mixer en lugar de winsound"""
        BEEP_SOUND.play()

    @staticmethod
    def escuchar(duracion=3):
        """Función para capturar audio y transcribirlo"""
        try:
            samplerate = 16000
            
            threading.Thread(target=Logica.emitir_pitido).start()
            
            print("\n[ESCUCHANDO...]")
            audio = sd.rec(
                int(duracion * samplerate),
                samplerate=samplerate,
                channels=1,
                dtype='float32'
            )
            
            sd.wait()
            
            audio_np = audio.flatten()
            audio_np = audio_np / np.max(np.abs(audio_np))
            
            result = Logica.model.transcribe(
                audio_np.astype(np.float32),
                language="es",
                temperature=0.0,
                best_of=1,
                beam_size=2
            )
            
            texto = result["text"].strip()
            if texto:
                print(f"USUARIO: {texto}")
                return texto.lower()
            return None
            
        except Exception as e:
            print(f"Error al escuchar: {str(e)}")
            return None

    @staticmethod
    def hablar(texto):
        """Función para sintetizar voz"""
        print(f"ASISTENTE: {texto}")
        threading.Thread(target=Logica.engine.say, args=(texto,)).start()
        Logica.engine.runAndWait()

if _name_ == "_main_":
    # Ejemplo de uso
    Logica.hablar("Sistema de monitoreo de colmenas inicializado")
    respuesta = Logica.escuchar(5)
    if respuesta:
        print(f"Respuesta reconocida: {respuesta}")