# -*- coding: utf-8 -*-
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
import winsound
import threading
from fuzzywuzzy import fuzz

# Configuración inicial
load_dotenv()
engine = pyttsx3.init()
engine.setProperty('rate', 180)
engine.setProperty('voice', 'spanish')
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")

# ================= CONFIGURACIÓN WHISPER =================
WHISPER_MODEL = "small"
model = whisper.load_model(WHISPER_MODEL)

# ================= FUNCIONES DE AUDIO =================
def hablar(texto):
    """Función para sintetizar voz"""
    print(f"ASISTENTE: {texto}")
    threading.Thread(target=engine.say, args=(texto,)).start()
    engine.runAndWait()

def emitir_pitido(frecuencia=1000, duracion=200):
    """Emite un pitido para indicar que el sistema está escuchando"""
    winsound.Beep(frecuencia, duracion)

def escuchar(duracion=3):
    """Función para capturar audio y transcribirlo"""
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
            print(f"USUARIO: {texto}")
            return texto.lower()
        return None
        
    except Exception as e:
        print(f"Error al escuchar: {str(e)}")
        return None

# ================= FUNCIONES DE CONVERSIÓN =================
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

# ================= FUNCIONES DE BASE DE DATOS =================
def get_db_connection():
    try:
        return mysql.connector.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASS'),
            database=os.getenv('DB_NAME')
        )
    except Error as err:
        hablar(f"Error de MySQL: {err.msg}")
        return None

def verificar_tablas_colmenas():
    """Verifica y crea las tablas necesarias si no existen"""
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS apiarios (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre VARCHAR(50) NOT NULL,
            ubicacion VARCHAR(100),
            fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        cursor.execute("SELECT COUNT(*) FROM apiarios")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
            INSERT INTO apiarios (nombre, ubicacion) VALUES 
            ('Norte', 'Zona norte de la finca'),
            ('Centro', 'Zona central de la finca'),
            ('Sur', 'Zona sur de la finca')
            """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS colmenas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero_colmena INT NOT NULL,
            id_apiario INT NOT NULL,
            
            actividad_piqueras ENUM('Baja', 'Media', 'Alta'),
            poblacion_abejas ENUM('Baja', 'Media', 'Alta'),
            cuadros_alimento INT,
            cuadros_cria INT,
            
            estado_colmena ENUM(
                'Cámara de cría',
                'Cámara de cría y producción',
                'Cámara de cría y doble alza de producción'
            ),
            
            estado_sanitario ENUM(
                'Presencia barroa',
                'Presencia de polilla',
                'Presencia de curruncho',
                'Mortalidad- malformación en nodrizas',
                'Ninguno'
            ),
            
            limpieza_arveneses ENUM('Si', 'No'),
            estado_postura ENUM('Huevo', 'Larva y pupa', 'Mortalidad', 'Zanganeras'),
            distribucion_postura ENUM('No hay postura', 'dispersa', 'uniforme'),
            
            almacenamiento_alimento ENUM(
                'Existe pan de abeja',
                'Almacenamiento de néctar',
                'Bajo almacenamiento'
            ),
            
            tiene_camara_produccion ENUM('Si', 'No'),
            tipo_camara_produccion ENUM('Media alza', 'Alza profunda', 'No aplica'),
            
            numero_cuadros_produccion INT,
            cuadros_estampados INT,
            cuadros_estirados INT,
            cuadros_llenado INT,
            cuadros_operculados INT,
            porcentaje_operculo VARCHAR(20),
            cuadros_cosecha INT,
            kilos_cosecha DECIMAL(5,2),
            
            observaciones TEXT,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (id_apiario) REFERENCES apiarios(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS config_preguntas (
            id VARCHAR(50) PRIMARY KEY,
            pregunta TEXT,
            tipo VARCHAR(20),
            obligatoria BOOLEAN,
            orden INT,
            min_val INT DEFAULT NULL,
            max_val INT DEFAULT NULL,
            opciones TEXT DEFAULT NULL,
            depende_de VARCHAR(50) DEFAULT NULL,
            activa BOOLEAN DEFAULT TRUE
        )
        """)
        
        conn.commit()
        return True
    except Error as err:
        print(f"Error al verificar tablas: {err}")
        return False
    finally:
        if conn.is_connected():
            conn.close()

def obtener_apiarios():
    """Obtiene la lista de apiarios disponibles"""
    conn = get_db_connection()
    if not conn:
        return None
        
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, nombre, ubicacion FROM apiarios")
        return cursor.fetchall()
    except Error as err:
        hablar(f"Error al obtener apiarios: {err.msg}")
        return None
    finally:
        if conn.is_connected():
            conn.close()

