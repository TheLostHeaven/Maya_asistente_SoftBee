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
import winsound
import tempfile
import warnings
import scipy.io.wavfile as wav
from mysql.connector import Error
import json

# Configuración inicial
load_dotenv()
engine = pyttsx3.init()
engine.setProperty('rate', 160)
engine.setProperty('voice', 'spanish')
warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")

# ================= CONFIGURACIÓN WHISPER =================
WHISPER_MODEL = "base"
model = whisper.load_model(WHISPER_MODEL)

# ================= FUNCIONES DE AUDIO =================
def hablar(texto):
    print(f"ASISTENTE: {texto}")
    engine.say(texto)
    engine.runAndWait()

def escuchar(duracion=5):
    try:
        samplerate = 16000
        print("\n[ESCUCHANDO...]")
        audio = sd.rec(int(duracion * samplerate), samplerate=samplerate, channels=1, dtype='float32')
        sd.wait()
        audio_np = audio.flatten()
        audio_np = audio_np / np.max(np.abs(audio_np))
        result = model.transcribe(audio_np.astype(np.float32), language="es")
        texto = result["text"].strip()
        if texto:
            print(f"USUARIO: {texto}")
            return texto.lower()
        return None
    except Exception as e:
        hablar(f"Error al escuchar: {str(e)}")
        return None

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
    """Verifica que existan las tablas para todas las colmenas (1-10)"""
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor()
        
        for i in range(1, 11):
            table_name = f"colmena_{i}"
            cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INT AUTO_INCREMENT PRIMARY KEY,
                fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
                numero_colmena INT NOT NULL
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
            
