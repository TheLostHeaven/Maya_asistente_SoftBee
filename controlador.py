# controlador.py (modificado)
from flask import Flask, request, jsonify
from modelo import DatabaseModel
from logica import Logica
import whisper
import sounddevice as sd
import numpy as np
import pyttsx3
import threading
import pygame  
from datetime import datetime
import json

# ================= CONFIGURACIÓN INICIAL =================
app = Flask(_name_)

# Configuración para síntesis de voz
engine = pyttsx3.init()
engine.setProperty('rate', 180)
engine.setProperty('voice', 'spanish')

# Configuración para reconocimiento de voz
WHISPER_MODEL = "tiny"
model = whisper.load_model(WHISPER_MODEL)

# Inicializar pygame.mixer
pygame.mixer.init()
BEEP_SOUND = pygame.mixer.Sound("beep.wav")  # 👈 Archivo WAV para el pitido

# ================= FUNCIONES AUXILIARES =================
def emitir_pitido(frecuencia=1000, duracion=200):
    """Emite un pitido usando pygame.mixer"""
    BEEP_SOUND.play()

def procesar_respuesta_numerica(respuesta):
    """Convierte respuesta de voz a número"""
    try:
        return int(''.join(filter(str.isdigit, respuesta)))
    except:
        return None

def validar_opcion(respuesta, opciones_validas):
    """Valida que la respuesta coincida con las opciones"""
    respuesta = respuesta.lower()
    for opcion in opciones_validas:
        if opcion.lower() in respuesta:
            return opcion
    return None

def validar_numero(respuesta, min_val=None, max_val=None):
    """Valida y ajusta números dentro de rangos"""
    try:
        num = int(''.join(filter(str.isdigit, respuesta)))
        if min_val is not None and num < min_val:
            return min_val
        if max_val is not None and num > max_val:
            return max_val
        return num
    except:
        return None

# ================= RUTAS PARA PREGUNTAS =================
@app.route('/api/preguntas', methods=['GET'])
def obtener_preguntas():
    """Obtiene todas las preguntas configuradas"""
    preguntas = DatabaseModel.cargar_preguntas_desde_bd()
    if preguntas is None:
        return jsonify({'error': 'No se pudieron cargar las preguntas desde el get'}), 500
    return jsonify(preguntas)

@app.route('/api/preguntas', methods=['POST'])
def crear_pregunta():
    """Crea una nueva pregunta"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Datos no proporcionados'}), 400
    
    preguntas = DatabaseModel.cargar_preguntas_desde_bd()
    if preguntas is None:
        return jsonify({'error': 'No se pudieron cargar las preguntas desde el post'}), 500
    
    if any(p['id'] == data.get('id') for p in preguntas):
        return jsonify({'error': 'El ID de pregunta ya existe'}), 400
    
    preguntas.append(data)
    if not DatabaseModel.aplicar_cambios_preguntas(preguntas):
        return jsonify({'error': 'Error al guardar en la base de datos'}), 500
    
    return jsonify(data), 201

@app.route('/api/preguntas/<string:pregunta_id>', methods=['PUT'])
def actualizar_pregunta(pregunta_id):
    """Actualiza una pregunta existente"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Datos no proporcionados'}), 400
    
    preguntas = DatabaseModel.cargar_preguntas_desde_bd()
    if preguntas is None:
        return jsonify({'error': 'No se pudieron cargar las preguntas desde el put'}), 500
    
    for i, p in enumerate(preguntas):
        if p['id'] == pregunta_id:
            preguntas[i] = data
            if not DatabaseModel.aplicar_cambios_preguntas(preguntas):
                return jsonify({'error': 'Error al guardar en la base de datos'}), 500
            return jsonify(data)
    
    return jsonify({'error': 'Pregunta no encontrada'}), 404

@app.route('/api/preguntas/<string:pregunta_id>', methods=['DELETE'])
def eliminar_pregunta(pregunta_id):
    """Elimina (desactiva) una pregunta"""
    preguntas = DatabaseModel.cargar_preguntas_desde_bd()
    if preguntas is None:
        return jsonify({'error': 'No se pudieron cargar las preguntas desde delete'}), 500
    
    for p in preguntas:
        if p['id'] == pregunta_id:
            p['activa'] = False
            if not DatabaseModel.aplicar_cambios_preguntas(preguntas):
                return jsonify({'error': 'Error al guardar en la base de datos'}), 500
            return jsonify({'message': 'Pregunta desactivada correctamente'})
    
    return jsonify({'error': 'Pregunta no encontrada'}), 404