def obtener_colmenas_apiario(id_apiario):
    """Obtiene las colmenas de un apiario específico"""
    conn = get_db_connection()
    if not conn:
        return None
        
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
        SELECT id, numero_colmena 
        FROM colmenas 
        WHERE id_apiario = %s
        ORDER BY numero_colmena
        """, (id_apiario,))
        return cursor.fetchall()
    except Error as err:
        hablar(f"Error al obtener colmenas: {err.msg}")
        return None
    finally:
        if conn.is_connected():
            conn.close()

def crear_colmena(numero_colmena, id_apiario):
    """Crea una nueva colmena en el apiario especificado"""
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO colmenas (numero_colmena, id_apiario)
        VALUES (%s, %s)
        """, (numero_colmena, id_apiario))
        conn.commit()
        return True
    except Error as err:
        print(f"Error al crear colmena: {err}")
        conn.rollback()
        return False
    finally:
        if conn.is_connected():
            conn.close()

# ================= GESTIÓN DE PREGUNTAS =================
def cargar_preguntas_desde_bd():
    """Carga la estructura de preguntas desde la base de datos"""
    conn = get_db_connection()
    if not conn:
        return None
        
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Modificar esta parte para acceder correctamente al resultado
        cursor.execute("SELECT COUNT(*) as total FROM config_preguntas")
        count_result = cursor.fetchone()
        count = count_result['total'] if count_result else 0
        
        if count == 0:
            cursor.execute("SHOW COLUMNS FROM colmenas")
            columns = cursor.fetchall()
            
            exclude_columns = {'id', 'numero_colmena', 'id_apiario', 'fecha_registro'}
            preguntas = []
            
            for col in columns:
                if col['Field'] in exclude_columns:
                    continue
                    
                pregunta = {
                    'id': col['Field'],
                    'pregunta': col['Field'].replace('_', ' ').title(),
                    'tipo': 'texto',
                    'obligatoria': col['Null'] == 'NO',
                    'orden': len(preguntas) + 1,
                    'depende_de': None,
                    'activa': True
                }
                
                if 'int' in col['Type'] or 'decimal' in col['Type']:
                    pregunta['tipo'] = 'numero'
                    pregunta['min'] = 0
                    pregunta['max'] = 20 if 'cuadros' in col['Field'] else 100
                elif col['Type'].startswith('enum'):
                    pregunta['tipo'] = 'opcion'
                    pregunta['opciones'] = re.findall(r"'(.*?)'", col['Type'])
                
                preguntas.append(pregunta)
            
            for p in preguntas:
                opciones_str = json.dumps(p['opciones']) if 'opciones' in p else None
                
                cursor.execute("""
                INSERT INTO config_preguntas 
                (id, pregunta, tipo, obligatoria, orden, min_val, max_val, opciones, depende_de, activa)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    p['id'],
                    p['pregunta'],
                    p['tipo'],
                    p['obligatoria'],
                    p['orden'],
                    p.get('min'),
                    p.get('max'),
                    opciones_str,
                    p.get('depende_de'),
                    p['activa']
                ))
            
            conn.commit()
            return preguntas
        else:
            cursor.execute("SELECT * FROM config_preguntas ORDER BY orden")
            preguntas = []
            
            for row in cursor.fetchall():
                pregunta = {
                    'id': row['id'],
                    'pregunta': row['pregunta'],
                    'tipo': row['tipo'],
                    'obligatoria': bool(row['obligatoria']),
                    'orden': row['orden'],
                    'depende_de': row['depende_de'],
                    'activa': bool(row.get('activa', True))
                }
                
                if row['tipo'] == 'numero':
                    pregunta['min'] = row['min_val'] if row['min_val'] is not None else 0
                    pregunta['max'] = row['max_val'] if row['max_val'] is not None else 100
                elif row['tipo'] == 'opcion' and row['opciones']:
                    pregunta['opciones'] = json.loads(row['opciones'])
                
                preguntas.append(pregunta)
            
            return preguntas
            
    except Error as err:
        hablar(f"Error al cargar preguntas: {err.msg}")
        return None
    finally:
        if conn.is_connected():
            conn.close()
            
def mostrar_preguntas(preguntas):
    print("\n" + "="*80)
    print("LISTA DE PREGUNTAS".center(80))
    print("="*80)
    print(f"{'#':<5} {'ID':<20} {'Pregunta':<30} {'Tipo':<15} {'Obligatoria':<10} {'Activa':<10} {'Depende de':<15} {'Opciones'}")
    print("-"*80)
    for i, p in enumerate(preguntas, 1):
        opciones = p.get('opciones', '')
        if opciones:
            opciones = ', '.join(opciones[:3]) + ('...' if len(opciones) > 3 else '')
        depende_de = p.get('depende_de', '') or ''
        print(f"{i:<5} {p['id']:<20} {p['pregunta']:<30} {p['tipo']:<15} {'Sí' if p['obligatoria'] else 'No':<10} {'Sí' if p.get('activa', True) else 'No':<10} {depende_de:<15} {opciones}")
    print("="*80)

def mostrar_preguntas_previo(preguntas):
    """Muestra las preguntas que se realizarán antes de iniciar el monitoreo"""
    print("\n" + "="*80)
    print("PREGUNTAS A REALIZAR".center(80))
    print("="*80)
    
    preguntas_activas = [p for p in preguntas if p.get('activa', True)]
    preguntas_activas.sort(key=lambda x: x.get('orden', 0))
    
    for i, pregunta in enumerate(preguntas_activas, 1):
        print(f"{i}. {pregunta['pregunta']}")
        if pregunta['tipo'] == 'opcion':
            print(f"   Opciones: {', '.join(f'{n+1}. {o}' for n, o in enumerate(pregunta['opciones']))}")
        elif pregunta['tipo'] == 'numero':
            print(f"   Rango: {pregunta.get('min', 0)} a {pregunta.get('max', 100)}")
    print("="*80)

def editar_pregunta(pregunta, preguntas):
    while True:
        print("\n" + "="*50)
        print("EDITAR PREGUNTA".center(50))
        print("="*50)
        print(f"1. Texto: {pregunta['pregunta']}")
        print(f"2. Tipo: {pregunta['tipo']}")
        print(f"3. Obligatoria: {'Sí' if pregunta['obligatoria'] else 'No'}")
        print(f"4. Activa: {'Sí' if pregunta.get('activa', True) else 'No'}")
        print(f"5. Orden: {pregunta.get('orden', len(preguntas)+1)}")
        print(f"6. Depende de: {pregunta.get('depende_de', 'Ninguna')}")
        if pregunta['tipo'] == 'numero':
            print(f"7. Rango: {pregunta.get('min', 0)}-{pregunta.get('max', 100)}")
        elif pregunta['tipo'] == 'opcion':
            print(f"7. Opciones: {', '.join(pregunta['opciones'])}")
        else:
            print("7. ---")
        print("8. Guardar cambios")
        print("9. Cancelar")
        print("="*50)
        
        opcion = input("Seleccione qué editar (1-9): ").strip()
        
        if opcion == "1":
            nuevo_texto = input("Nuevo texto: ").strip()
            if nuevo_texto:
                pregunta['pregunta'] = nuevo_texto
        elif opcion == "2":
            nuevo_tipo = input("Nuevo tipo (numero/opcion/texto): ").lower()
            if nuevo_tipo in ['numero', 'opcion', 'texto']:
                pregunta['tipo'] = nuevo_tipo
                if nuevo_tipo == 'opcion' and 'opciones' not in pregunta:
                    pregunta['opciones'] = ['Opción 1', 'Opción 2']
        elif opcion == "3":
            pregunta['obligatoria'] = not pregunta['obligatoria']
        elif opcion == "4":
            pregunta['activa'] = not pregunta.get('activa', True)
        elif opcion == "5":
            try:
                nuevo_orden = int(input("Nuevo orden: "))
                pregunta['orden'] = nuevo_orden
            except ValueError:
                print("Debe ser un número entero")
        elif opcion == "6":
            print("\nPreguntas disponibles para dependencia (solo preguntas de tipo opción):")
            preguntas_opcion = [p for p in preguntas if p['tipo'] == 'opcion' and p['id'] != pregunta['id']]
            for i, p in enumerate(preguntas_opcion, 1):
                print(f"{i}. {p['pregunta']} ({p['id']})")
            
            seleccion = input("\nNúmero de pregunta de la que depende (0 para ninguna): ").strip()
            if seleccion == "0":
                pregunta['depende_de'] = None
            else:
                try:
                    num = int(seleccion) - 1
                    if 0 <= num < len(preguntas_opcion):
                        pregunta['depende_de'] = preguntas_opcion[num]['id']
                except ValueError:
                    print("Número inválido")
        elif opcion == "7":
            if pregunta['tipo'] == 'numero':
                try:
                    min_val = int(input("Nuevo mínimo: "))
                    max_val = int(input("Nuevo máximo: "))
                    if min_val < max_val:
                        pregunta['min'] = min_val
                        pregunta['max'] = max_val
                except ValueError:
                    print("Deben ser números válidos")
            elif pregunta['tipo'] == 'opcion':
                print("\nOpciones actuales:")
                for i, op in enumerate(pregunta['opciones'], 1):
                    print(f"{i}. {op}")
                print("\na. Añadir opción")
                print("b. Eliminar opción")
                print("c. Editar opción")
                sub_op = input("Seleccione (a-c): ").lower()
                
                if sub_op == 'a':
                    nueva_op = input("Nueva opción: ").strip()
                    if nueva_op:
                        pregunta['opciones'].append(nueva_op)
                elif sub_op == 'b':
                    try:
                        num = int(input("Número de opción a eliminar: "))
                        if 1 <= num <= len(pregunta['opciones']):
                            pregunta['opciones'].pop(num-1)
                    except ValueError:
                        print("Número inválido")
                elif sub_op == 'c':
                    try:
                        num = int(input("Número de opción a editar: "))
                        if 1 <= num <= len(pregunta['opciones']):
                            nueva_op = input(f"Nuevo texto para '{pregunta['opciones'][num-1]}': ").strip()
                            if nueva_op:
                                pregunta['opciones'][num-1] = nueva_op
                    except ValueError:
                        print("Número inválido")
        elif opcion == "8":
            return pregunta
        elif opcion == "9":
            return None
        else:
            print("Opción no válida")

def agregar_pregunta(preguntas):
    """Agrega una nueva pregunta al sistema"""
    print("\n" + "="*50)
    print("AGREGAR NUEVA PREGUNTA".center(50))
    print("="*50)
    
    print("\nEl ID debe coincidir con el nombre de columna en la BD")
    print("Ejemplo: 'nueva_actividad' se convertirá en columna 'nueva_actividad'")
    pregunta_id = input("ID de la pregunta (sin espacios): ").strip().lower()
    
    if not pregunta_id or any(p['id'] == pregunta_id for p in preguntas):
        print("ID inválido o ya existe")
        return None
    
    pregunta = {
        'id': pregunta_id,
        'pregunta': pregunta_id.replace('_', ' ').title(),
        'tipo': 'texto',
        'obligatoria': False,
        'activa': True,
        'orden': len(preguntas) + 1,
        'depende_de': None
    }
    
    # Editar los campos básicos
    pregunta['pregunta'] = input(f"Texto de la pregunta [{pregunta['pregunta']}]: ").strip() or pregunta['pregunta']
    
    tipo = input("Tipo (numero/opcion/texto) [texto]: ").lower().strip()
    if tipo in ['numero', 'opcion']:
        pregunta['tipo'] = tipo
        
        if tipo == 'numero':
            try:
                pregunta['min'] = int(input("Valor mínimo [0]: ") or 0)
                pregunta['max'] = int(input("Valor máximo [100]: ") or 100)
            except ValueError:
                print("Usando valores por defecto")
        elif tipo == 'opcion':
            print("Ingrese opciones (una por línea, vacío para terminar):")
            opciones = []
            while True:
                op = input(f"Opción {len(opciones)+1}: ").strip()
                if not op:
                    if len(opciones) < 2:
                        print("Mínimo 2 opciones")
                        continue
                    break
                opciones.append(op)
            pregunta['opciones'] = opciones
    
    pregunta['obligatoria'] = input("¿Es obligatoria? (s/n) [n]: ").lower().strip() == 's'
    
    try:
        nuevo_orden = input(f"Orden (actualmente {pregunta['orden']}) [Enter para mantener]: ").strip()
        if nuevo_orden:
            pregunta['orden'] = int(nuevo_orden)
    except ValueError:
        print("Usando orden por defecto")
    
    # Configurar dependencia si es necesario
    if pregunta['tipo'] != 'opcion':
        print("\nPreguntas disponibles para dependencia (solo preguntas de tipo opción):")
        preguntas_opcion = [p for p in preguntas if p['tipo'] == 'opcion']
        for i, p in enumerate(preguntas_opcion, 1):
            print(f"{i}. {p['pregunta']} ({p['id']})")
        
        seleccion = input("\nNúmero de pregunta de la que depende (0 para ninguna): ").strip()
        if seleccion != "0":
            try:
                num = int(seleccion) - 1
                if 0 <= num < len(preguntas_opcion):
                    pregunta['depende_de'] = preguntas_opcion[num]['id']
            except ValueError:
                print("Número inválido")
    
    return pregunta

def eliminar_multiple_preguntas(preguntas):
    """Permite seleccionar y desactivar múltiples preguntas a la vez"""
    while True:
        mostrar_preguntas(preguntas)
        print("\nSeleccione las preguntas a desactivar (ej. 1,3,5 o 'todos' para todas)")
        print("Ingrese '0' para cancelar")
        
        seleccion = input("Números de preguntas a desactivar: ").strip().lower()
        
        if seleccion == '0':
            return False  # Cancelar
        elif seleccion == 'todos':
            confirmar = input("¿Está seguro de desactivar TODAS las preguntas? (s/n): ").lower()
            if confirmar == 's':
                for p in preguntas:
                    p['activa'] = False
                return True
            return False
        
        try:
            numeros = [int(n.strip()) for n in seleccion.split(',') if n.strip().isdigit()]
            numeros = list(set(numeros))  # Eliminar duplicados
            
            if not numeros:
                print("Selección inválida")
                continue
                
            print("\nPreguntas seleccionadas para desactivar:")
            for num in numeros:
                if 1 <= num <= len(preguntas):
                    print(f"{num}. {preguntas[num-1]['pregunta']}")
                else:
                    print(f"¡Número {num} fuera de rango!")
            
            confirmar = input("\n¿Confirmar desactivación? (s/n): ").lower()
            if confirmar != 's':
                continue
            
            for num in numeros:
                if 1 <= num <= len(preguntas):
                    preguntas[num-1]['activa'] = False
            
            print(f"\nSe desactivaron {len(numeros)} preguntas")
            return True
            
        except ValueError:
            print("Formato inválido. Use números separados por comas.")

def activar_multiple_preguntas(preguntas):
    """Permite seleccionar y activar múltiples preguntas a la vez"""
    while True:
        preguntas_inactivas = [p for p in preguntas if not p.get('activa', True)]
        if not preguntas_inactivas:
            print("No hay preguntas inactivas para activar")
            return False
            
        print("\nPreguntas inactivas:")
        for i, p in enumerate(preguntas_inactivas, 1):
            print(f"{i}. {p['pregunta']}")
        
        print("\nSeleccione las preguntas a activar (ej. 1,3,5 o 'todos' para todas)")
        print("Ingrese '0' para cancelar")
        
        seleccion = input("Números de preguntas a activar: ").strip().lower()
        
        if seleccion == '0':
            return False
        elif seleccion == 'todos':
            confirmar = input("¿Está seguro de activar TODAS las preguntas inactivas? (s/n): ").lower()
            if confirmar == 's':
                for p in preguntas_inactivas:
                    p['activa'] = True
                return True
            return False
        
        try:
            numeros = [int(n.strip()) for n in seleccion.split(',') if n.strip().isdigit()]
            numeros = list(set(numeros))
            
            if not numeros:
                print("Selección inválida")
                continue
                
            print("\nPreguntas seleccionadas para activar:")
            for num in numeros:
                if 1 <= num <= len(preguntas_inactivas):
                    print(f"{num}. {preguntas_inactivas[num-1]['pregunta']}")
                else:
                    print(f"¡Número {num} fuera de rango!")
            
            confirmar = input("\n¿Confirmar activación? (s/n): ").lower()
            if confirmar != 's':
                continue
            
            for num in numeros:
                if 1 <= num <= len(preguntas_inactivas):
                    preguntas_inactivas[num-1]['activa'] = True
            
            print(f"\nSe activaron {len(numeros)} preguntas")
            return True
            
        except ValueError:
            print("Formato inválido. Use números separados por comas.")

def aplicar_cambios_bd(preguntas):
    """Aplica los cambios de preguntas a la base de datos"""
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM config_preguntas")
        
        for p in preguntas:
            opciones_str = json.dumps(p['opciones']) if 'opciones' in p else None
            
            cursor.execute("""
            INSERT INTO config_preguntas 
            (id, pregunta, tipo, obligatoria, orden, min_val, max_val, opciones, depende_de, activa)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                p['id'],
                p['pregunta'],
                p['tipo'],
                p['obligatoria'],
                p['orden'],
                p.get('min'),
                p.get('max'),
                opciones_str,
                p.get('depende_de'),
                p.get('activa', True)
            ))
        
        conn.commit()
        return True
    except Error as err:
        print(f"Error al actualizar BD: {err}")
        conn.rollback()
        return False
    finally:
        if conn.is_connected():
            conn.close()