def get_column_info(table_name):
    """Obtiene información de las columnas de una tabla"""
    conn = get_db_connection()
    if not conn:
        return None
        
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SHOW COLUMNS FROM {table_name}")
        columns = cursor.fetchall()
        
        # Mapear tipos ENUM a opciones
        for col in columns:
            if col['Type'].startswith('enum'):
                col['Options'] = re.findall(r"'(.*?)'", col['Type'])
        return columns
    except Error as err:
        hablar(f"Error al obtener columnas: {err.msg}")
        return None
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
        
        # 1. Verificar si existe la tabla config_preguntas y tiene las columnas necesarias
        cursor.execute("""
        SELECT COUNT(*) as existe 
        FROM information_schema.tables 
        WHERE table_schema = DATABASE() AND table_name = 'config_preguntas'
        """)
        existe_tabla = cursor.fetchone()['existe']
        
        if existe_tabla:
            # Verificar si la tabla tiene las columnas necesarias
            cursor.execute("""
            SELECT COLUMN_NAME 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'config_preguntas'
            """)
            columnas = {row['COLUMN_NAME'] for row in cursor.fetchall()}
            
            columnas_requeridas = {'id', 'pregunta', 'tipo', 'obligatoria', 'orden', 'depende_de', 'activa'}
            if not columnas_requeridas.issubset(columnas):
                # La tabla existe pero no tiene la estructura correcta
                hablar("La tabla de configuración existe pero no tiene la estructura correcta. Recreándola...")
                cursor.execute("DROP TABLE IF EXISTS config_preguntas")
                conn.commit()
                existe_tabla = False
        
        if not existe_tabla:
            # 2. Cargar estructura básica desde la primera colmena (para migración)
            cursor.execute("SHOW COLUMNS FROM colmena_1")
            columns = cursor.fetchall()
            
            preguntas = []
            for col in columns:
                if col['Field'] in ['id', 'fecha_registro']:
                    continue
                    
                pregunta = {
                    'id': col['Field'],
                    'pregunta': col['Field'].replace('_', ' ').title(),
                    'tipo': 'texto',
                    'obligatoria': col['Null'] == 'NO',
                    'orden': len(preguntas) + 1,
                    'depende_de': None,
                    'activa': True  # Todas las preguntas activas por defecto
                }
                
                if 'int' in col['Type'] or 'decimal' in col['Type']:
                    pregunta['tipo'] = 'numero'
                    pregunta['min'] = 0
                    pregunta['max'] = 20 if 'cuadros' in col['Field'] else 100
                elif col['Type'].startswith('enum'):
                    pregunta['tipo'] = 'opcion'
                    pregunta['opciones'] = re.findall(r"'(.*?)'", col['Type'])
                
                preguntas.append(pregunta)
            
            # 3. Crear la tabla config_preguntas con la estructura correcta
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
            
            # 4. Insertar los datos iniciales
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
            # 5. Cargar desde configuración existente
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
                    'activa': bool(row.get('activa', True))  # Por defecto True si no existe
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
        # Convertir None a cadena vacía antes de formatear
        depende_de = p.get('depende_de', '') or ''
        print(f"{i:<5} {p['id']:<20} {p['pregunta']:<30} {p['tipo']:<15} {'Sí' if p['obligatoria'] else 'No':<10} {'Sí' if p.get('activa', True) else 'No':<10} {depende_de:<15} {opciones}")
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
    print("\n" + "="*50)
    print("AGREGAR NUEVA PREGUNTA".center(50))
    print("="*50)
    
    # ID de la pregunta (debe coincidir con nombre de columna)
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
            # Procesar selección múltiple
            numeros = [int(n.strip()) for n in seleccion.split(',') if n.strip().isdigit()]
            numeros = list(set(numeros))  # Eliminar duplicados
            
            if not numeros:
                print("Selección inválida")
                continue
                
            # Mostrar preguntas seleccionadas
            print("\nPreguntas seleccionadas para desactivar:")
            for num in numeros:
                if 1 <= num <= len(preguntas):
                    print(f"{num}. {preguntas[num-1]['pregunta']}")
                else:
                    print(f"¡Número {num} fuera de rango!")
            
            confirmar = input("\n¿Confirmar desactivación? (s/n): ").lower()
            if confirmar != 's':
                continue
            
            # Desactivar preguntas seleccionadas
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
        # Mostrar solo preguntas inactivas
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
            return False  # Cancelar
        elif seleccion == 'todos':
            confirmar = input("¿Está seguro de activar TODAS las preguntas inactivas? (s/n): ").lower()
            if confirmar == 's':
                for p in preguntas_inactivas:
                    p['activa'] = True
                return True
            return False
        
        try:
            # Procesar selección múltiple
            numeros = [int(n.strip()) for n in seleccion.split(',') if n.strip().isdigit()]
            numeros = list(set(numeros))  # Eliminar duplicados
            
            if not numeros:
                print("Selección inválida")
                continue
                
            # Mostrar preguntas seleccionadas
            print("\nPreguntas seleccionadas para activar:")
            for num in numeros:
                if 1 <= num <= len(preguntas_inactivas):
                    print(f"{num}. {preguntas_inactivas[num-1]['pregunta']}")
                else:
                    print(f"¡Número {num} fuera de rango!")
            
            confirmar = input("\n¿Confirmar activación? (s/n): ").lower()
            if confirmar != 's':
                continue
            
            # Activar preguntas seleccionadas
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
        
        # 1. Crear tabla de configuración si no existe
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
        
        # 2. Limpiar configuración previa
        cursor.execute("DELETE FROM config_preguntas")
        
        # 3. Guardar la nueva configuración
        for p in preguntas:
            # Serializar opciones si es una pregunta de opción múltiple
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
                print(f"{i}. {p['pregunta']} (Orden: {p['orden']}")
                
        elif opcion == "5":
            return
        else:
            print("Opción no válida")

