# modelo.py
import os
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv
import re
import json
from mysql.connector import Error, pooling
from pathlib import Path
import logging

# Configuración inicial
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='app.log'
)

class DatabaseModel:
    # Configuración del pool de conexiones
    _connection_pool = None
    
    @classmethod
    def initialize_pool(cls):
        """Inicializa el pool de conexiones a la base de datos"""
        try:
            cls._connection_pool = pooling.MySQLConnectionPool(
                pool_name="beehive_pool",
                pool_size=5,
                host=os.getenv('DB_HOST'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASS'),
                database=os.getenv('DB_NAME')
            )
            logging.info("Pool de conexiones inicializado correctamente")
        except Error as err:
            logging.error(f"Error al inicializar el pool de conexiones: {err}")

    @classmethod
    def get_db_connection(cls):
        """Obtiene una conexión del pool"""
        if cls._connection_pool is None:
            cls.initialize_pool()
        
        try:
            conn = cls._connection_pool.get_connection()
            return conn
        except Error as err:
            logging.error(f"Error al obtener conexión del pool: {err}")
            return None

    @staticmethod
    def verificar_tablas_colmenas():
        """Verifica y crea las tablas necesarias si no existen"""
        conn = DatabaseModel.get_db_connection()
        if not conn:
            logging.error("No se pudo establecer conexión para verificar tablas")
            return False
            
        try:
            cursor = conn.cursor()
            
            # Crear tabla apiarios si no existe
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS apiarios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nombre VARCHAR(50) NOT NULL,
                ubicacion VARCHAR(100),
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_nombre (nombre)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            
            # Insertar datos iniciales si no existen
            cursor.execute("SELECT COUNT(*) FROM apiarios")
            if cursor.fetchone()[0] == 0:
                cursor.executemany("""
                INSERT INTO apiarios (nombre, ubicacion) VALUES (%s, %s)
                """, [
                    ('Norte', 'Zona norte de la finca'),
                    ('Centro', 'Zona central de la finca'),
                    ('Sur', 'Zona sur de la finca')
                ])
            
            # Crear tabla colmenas con estructura mejorada
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS colmenas (
                id INT AUTO_INCREMENT PRIMARY KEY,
                numero_colmena INT NOT NULL,
                id_apiario INT NOT NULL,
                
                actividad_piqueras ENUM('Baja', 'Media', 'Alta') DEFAULT NULL,
                poblacion_abejas ENUM('Baja', 'Media', 'Alta') DEFAULT NULL,
                cuadros_alimento INT DEFAULT NULL,
                cuadros_cria INT DEFAULT NULL,
                
                estado_colmena ENUM(
                    'Cámara de cría',
                    'Cámara de cría y producción',
                    'Cámara de cría y doble alza de producción'
                ) DEFAULT NULL,
                
                estado_sanitario ENUM(
                    'Presencia barroa',
                    'Presencia de polilla',
                    'Presencia de curruncho',
                    'Mortalidad- malformación en nodrizas',
                    'Ninguno'
                ) DEFAULT NULL,
                
                limpieza_arveneses ENUM('Si', 'No') DEFAULT NULL,
                estado_postura ENUM('Huevo', 'Larva y pupa', 'Mortalidad', 'Zanganeras') DEFAULT NULL,
                distribucion_postura ENUM('No hay postura', 'dispersa', 'uniforme') DEFAULT NULL,
                
                almacenamiento_alimento ENUM(
                    'Existe pan de abeja',
                    'Almacenamiento de néctar',
                    'Bajo almacenamiento'
                ) DEFAULT NULL,
                
                tiene_camara_produccion ENUM('Si', 'No') DEFAULT NULL,
                tipo_camara_produccion ENUM('Media alza', 'Alza profunda', 'No aplica') DEFAULT NULL,
                
                numero_cuadros_produccion INT DEFAULT NULL,
                cuadros_estampados INT DEFAULT NULL,
                cuadros_estirados INT DEFAULT NULL,
                cuadros_llenado INT DEFAULT NULL,
                cuadros_operculados INT DEFAULT NULL,
                porcentaje_operculo VARCHAR(20) DEFAULT NULL,
                cuadros_cosecha INT DEFAULT NULL,
                kilos_cosecha DECIMAL(5,2) DEFAULT NULL,
                
                observaciones TEXT DEFAULT NULL,
                fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (id_apiario) REFERENCES apiarios(id),
                UNIQUE KEY unique_colmena_apiario (numero_colmena, id_apiario)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            
            # Tabla de configuración de preguntas
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS config_preguntas (
                id VARCHAR(50) PRIMARY KEY,
                pregunta TEXT NOT NULL,
                tipo ENUM('numero', 'opcion', 'texto') NOT NULL,
                obligatoria BOOLEAN DEFAULT FALSE,
                orden INT NOT NULL,
                min_val INT DEFAULT NULL,
                max_val INT DEFAULT NULL,
                opciones JSON DEFAULT NULL,
                depende_de VARCHAR(50) DEFAULT NULL,
                activa BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (depende_de) REFERENCES config_preguntas(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            
            conn.commit()
            logging.info("Tablas verificadas/creadas correctamente")
            return True
        except Error as err:
            conn.rollback()
            logging.error(f"Error al verificar tablas: {err}")
            return False
        finally:
            if conn.is_connected():
                conn.close()

    @staticmethod
    def obtener_apiarios(activos=True):
        """Obtiene la lista de apiarios disponibles"""
        conn = DatabaseModel.get_db_connection()
        if not conn:
            logging.error("No se pudo establecer conexión para obtener apiarios")
            return None
            
        try:
            cursor = conn.cursor(dictionary=True)
            query = "SELECT id, nombre, ubicacion FROM apiarios"
            cursor.execute(query)
            return cursor.fetchall()
        except Error as err:
            logging.error(f"Error al obtener apiarios: {err}")
            return None
        finally:
            if conn.is_connected():
                conn.close()

    @staticmethod
    def obtener_colmenas_apiario(id_apiario):
        """Obtiene las colmenas de un apiario específico con información básica"""
        conn = DatabaseModel.get_db_connection()
        if not conn:
            logging.error("No se pudo establecer conexión para obtener colmenas")
            return None
            
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
            SELECT c.id, c.numero_colmena, a.nombre as nombre_apiario
            FROM colmenas c
            JOIN apiarios a ON c.id_apiario = a.id
            WHERE c.id_apiario = %s
            ORDER BY c.numero_colmena
            """, (id_apiario,))
            return cursor.fetchall()
        except Error as err:
            logging.error(f"Error al obtener colmenas: {err}")
            return None
        finally:
            if conn.is_connected():
                conn.close()

    @staticmethod
    def crear_colmena(numero_colmena, id_apiario):
        """Crea una nueva colmena en el apiario especificado"""
        conn = DatabaseModel.get_db_connection()
        if not conn:
            logging.error("No se pudo establecer conexión para crear colmena")
            return False
            
        try:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO colmenas (numero_colmena, id_apiario)
            VALUES (%s, %s)
            """, (numero_colmena, id_apiario))
            conn.commit()
            logging.info(f"Colmena {numero_colmena} creada en apiario {id_apiario}")
            return True
        except Error as err:
            conn.rollback()
            logging.error(f"Error al crear colmena: {err}")
            return False
        finally:
            if conn.is_connected():
                conn.close()

    @staticmethod
    def cargar_preguntas_desde_bd(activas=True):
        """Carga la estructura de preguntas desde la base de datos"""
        conn = DatabaseModel.get_db_connection()
        if not conn:
            logging.error("No se pudo establecer conexión para cargar preguntas")
            return None
            
        try:
            cursor = conn.cursor(dictionary=True)
            
            query = """
            SELECT * FROM config_preguntas 
            WHERE activa = %s OR %s = FALSE
            ORDER BY orden
            """
            cursor.execute(query, (activas, activas))
            
            preguntas = []
            for row in cursor.fetchall():
                pregunta = {
                    'id': row['id'],
                    'pregunta': row['pregunta'],
                    'tipo': row['tipo'],
                    'obligatoria': bool(row['obligatoria']),
                    'orden': row['orden'],
                    'depende_de': row['depende_de'],
                    'activa': bool(row['activa'])
                }
                
                if row['tipo'] == 'numero':
                    pregunta['min'] = row['min_val'] if row['min_val'] is not None else 0
                    pregunta['max'] = row['max_val'] if row['max_val'] is not None else 100
                elif row['tipo'] == 'opcion' and row['opciones']:
                    pregunta['opciones'] = json.loads(row['opciones'])
                
                preguntas.append(pregunta)
            
            logging.info(f"Cargadas {len(preguntas)} preguntas desde la BD")
            return preguntas
        except Error as err:
            logging.error(f"Error al cargar preguntas: {err}")
            return None
        finally:
            if conn.is_connected():
                conn.close()

    @staticmethod
    def aplicar_cambios_preguntas(preguntas):
        """Aplica los cambios de preguntas a la base de datos en una transacción"""
        conn = DatabaseModel.get_db_connection()
        if not conn:
            logging.error("No se pudo establecer conexión para actualizar preguntas")
            return False
            
        try:
            cursor = conn.cursor()
            
            # Iniciar transacción
            conn.start_transaction()
            
            # Eliminar todas las preguntas existentes
            cursor.execute("DELETE FROM config_preguntas")
            
            # Insertar las nuevas preguntas
            for p in preguntas:
                opciones_str = json.dumps(p.get('opciones')) if 'opciones' in p else None
                
                cursor.execute("""
                INSERT INTO config_preguntas 
                (id, pregunta, tipo, obligatoria, orden, min_val, max_val, opciones, depende_de, activa)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    p['id'],
                    p['pregunta'],
                    p['tipo'],
                    p.get('obligatoria', False),
                    p.get('orden', 0),
                    p.get('min'),
                    p.get('max'),
                    opciones_str,
                    p.get('depende_de'),
                    p.get('activa', True)
                ))
            
            conn.commit()
            logging.info(f"Actualizadas {len(preguntas)} preguntas en la BD")
            return True
        except Error as err:
            conn.rollback()
            logging.error(f"Error al actualizar preguntas: {err}")
            return False
        finally:
            if conn.is_connected():
                conn.close()

    @staticmethod
    def guardar_respuestas(respuestas):
        """Guarda las respuestas del monitoreo en la base de datos"""
        conn = DatabaseModel.get_db_connection()
        if not conn:
            logging.error("No se pudo establecer conexión para guardar respuestas")
            return False
            
        try:
            cursor = conn.cursor()
            
            # Obtener columnas válidas de la tabla
            cursor.execute("SHOW COLUMNS FROM colmenas")
            existing_columns = {row[0] for row in cursor.fetchall()}
            
            # Preparar datos para inserción
            columns = ['numero_colmena', 'id_apiario']
            values = [respuestas['colmena'], respuestas['id_apiario']]
            
            # Filtrar y validar campos adicionales
            for key, value in respuestas.items():
                if key in existing_columns and key not in ['colmena', 'id_apiario'] and value is not None:
                    columns.append(key)
                    values.append(value)
            
            # Construir y ejecutar consulta
            columns_str = ', '.join(columns)
            placeholders = ', '.join(['%s'] * len(values))
            query = f"INSERT INTO colmenas ({columns_str}) VALUES ({placeholders})"
            
            cursor.execute(query, values)
            conn.commit()
            logging.info(f"Monitoreo guardado para colmena {respuestas['colmena']}")
            return True
        except Error as err:
            conn.rollback()
            logging.error(f"Error al guardar respuestas: {err}")
            return False
        finally:
            if conn.is_connected():
                conn.close()

    @staticmethod
    def agregar_apiario(nombre, ubicacion=None):
        """Agrega un nuevo apiario a la base de datos"""
        conn = DatabaseModel.get_db_connection()
        if not conn:
            logging.error("No se pudo establecer conexión para agregar apiario")
            return False
            
        try:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO apiarios (nombre, ubicacion) VALUES (%s, %s)",
                (nombre, ubicacion)
            )
            conn.commit()
            logging.info(f"Apiario '{nombre}' agregado correctamente")
            return True
        except Error as err:
            conn.rollback()
            logging.error(f"Error al agregar apiario '{nombre}': {err}")
            return False
        finally:
            if conn.is_connected():
                conn.close()

    @staticmethod
    def actualizar_apiario(apiario_id, nombre=None, ubicacion=None):
        """Actualiza un apiario existente"""
        conn = DatabaseModel.get_db_connection()
        if not conn:
            logging.error("No se pudo establecer conexión para actualizar apiario")
            return False
            
        try:
            cursor = conn.cursor()
            
            updates = []
            params = []
            
            if nombre is not None:
                updates.append("nombre = %s")
                params.append(nombre)
            if ubicacion is not None:
                updates.append("ubicacion = %s")
                params.append(ubicacion)
            
            if not updates:
                logging.warning("Nada que actualizar para el apiario")
                return False
                
            params.append(apiario_id)
            query = f"UPDATE apiarios SET {', '.join(updates)} WHERE id = %s"
            
            cursor.execute(query, params)
            conn.commit()
            logging.info(f"Apiario {apiario_id} actualizado correctamente")
            return True
        except Error as err:
            conn.rollback()
            logging.error(f"Error al actualizar apiario {apiario_id}: {err}")
            return False
        finally:
            if conn.is_connected():
                conn.close()

# Inicializar el pool de conexiones al importar el módulo
DatabaseModel.initialize_pool()