def reordenar_preguntas(preguntas):
    """Permite reorganizar el orden de las preguntas"""
    while True:
        mostrar_preguntas(preguntas)
        print("\nOpciones:")
        print("1. Mover pregunta arriba")
        print("2. Mover pregunta abajo")
        print("3. Establecer orden numérico")
        print("4. Mostrar orden actual")
        print("5. Finalizar reordenamiento")
        
        opcion = input("Seleccione una opción (1-5): ").strip()
        
        if opcion == "1":
            try:
                num = int(input("Número de pregunta a mover arriba: ")) - 1
                if 0 < num < len(preguntas):
                    preguntas[num]['orden'], preguntas[num-1]['orden'] = preguntas[num-1]['orden'], preguntas[num]['orden']
                    preguntas.sort(key=lambda x: x['orden'])
            except ValueError:
                print("Número inválido")
                
        elif opcion == "2":
            try:
                num = int(input("Número de pregunta a mover abajo: ")) - 1
                if 0 <= num < len(preguntas)-1:
                    preguntas[num]['orden'], preguntas[num+1]['orden'] = preguntas[num+1]['orden'], preguntas[num]['orden']
                    preguntas.sort(key=lambda x: x['orden'])
            except ValueError:
                print("Número inválido")
                
        elif opcion == "3":
            try:
                num = int(input("Número de pregunta a reordenar: ")) - 1
                nuevo_orden = int(input("Nuevo orden numérico: "))
                if 0 <= num < len(preguntas):
                    preguntas[num]['orden'] = nuevo_orden
                    preguntas.sort(key=lambda x: x['orden'])
            except ValueError:
                print("Entrada inválida")
                
        elif opcion == "4":
            print("\nOrden actual:")
            for i, p in enumerate(preguntas, 1):
                print(f"{i}. {p['pregunta']} (Orden: {p['orden']})")
                
        elif opcion == "5":
            return
        else:
            print("Opción no válida")