def palabras_a_numero(texto):
    """Convierte palabras de números en español a valores numéricos"""
    numeros = {
        'cero': 0, 'uno': 1, 'un': 1, 'una': 1,
        'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5,
        'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9,
        'diez': 10, 'once': 11, 'doce': 12, 'trece': 13,
        'catorce': 14, 'quince': 15, 'dieciseis': 16, 'dieciséis': 16,
        'diecisiete': 17, 'dieciocho': 18, 'diecinueve': 19,
        'veinte': 20, 'veintiuno': 21, 'veintidós': 22, 'veintitrés': 23,
        'veinticuatro': 24, 'veinticinco': 25, 'veintiséis': 26,
        'veintisiete': 27, 'veintiocho': 28, 'veintinueve': 29,
        'treinta': 30, 'cuarenta': 40, 'cincuenta': 50,
        'sesenta': 60, 'setenta': 70, 'ochenta': 80,
        'noventa': 90, 'cien': 100
    }
    
    # Manejar combinaciones como "cuarenta y cinco"
    if ' y ' in texto:
        partes = texto.split(' y ')
        if len(partes) == 2:
            num1 = numeros.get(partes[0].lower(), 0)
            num2 = numeros.get(partes[1].lower(), 0)
            return num1 + num2
    
    return numeros.get(texto.lower(), None)            

# ================= MONITOREO POR VOZ =================
def guardar_respuestas(colmena, respuestas):
    """Guarda las respuestas en la base de datos"""
    conn = get_db_connection()
    if not conn:
        return False
        
    try:
        cursor = conn.cursor()
        
        # Preparar consulta SQL
        table_name = f"colmena_{colmena}"
        columns = ['fecha_registro', 'numero_colmena']  # Añadimos numero_colmena
        values = [datetime.now().strftime('%Y-%m-%d %H:%M:%S'), colmena]  # Añadimos el número
        
        # Verificar y agregar columnas que no existen
        cursor.execute(f"SHOW COLUMNS FROM {table_name}")
        existing_columns = {row[0] for row in cursor.fetchall()}
        
        # Asegurarnos que numero_colmena exista en la tabla
        if 'numero_colmena' not in existing_columns:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN numero_colmena INT")
            conn.commit()
            existing_columns.add('numero_colmena')
        
        for key, value in respuestas.items():
            if key != 'colmena':  # No necesitamos guardar el número de colmena como campo adicional
                if key not in existing_columns:
                    try:
                        col_type = "VARCHAR(255)"
                        if isinstance(value, int):
                            col_type = "INT"
                        elif isinstance(value, float):
                            col_type = "DECIMAL(10,2)"
                            
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {key} {col_type}")
                        conn.commit()
                        existing_columns.add(key)
                        print(f"Se agregó la columna {key} a la tabla {table_name}")
                    except Error as err:
                        print(f"No se pudo agregar columna {key}: {err}")
                        continue
                
                columns.append(key)
                values.append(value)
        
        columns_str = ', '.join(columns)
        placeholders = ', '.join(['%s'] * len(values))
        
        query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
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
    
    # Verificar que existan las tablas
    if not verificar_tablas_colmenas():
        hablar("Error en la base de datos. No se pueden verificar las tablas.")
        return
    
    # Cargar preguntas configuradas
    preguntas = cargar_preguntas_desde_bd()
    if not preguntas:
        hablar("No se pudieron cargar las preguntas de configuración")
        return
    
    hablar("Por favor indique el número de colmena a monitorear (del 1 al 10)")
    colmena = None
    
    while colmena is None:
        respuesta = escuchar()
        if respuesta:
            try:
                num = int(respuesta)
                if 1 <= num <= 10:
                    colmena = num
                else:
                    hablar("Por favor indique un número entre 1 y 10")
            except ValueError:
                # Intentar convertir palabras a números
                num = palabras_a_numero(respuesta)
                if num is not None and 1 <= num <= 10:
                    colmena = num
                else:
                    hablar("No entendí el número de colmena. Por favor dígalo nuevamente.")
    
    hablar(f"Monitoreando colmena {colmena}. Empezaremos con las preguntas.")
    
    # Filtrar preguntas activas y ordenarlas
    preguntas_activas = [p for p in preguntas if p.get('activa', True)]
    preguntas_activas.sort(key=lambda x: x.get('orden', 0))
    
    respuestas = {'colmena': colmena}
    
    for pregunta in preguntas_activas:
        # Verificar dependencias
        if pregunta.get('depende_de'):
            pregunta_dependencia = next((p for p in preguntas_activas if p['id'] == pregunta['depende_de']), None)
            if pregunta_dependencia and pregunta_dependencia['id'] in respuestas:
                valor_dependencia = respuestas[pregunta_dependencia['id']]
                if pregunta_dependencia['tipo'] == 'opcion' and valor_dependencia not in pregunta_dependencia.get('opciones', []):
                    continue  # Saltar esta pregunta si no cumple la dependencia
        
        pregunta_respondida = False
        
        while not pregunta_respondida:
            hablar(pregunta['pregunta'])
            
            if pregunta['tipo'] == 'opcion':
                hablar(f"Opciones disponibles: {', '.join(pregunta['opciones'])}")
            elif pregunta['tipo'] == 'numero':
                hablar(f"Por favor responda con un número entre {pregunta.get('min', 0)} y {pregunta.get('max', 100)}")
            
            respuesta = escuchar()
            if not respuesta:
                hablar("No capté su respuesta. Por favor repita.")
                continue
                
            if pregunta['tipo'] == 'opcion':
                respuesta = respuesta.lower()
                opciones = [o.lower() for o in pregunta['opciones']]
                
                for i, op in enumerate(opciones):
                    if op in respuesta:
                        respuestas[pregunta['id']] = pregunta['opciones'][i]
                        pregunta_respondida = True
                        break
                
                if not pregunta_respondida:
                    hablar(f"Opción no válida. Las opciones son: {', '.join(pregunta['opciones'])}")
                    
            elif pregunta['tipo'] == 'numero':
                try:
                    num = int(respuesta)
                    min_val = pregunta.get('min', 0)
                    max_val = pregunta.get('max', 100)
                    if min_val <= num <= max_val:
                        respuestas[pregunta['id']] = num
                        pregunta_respondida = True
                    else:
                        hablar(f"El valor debe estar entre {min_val} y {max_val}")
                except ValueError:
                    # Intentar convertir palabras a números
                    num = palabras_a_numero(respuesta)
                    if num is not None and pregunta.get('min', 0) <= num <= pregunta.get('max', 100):
                        respuestas[pregunta['id']] = num
                        pregunta_respondida = True
                    else:
                        hablar("No entendí el número. Por favor responda con un valor numérico.")
            else:  # Tipo texto
                respuestas[pregunta['id']] = respuesta
                pregunta_respondida = True
    
    # Guardar respuestas
    if guardar_respuestas(colmena, respuestas):
        hablar("Datos guardados correctamente. Monitoreo completado.")
    else:
        hablar("Hubo un error al guardar los datos. Por favor intente nuevamente.")

