"""
Módulo para manejo seguro de credenciales MT5
"""
import os
import json
import logging
from cryptography.fernet import Fernet
from pathlib import Path

logger = logging.getLogger(__name__)

# Archivo para almacenar credenciales encriptadas
CREDENTIALS_FILE = "mt5_credentials.enc"
KEY_FILE = "mt5_key.key"

def _get_or_create_key():
    """Obtiene o crea una clave de encriptación"""
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, 'rb') as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, 'wb') as f:
            f.write(key)
        return key

def save_credentials(login, password, server):
    """Guarda las credenciales de MT5 de forma encriptada"""
    try:
        key = _get_or_create_key()
        fernet = Fernet(key)
        
        credentials = {
            'login': login,
            'password': password,
            'server': server
        }
        
        # Encriptar credenciales
        encrypted_data = fernet.encrypt(json.dumps(credentials).encode())
        
        # Guardar en archivo
        with open(CREDENTIALS_FILE, 'wb') as f:
            f.write(encrypted_data)
            
        logger.info("Credenciales MT5 guardadas exitosamente")
        return True
        
    except Exception as e:
        logger.error(f"Error guardando credenciales: {e}")
        return False

def load_credentials():
    """Carga las credenciales de MT5 desde archivo encriptado"""
    try:
        if not os.path.exists(CREDENTIALS_FILE) or not os.path.exists(KEY_FILE):
            return None
            
        key = _get_or_create_key()
        fernet = Fernet(key)
        
        # Leer archivo encriptado
        with open(CREDENTIALS_FILE, 'rb') as f:
            encrypted_data = f.read()
            
        # Desencriptar
        decrypted_data = fernet.decrypt(encrypted_data)
        credentials = json.loads(decrypted_data.decode())
        
        return credentials
        
    except Exception as e:
        logger.error(f"Error cargando credenciales: {e}")
        return None

def clear_credentials():
    """Elimina las credenciales almacenadas"""
    try:
        if os.path.exists(CREDENTIALS_FILE):
            os.remove(CREDENTIALS_FILE)
        if os.path.exists(KEY_FILE):
            os.remove(KEY_FILE)
        logger.info("Credenciales eliminadas exitosamente")
        return True
    except Exception as e:
        logger.error(f"Error eliminando credenciales: {e}")
        return False

def credentials_exist():
    """Verifica si existen credenciales guardadas"""
    return os.path.exists(CREDENTIALS_FILE) and os.path.exists(KEY_FILE)