# ================= MONITOREO POR VOZ =================
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
            numero_opcion = palabras_a_numero(respuesta)
        
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
            hablar(f"Opción no reconocida. Por favor diga el número de la opción: {', '.join(opciones_numeradas)}")
            
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
                    hablar(f"El valor debe estar entre {min_val} y {max_val}")
        except ValueError:
            num = palabras_a_numero(respuesta)
            if num is not None and pregunta.get('min', 0) <= num <= pregunta.get('max', 100):
                respuestas[pregunta['id']] = num
                pregunta_respondida = True
            else:
                if intentos < 2:
                    hablar("No entendí el número. Por favor responda con un valor numérico.")
    else:  # Tipo texto
        respuestas[pregunta['id']] = respuesta
        pregunta_respondida = True
    
    return pregunta_respondida

def guardar_respuestas(respuestas):
    """Guarda las respuestas en la base de datos"""
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor()
        
        columns = ['numero_colmena', 'id_apiario']
        values = [respuestas['colmena'], respuestas['id_apiario']]
        
        cursor.execute("SHOW COLUMNS FROM colmenas")
        existing_columns = {row[0] for row in cursor.fetchall()}
        
        for key, value in respuestas.items():
            if key in existing_columns and key not in ['colmena', 'id_apiario']:
                columns.append(key)
                values.append(value)
        
        columns_str = ', '.join(columns)
        placeholders = ', '.join(['%s'] * len(values))
        
        query = f"INSERT INTO colmenas ({columns_str}) VALUES ({placeholders})"
        cursor.execute(query, values)
        conn.commit()
        return True
    except Error as err:
        print(f"Error al guardar respuestas: {err}")
        conn.rollback()
        return False
    finally:
        if conn.is_connected():
            conn.close()