# ================= MENÚ DE CONFIGURACIÓN =================
def menu_configuracion():
    preguntas = cargar_preguntas_desde_bd()
    if not preguntas:
        hablar("No se pudieron cargar las preguntas desde la BD")
        return
    
    cambios_guardados = True  # Trackear si hay cambios no guardados
    
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
        
        # Mostrar advertencia si hay cambios no guardados
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
                return  # Volver sin confirmación si ya está todo guardado
            confirmar = input("¿Salir sin guardar cambios? (s/n): ").lower()
            if confirmar == 's':
                return
        else:
            print("Opción no válida")

# ================= FUNCIÓN PRINCIPAL =================
def main():
    while True:
        print("\n" + "="*50)
        print("SISTEMA DE MONITOREO DE COLMENAS".center(50))
        print("="*50)
        print("1. Iniciar monitoreo por voz")
        print("2. Configurar preguntas")
        print("3. Salir")
        print("="*50)
        
        opcion = input("Seleccione una opción (1-3): ").strip()
        
        if opcion == "1":
            iniciar_monitoreo_voz()
        elif opcion == "2":
            menu_configuracion()
        elif opcion == "3":
            hablar("Saliendo del sistema. ¡Hasta pronto!")
            break
        else:
            print("Opción no válida")

if __name__ == "__main__":
    main()