# ================= RUTAS PARA APIARIOS =================
@app.route('/api/apiarios', methods=['GET'])
def obtener_apiarios():
    """Obtiene todos los apiarios"""
    apiarios = DatabaseModel.obtener_apiarios()
    if apiarios is None:
        return jsonify({'error': 'No se pudieron obtener los apiarios'}), 500
    return jsonify(apiarios)

@app.route('/api/apiarios', methods=['POST'])
def crear_apiario():
    """Crea un nuevo apiario"""
    data = request.get_json()
    if not data or not data.get('nombre'):
        return jsonify({'error': 'Nombre del apiario es requerido'}), 400
    
    if DatabaseModel.agregar_apiario(data['nombre'], data.get('ubicacion', '')):
        return jsonify({'message': 'Apiario creado correctamente'}), 201
    else:
        return jsonify({'error': 'Error al crear el apiario'}), 500

@app.route('/api/apiarios/<int:apiario_id>', methods=['GET'])
def obtener_apiarios(apiario_id):
    """Obtiene un apiario específico"""
    apiario = DatabaseModel.obtener_apiarios(apiario_id)
    if apiario is None:
        return jsonify({'error': 'Error al obtener el apiario'}), 500
    if not apiario:
        return jsonify({'error': 'Apiario no encontrado'}), 404
    return jsonify(apiario)

@app.route('/api/apiarios/<int:apiario_id>', methods=['PUT'])
def actualizar_apiario(apiario_id):
    """Actualiza un apiario existente"""
    data = request.get_json()
    if not data or not data.get('nombre'):
        return jsonify({'error': 'Nombre del apiario es requerido'}), 400
    
    if DatabaseModel.actualizar_apiario(apiario_id, data['nombre'], data.get('ubicacion', '')):
        return jsonify({'message': 'Apiario actualizado correctamente'})
    else:
        return jsonify({'error': 'Error al actualizar el apiario'}), 500

@app.route('/api/apiarios/<int:apiario_id>', methods=['DELETE'])
def eliminar_apiario(apiario_id):
    """Elimina un apiario"""
    if DatabaseModel.eliminar_apiario(apiario_id):
        return jsonify({'message': 'Apiario eliminado correctamente'})
    else:
        return jsonify({'error': 'Error al eliminar el apiario'}), 500

# ================= RUTAS PARA COLMENAS =================
@app.route('/api/apiarios/<int:apiario_id>/colmenas', methods=['GET'])
def obtener_colmenas_apiario(apiario_id):
    """Obtiene las colmenas de un apiario"""
    colmenas = DatabaseModel.obtener_colmenas_apiario(apiario_id)
    if colmenas is None:
        return jsonify({'error': 'No se pudieron obtener las colmenas'}), 500
    return jsonify(colmenas)

@app.route('/api/apiarios/<int:apiario_id>/colmenas', methods=['POST'])
def crear_colmena(apiario_id):
    """Crea una nueva colmena en un apiario"""
    data = request.get_json()
    if not data or not data.get('numero_colmena'):
        return jsonify({'error': 'Número de colmena es requerido'}), 400
    
    if DatabaseModel.crear_colmena(data['numero_colmena'], apiario_id):
        return jsonify({'message': 'Colmena creada correctamente'}), 201
    else:
        return jsonify({'error': 'Error al crear la colmena'}), 500

@app.route('/api/colmenas/<int:colmena_id>', methods=['GET'])
def obtener_colmena(colmena_id):
    """Obtiene una colmena específica"""
    colmena = DatabaseModel.obtener_colmena(colmena_id)
    if colmena is None:
        return jsonify({'error': 'Error al obtener la colmena'}), 500
    if not colmena:
        return jsonify({'error': 'Colmena no encontrada'}), 404
    return jsonify(colmena)