def iniciar_monitoreo_voz():
    """Función principal para el monitoreo por voz"""
    hablar("Bienvenido al sistema de monitoreo de colmenas por voz")
    
    if not verificar_tablas_colmenas():
        hablar("Error en la base de datos. No se pueden verificar las tablas.")
        return
    
    preguntas = cargar_preguntas_desde_bd()
    if not preguntas:
        hablar("No se pudieron cargar las preguntas de configuración")
        return
    
    hablar("A continuación se mostrarán las preguntas que se realizarán durante el monitoreo.")
    mostrar_preguntas_previo(preguntas)
    hablar("¿Desea continuar con el monitoreo? Por favor diga 'confirmar' para continuar o 'cancelar' para salir.")
    
    respuesta = None
    while respuesta not in ['confirmar', 'cancelar']:
        respuesta = escuchar()
        if confirmacion_reconocida(respuesta, 'confirmar'):
            break
        elif respuesta and 'cancelar' in respuesta.lower():
            hablar("Monitoreo cancelado.")
            return
        else:
            hablar("No entendí su respuesta. Por favor diga 'confirmar' para continuar o 'cancelar' para salir.")
    
    # Seleccionar apiario
    hablar("Por favor indique el apiario a monitorear. Opciones: Norte, Centro o Sur")
    apiario = None
    apiarios_disponibles = obtener_apiarios()
    
    while apiario is None:
        respuesta = escuchar()
        if respuesta:
            for a in apiarios_disponibles:
                if fuzz.ratio(respuesta.lower(), a['nombre'].lower()) > 70:
                    apiario = a
                    break
            
            if apiario is None:
                hablar("Apiario no reconocido. Por favor diga Norte, Centro o Sur")
    
    hablar(f"Monitoreando apiario {apiario['nombre']}. A continuación indique el número de colmena.")
    
    # Seleccionar colmena
    colmenas_disponibles = obtener_colmenas_apiario(apiario['id'])
    if not colmenas_disponibles:
        hablar(f"No hay colmenas registradas en el apiario {apiario['nombre']}")
        return
    
    hablar(f"Colmenas disponibles en apiario {apiario['nombre']}: {', '.join(str(c['numero_colmena']) for c in colmenas_disponibles)}")
    colmena = None
    
    while colmena is None:
        respuesta = escuchar()
        if respuesta:
            try:
                num = int(respuesta)
                if any(c['numero_colmena'] == num for c in colmenas_disponibles):
                    colmena = num
                else:
                    hablar(f"El número {num} no corresponde a una colmena en este apiario")
            except ValueError:
                num = palabras_a_numero(respuesta)
                if num is not None and any(c['numero_colmena'] == num for c in colmenas_disponibles):
                    colmena = num
                else:
                    hablar("Número de colmena no reconocido. Por favor diga un número válido")
    
    hablar(f"Monitoreando colmena {colmena} en apiario {apiario['nombre']}. Empezaremos con las preguntas.")
    
    preguntas_activas = [p for p in preguntas if p.get('activa', True)]
    preguntas_activas.sort(key=lambda x: x.get('orden', 0))
    
    respuestas = {'colmena': colmena, 'id_apiario': apiario['id']}
    
    for pregunta in preguntas_activas:
        if pregunta.get('depende_de'):
            pregunta_dependencia = next((p for p in preguntas_activas if p['id'] == pregunta['depende_de']), None)
            if pregunta_dependencia and pregunta_dependencia['id'] in respuestas:
                valor_dependencia = respuestas[pregunta_dependencia['id']]
                if pregunta_dependencia['tipo'] == 'opcion' and valor_dependencia not in pregunta_dependencia.get('opciones', []):
                    continue
        
        intentos = 0
        pregunta_respondida = False
        
        while not pregunta_respondida and intentos < 2:
            intentos += 1
            
            texto_pregunta = pregunta['pregunta']
            if pregunta['tipo'] == 'opcion':
                opciones_numeradas = [f"{n+1}. {o}" for n, o in enumerate(pregunta['opciones'])]
                texto_pregunta += f". Opciones: {', '.join(opciones_numeradas)}. Responda con el número de la opción."
            elif pregunta['tipo'] == 'numero':
                texto_pregunta += f". Responda con un número entre {pregunta.get('min', 0)} y {pregunta.get('max', 100)}"
            
            hablar(texto_pregunta)
            
            respuesta = escuchar(duracion=5 if pregunta['tipo'] == 'texto' else 3)
            if not respuesta:
                if intentos < 2:
                    hablar("No capté su respuesta. Por favor repita.")
                continue
                
            pregunta_respondida = procesar_respuesta_pregunta(pregunta, respuesta, intentos, respuestas)
    
    hablar("Resumen de respuestas:")
    for key, value in respuestas.items():
        if key not in ['colmena', 'id_apiario']:
            pregunta = next((p for p in preguntas_activas if p['id'] == key), None)
            if pregunta:
                hablar(f"{pregunta['pregunta']}: {value}")
    
    hablar("¿Los datos son correctos? Por favor diga 'confirmar' para guardar o 'cancelar' para repetir el monitoreo.")
    confirmacion = None
    while confirmacion not in ['confirmar', 'cancelar']:
        confirmacion = escuchar()
        if confirmacion and 'confirmar' in confirmacion.lower():
            if guardar_respuestas(respuestas):
                hablar("Datos guardados correctamente. Monitoreo completado.")
            else:
                hablar("Hubo un error al guardar los datos. Por favor intente nuevamente.")
            break
        elif confirmacion and 'cancelar' in confirmacion.lower():
            hablar("Reiniciando el monitoreo para esta colmena.")
            iniciar_monitoreo_voz()
            break
        else:
            hablar("No entendí su respuesta. Por favor diga 'confirmar' para guardar o 'cancelar' para repetir.")

# ================= MENÚ DE CONFIGURACIÓN =================
def menu_configuracion():
    preguntas = cargar_preguntas_desde_bd()
    if not preguntas:
        hablar("No se pudieron cargar las preguntas desde la BD")
        return
    
    cambios_guardados = True
    
    while True:
        print("\n" + "="*50)
        print("CONFIGURACIÓN DE PREGUNTAS".center(50))
        print("="*50)
        print("1. Ver todas las preguntas")
        print("2. Editar pregunta existente")
        print("3. Agregar nueva pregunta")
        print("4. Desactivar pregunta(s)")
        print("5. Activar pregunta(s)")
        print("6. Reordenar preguntas")
        print("7. Guardar cambios en BD")
        print("8. Volver al menú principal")
        print("="*50)
        
        if not cambios_guardados:
            print("¡ATENCIÓN! Hay cambios no guardados".center(50))
        
        opcion = input("Selección (1-8): ").strip()
        
        if opcion == "1":
            mostrar_preguntas(preguntas)
        elif opcion == "2":
            mostrar_preguntas(preguntas)
            try:
                num = int(input("Número de pregunta a editar (0 para cancelar): "))
                if 1 <= num <= len(preguntas):
                    pregunta_editada = editar_pregunta(preguntas[num-1], preguntas)
                    if pregunta_editada:
                        preguntas[num-1] = pregunta_editada
                        print("Pregunta actualizada")
                        cambios_guardados = False
            except ValueError:
                print("Entrada inválida")
        elif opcion == "3":
            nueva_pregunta = agregar_pregunta(preguntas)
            if nueva_pregunta:
                preguntas.append(nueva_pregunta)
                print("Pregunta agregada")
                cambios_guardados = False
        elif opcion == "4":
            if eliminar_multiple_preguntas(preguntas):
                cambios_guardados = False
        elif opcion == "5":
            if activar_multiple_preguntas(preguntas):
                cambios_guardados = False
        elif opcion == "6":
            reordenar_preguntas(preguntas)
            cambios_guardados = False
        elif opcion == "7":
            if aplicar_cambios_bd(preguntas):
                print("✓ Cambios guardados en la base de datos")
                cambios_guardados = True
            else:
                print("✗ Error al guardar cambios")
        elif opcion == "8":
            if cambios_guardados:
                return
            confirmar = input("¿Salir sin guardar cambios? (s/n): ").lower()
            if confirmar == 's':
                return
        else:
            print("Opción no válida")