@app.route('/api/colmenas/<int:colmena_id>', methods=['PUT'])
def actualizar_colmena(colmena_id):
    """Actualiza una colmena existente"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Datos no proporcionados'}), 400
    
    if DatabaseModel.actualizar_colmena(colmena_id, data):
        return jsonify({'message': 'Colmena actualizada correctamente'})
    else:
        return jsonify({'error': 'Error al actualizar la colmena'}), 500

@app.route('/api/colmenas/<int:colmena_id>', methods=['DELETE'])
def eliminar_colmena(colmena_id):
    """Elimina una colmena"""
    if DatabaseModel.eliminar_colmena(colmena_id):
        return jsonify({'message': 'Colmena eliminada correctamente'})
    else:
        return jsonify({'error': 'Error al eliminar la colmena'}), 500

# ================= RUTAS PARA MONITOREOS =================
@app.route('/api/monitoreos', methods=['POST'])
def crear_monitoreo():
    """Guarda un nuevo monitoreo"""
    data = request.get_json()
    if not data or not data.get('colmena') or not data.get('id_apiario'):
        return jsonify({'error': 'Datos incompletos para el monitoreo'}), 400
    
    if Logica.es_dispositivo_movil():
        if Logica.guardar_monitoreo_temp(data):
            return jsonify({'message': 'Monitoreo guardado localmente para sincronización posterior'}), 201
        else:
            return jsonify({'error': 'Error al guardar el monitoreo localmente'}), 500
    else:
        if DatabaseModel.guardar_respuestas(data):
            return jsonify({'message': 'Monitoreo guardado correctamente'}), 201
        else:
            return jsonify({'error': 'Error al guardar el monitoreo'}), 500

@app.route('/api/monitoreos/sincronizar', methods=['POST'])
def sincronizar_monitoreos():
    """Sincroniza monitoreos pendientes (para móviles)"""
    if not Logica.es_dispositivo_movil():
        return jsonify({'error': 'La sincronización solo está disponible en dispositivos móviles'}), 400
    
    if Logica.sincronizar_monitoreos_pendientes():
        return jsonify({'message': 'Monitoreos sincronizados correctamente'})
    else:
        return jsonify({'error': 'Error al sincronizar algunos monitoreos'}), 500

@app.route('/api/monitoreos/pendientes', methods=['GET'])
def obtener_monitoreos_pendientes():
    """Obtiene monitoreos pendientes de sincronizar"""
    if not Logica.es_dispositivo_movil():
        return jsonify({'error': 'Esta función solo está disponible en dispositivos móviles'}), 400
    
    monitoreos = Logica.cargar_monitoreos_pendientes()
    return jsonify(monitoreos)

@app.route('/api/monitoreos', methods=['GET'])
def obtener_monitoreos():
    """Obtiene todos los monitoreos registrados"""
    monitoreos = DatabaseModel.obtener_monitoreos()
    if monitoreos is None:
        return jsonify({'error': 'No se pudieron obtener los monitoreos'}), 500
    return jsonify(monitoreos)

@app.route('/api/monitoreos/<int:monitoreo_id>', methods=['GET'])
def obtener_monitoreo(monitoreo_id):
    """Obtiene un monitoreo específico"""
    monitoreo = DatabaseModel.obtener_monitoreo(monitoreo_id)
    if monitoreo is None:
        return jsonify({'error': 'Error al obtener el monitoreo'}), 500
    if not monitoreo:
        return jsonify({'error': 'Monitoreo no encontrado'}), 404
    return jsonify(monitoreo)

# ================= RUTAS PARA MONITOREO POR VOZ =================
@app.route('/api/monitoreo/iniciar', methods=['POST'])
def iniciar_monitoreo_voz():
    """Inicia un monitoreo guiado por voz"""
    try:
        # Saludo inicial
        hablar_texto({"texto": "Bienvenido al sistema de monitoreo de colmenas por voz. Yo soy Maya, te asistiré durante este monitoreo."})
        
        # Obtener preguntas activas
        preguntas = DatabaseModel.cargar_preguntas_desde_bd()
        if not preguntas:
            return jsonify({'error': 'No se pudieron cargar las preguntas'}), 500
            
        preguntas_activas = [p for p in preguntas if p.get('activa', True)]
        preguntas_activas.sort(key=lambda x: x.get('orden', 0))
        
        # Seleccionar apiario
        apiarios = DatabaseModel.obtener_apiarios()
        if not apiarios:
            return jsonify({'error': 'No hay apiarios registrados'}), 400
            
        hablar_texto({"texto": "Por favor indique el apiario a monitorear. Las opciones son: " + ", ".join(a['nombre'] for a in apiarios)})
        
        apiario_audio = escuchar_audio()
        if 'error' in apiario_audio:
            return jsonify({'error': 'Error al capturar audio del apiario'}), 400
            
        apiario_id = None
        for a in apiarios:
            if a['nombre'].lower() in apiario_audio.get('texto', '').lower():
                apiario_id = a['id']
                break
                
        if not apiario_id:
            return jsonify({'error': 'Apiario no reconocido'}), 400
            
        # Seleccionar colmena
        colmenas = DatabaseModel.obtener_colmenas_apiario(apiario_id)
        if not colmenas:
            return jsonify({'error': 'No hay colmenas en este apiario'}), 400
            
        hablar_texto({"texto": f"Por favor indique el número de colmena a monitorear. Las opciones son: {', '.join(str(c['numero_colmena']) for c in colmenas)}"})
        
        colmena_audio = escuchar_audio()
        if 'error' in colmena_audio:
            return jsonify({'error': 'Error al capturar audio de la colmena'}), 400
            
        numero_colmena = procesar_respuesta_numerica(colmena_audio.get('texto', ''))
        if not numero_colmena or not any(c['numero_colmena'] == numero_colmena for c in colmenas):
            return jsonify({'error': 'Número de colmena no válido'}), 400
            
        # Procesar preguntas
        respuestas = {
            'id_apiario': apiario_id,
            'colmena': numero_colmena,
            'fecha': datetime.now().isoformat(),
            'respuestas': {}
        }
        
        for pregunta in preguntas_activas:
            if pregunta.get('depende_de'):
                # Verificar dependencia
                pass
                
            intentos = 0
            pregunta_respondida = False
            
            while not pregunta_respondida and intentos < 2:
                intentos += 1
                
                texto_pregunta = pregunta['pregunta']
                if pregunta['tipo'] == 'opcion':
                    opciones = " o ".join(pregunta['opciones'])
                    texto_pregunta += f". Opciones: {opciones}"
                    
                hablar_texto({"texto": texto_pregunta})
                
                respuesta_audio = escuchar_audio()
                if 'error' in respuesta_audio:
                    continue
                    
                respuesta_texto = respuesta_audio.get('texto', '')
                
                # Procesar según tipo
                if pregunta['tipo'] == 'opcion':
                    respuesta_validada = validar_opcion(respuesta_texto, pregunta['opciones'])
                elif pregunta['tipo'] == 'numero':
                    respuesta_validada = validar_numero(respuesta_texto, pregunta.get('min'), pregunta.get('max'))
                else:
                    respuesta_validada = respuesta_texto
                    
                if respuesta_validada:
                    respuestas['respuestas'][pregunta['id']] = respuesta_validada
                    pregunta_respondida = True
                    
                    # Confirmación
                    hablar_texto({"texto": f"Has respondido: {respuesta_validada}. ¿Es correcto? Diga 'sí' para confirmar o 'no' para repetir"})
                    
                    confirmacion_audio = escuchar_audio()
                    if confirmacion_audio.get('texto', '').lower().startswith('no'):
                        pregunta_respondida = False
                        respuestas['respuestas'].pop(pregunta['id'], None)
        
        # Guardar monitoreo
        if Logica.es_dispositivo_movil():
            if Logica.guardar_monitoreo_temp(respuestas):
                hablar_texto({"texto": "Monitoreo guardado localmente para sincronización posterior"})
                return jsonify(respuestas), 201
            else:
                hablar_texto({"texto": "Error al guardar el monitoreo localmente"})
                return jsonify({'error': 'Error al guardar localmente'}), 500
        else:
            if DatabaseModel.guardar_respuestas(respuestas):
                hablar_texto({"texto": "Monitoreo completado y guardado exitosamente"})
                return jsonify(respuestas), 201
            else:
                hablar_texto({"texto": "Error al guardar el monitoreo"})
                return jsonify({'error': 'Error al guardar'}), 500
                
    except Exception as e:
        hablar_texto({"texto": f"Ocurrió un error durante el monitoreo: {str(e)}"})
        return jsonify({'error': str(e)}), 500

# ================= RUTAS PARA INTERACCIÓN POR VOZ =================
@app.route('/api/voz/hablar', methods=['POST'])
def hablar_texto():
    """Sintetiza voz a partir de texto"""
    data = request.get_json()
    if not data or not data.get('texto'):
        return jsonify({'error': 'Texto no proporcionado'}), 400
    
    texto = data['texto']
    threading.Thread(target=engine.say, args=(texto,)).start()
    engine.runAndWait()
    return jsonify({'message': 'Texto enviado para síntesis de voz'})

@app.route('/api/voz/escuchar', methods=['POST'])
def escuchar_audio():
    """Captura audio y lo transcribe"""
    data = request.get_json(silent=True)
    duracion = data.get('duracion', 5) if data else 5
    
    try:
        samplerate = 16000
        threading.Thread(target=emitir_pitido).start()
        
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
        
        result = model.transcribe(
            audio_np.astype(np.float32),
            language="es",
            temperature=0.0,
            best_of=1,
            beam_size=2
        )
        
        texto = result["text"].strip()
        if texto:
            return jsonify({'texto': texto.lower()})
        return jsonify({'error': 'No se detectó voz'}), 400
        
    except Exception as e:
        return jsonify({'error': f"Error al escuchar: {str(e)}"}), 500

# ================= INICIO DE LA APLICACIÓN =================
# Cambia la parte final del archivo a:
if _name_ == "_main_":
    app.run(host="0.0.0.0", port=8080)  # Para Flask