# ================= MENÚ DE GESTIÓN DE APIARIOS =================
def menu_gestion_apiarios():
    """Menú para gestionar apiarios y colmenas"""
    while True:
        print("\n" + "="*50)
        print("GESTIÓN DE APIARIOS Y COLMENAS".center(50))
        print("="*50)
        print("1. Listar apiarios y colmenas")
        print("2. Agregar apiario")
        print("3. Editar apiario")
        print("4. Agregar colmena a apiario")
        print("5. Volver al menú principal")
        print("="*50)
        
        opcion = input("Selección (1-5): ").strip()
        
        if opcion == "1":
            listar_apiarios_colmenas()
        elif opcion == "2":
            agregar_apiario()
        elif opcion == "3":
            editar_apiario()
        elif opcion == "4":
            agregar_colmena_a_apiario()
        elif opcion == "5":
            return
        else:
            print("Opción no válida")

def listar_apiarios_colmenas():
    """Muestra la lista de apiarios y sus colmenas"""
    apiarios = obtener_apiarios()
    if not apiarios:
        print("No hay apiarios registrados")
        return
    
    print("\n" + "="*80)
    print("LISTA DE APIARIOS Y COLMENAS".center(80))
    print("="*80)
    for apiario in apiarios:
        print(f"\nAPIARIO: {apiario['nombre']} - {apiario['ubicacion']}")
        colmenas = obtener_colmenas_apiario(apiario['id'])
        if colmenas:
            print(f"Colmenas: {', '.join(str(c['numero_colmena']) for c in colmenas)}")
        else:
            print("No tiene colmenas asignadas")
    print("="*80)

def agregar_apiario():
    """Agrega un nuevo apiario"""
    print("\n" + "="*50)
    print("AGREGAR NUEVO APIARIO".center(50))
    print("="*50)
    
    nombre = input("Nombre del apiario: ").strip()
    ubicacion = input("Ubicación: ").strip()
    
    if not nombre:
        print("El nombre es obligatorio")
        return
    
    conn = get_db_connection()
    if not conn:
        return
        
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO apiarios (nombre, ubicacion) VALUES (%s, %s)", (nombre, ubicacion))
        conn.commit()
        print(f"Apiario '{nombre}' agregado correctamente")
    except Error as err:
        print(f"Error al agregar apiario: {err}")
        conn.rollback()
    finally:
        if conn.is_connected():
            conn.close()

def editar_apiario():
    """Edita un apiario existente"""
    apiarios = obtener_apiarios()
    if not apiarios:
        print("No hay apiarios para editar")
        return
    
    print("\nApiarios disponibles:")
    for i, apiario in enumerate(apiarios, 1):
        print(f"{i}. {apiario['nombre']} - {apiario['ubicacion']}")
    
    try:
        seleccion = int(input("Seleccione apiario a editar (0 para cancelar): "))
        if seleccion == 0:
            return
        if 1 <= seleccion <= len(apiarios):
            apiario = apiarios[seleccion-1]
            
            nuevo_nombre = input(f"Nuevo nombre [{apiario['nombre']}]: ").strip() or apiario['nombre']
            nueva_ubicacion = input(f"Nueva ubicación [{apiario['ubicacion']}]: ").strip() or apiario['ubicacion']
            
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                    UPDATE apiarios 
                    SET nombre = %s, ubicacion = %s 
                    WHERE id = %s
                    """, (nuevo_nombre, nueva_ubicacion, apiario['id']))
                    conn.commit()
                    print("Apiario actualizado correctamente")
                except Error as err:
                    print(f"Error al actualizar apiario: {err}")
                    conn.rollback()
                finally:
                    if conn.is_connected():
                        conn.close()
    except ValueError:
        print("Selección inválida")

def agregar_colmena_a_apiario():
    """Agrega una nueva colmena a un apiario"""
    apiarios = obtener_apiarios()
    if not apiarios:
        print("No hay apiarios registrados")
        return
    
    print("\nApiarios disponibles:")
    for i, apiario in enumerate(apiarios, 1):
        print(f"{i}. {apiario['nombre']}")
    
    try:
        seleccion = int(input("Seleccione apiario (0 para cancelar): "))
        if seleccion == 0:
            return
        if 1 <= seleccion <= len(apiarios):
            apiario = apiarios[seleccion-1]
            
            while True:
                try:
                    numero_colmena = int(input("Número de la nueva colmena: "))
                    
                    conn = get_db_connection()
                    if conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                        SELECT COUNT(*) FROM colmenas 
                        WHERE id_apiario = %s AND numero_colmena = %s
                        """, (apiario['id'], numero_colmena))
                        existe = cursor.fetchone()[0]
                        
                        if existe:
                            print(f"Ya existe una colmena con el número {numero_colmena} en este apiario")
                            continue
                            
                        if crear_colmena(numero_colmena, apiario['id']):
                            print(f"Colmena {numero_colmena} agregada correctamente al apiario {apiario['nombre']}")
                            break
                except ValueError:
                    print("Debe ingresar un número entero")
                finally:
                    if conn and conn.is_connected():
                        conn.close()
    except ValueError:
        print("Selección inválida")

# ================= FUNCIÓN PRINCIPAL =================
def main():
    while True:
        print("\n" + "="*50)
        print("SISTEMA DE MONITOREO DE COLMENAS".center(50))
        print("="*50)
        print("1. Iniciar monitoreo por voz")
        print("2. Configurar preguntas")
        print("3. Gestionar apiarios")
        print("4. Salir")
        print("="*50)
        
        opcion = input("Seleccione una opción (1-4): ").strip()
        
        if opcion == "1":
            iniciar_monitoreo_voz()
        elif opcion == "2":
            menu_configuracion()
        elif opcion == "3":
            menu_gestion_apiarios()
        elif opcion == "4":
            hablar("Saliendo del sistema. ¡Hasta pronto!")
            break
        else:
            print("Opción no válida")

if __name__ == "__main__":
    main()