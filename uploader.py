import os
import requests
import logging
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path

# =============================
# CARGAR VARIABLES DEL .env
# =============================
dotenv_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path)

USERNAME = os.getenv("NEXTCLOUD_USER")
PASSWORD = os.getenv("NEXTCLOUD_PASS")
NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL")
# Nueva variable para la carpeta raíz de las subidas
TARGET_FOLDER = os.getenv("NEXTCLOUD_TARGET_FOLDER", "TermuxUploads") 

# =============================
# CONFIGURACIÓN LOCAL
# =============================

CARPETA_MEDIA = Path("/storage/emulated/0/DCIM/Camera")
EXTENSIONES_VALIDAS = (".jpg", ".jpeg", ".png", ".mp4", ".mov", ".gif")

# ¡IMPORTANTE! Cambia esto a True para activar la eliminación de archivos locales.
# Por seguridad, empieza con False para probar que todo funciona bien.
DELETE_AFTER_UPLOAD = False 

# Archivos para guardar el estado y los logs
LOG_PATH = Path(__file__).resolve().parent / "subida.log"
UPLOADS_DB = Path(__file__).resolve().parent / "uploaded_files.txt"

# =============================
# CONFIGURAR LOGGER
# =============================
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def log(mensaje, nivel="info"):
    """Imprime en consola y guarda en el archivo de log."""
    print(mensaje)
    getattr(logging, nivel)(mensaje)

# =============================
# FUNCIONES DE GESTIÓN DE ESTADO
# =============================

def cargar_subidos():
    """Lee la lista de archivos ya subidos desde nuestra 'base de datos' de texto."""
    if not UPLOADS_DB.exists():
        return set()
    with open(UPLOADS_DB, 'r') as f:
        # Ignora líneas en blanco
        return set(line.strip() for line in f if line.strip())

def marcar_como_subido(filename: str):
    """Añade un archivo a la lista de subidos para no volver a procesarlo."""
    with open(UPLOADS_DB, 'a') as f:
        f.write(f"{filename}\n")

# =============================
# FUNCIONES DE NEXTCLOUD (WEBDAV)
# =============================

def crear_carpeta_remota(remote_path: str, session: requests.Session):
    """Crea una carpeta (y sus padres) en Nextcloud si no existen."""
    # Construye la URL base para las carpetas
    base_url = f"{NEXTCLOUD_URL.rstrip('/')}/remote.php/dav/files/{USERNAME}"
    
    # Divide la ruta en partes para crear cada nivel de carpeta
    parts = Path(remote_path).parts
    current_path = ""
    for part in parts:
        current_path = f"{current_path}/{part}"
        url = f"{base_url}/{current_path.strip('/')}"
        
        # Con PROPFIND verificamos si la carpeta ya existe
        response = session.request("PROPFIND", url, headers={'Depth': '0'})
        
        # Si la carpeta no existe (error 404), la creamos
        if response.status_code == 404:
            log(f"📁 Creando carpeta remota: {current_path}")
            mkcol_response = session.request("MKCOL", url)
            # Verificamos si la creación fue exitosa o si ya existía (código 405)
            if mkcol_response.status_code not in [201, 405]:
                log(f"❌ Error creando carpeta {current_path}: {mkcol_response.text}", "error")
                return False
    return True

def subir_archivo(file: Path, session: requests.Session):
    """Sube un archivo, lo marca como subido y opcionalmente lo elimina."""
    
    # 1. Organiza en carpetas por Año/Mes para mantener todo ordenado
    fecha_mod = datetime.fromtimestamp(file.stat().st_mtime)
    ano = fecha_mod.strftime("%Y")
    mes = fecha_mod.strftime("%m")
    
    carpeta_destino_remota = f"{TARGET_FOLDER.strip('/')}/{ano}/{mes}"
    
    # 2. Se asegura de que la carpeta remota exista antes de subir
    if not crear_carpeta_remota(carpeta_destino_remota, session):
        log(f"No se pudo crear la estructura de carpetas para {file.name}. Saltando archivo.", "error")
        return

    # 3. Construye la URL final y sube el archivo
    url = f"{NEXTCLOUD_URL.rstrip('/')}/remote.php/dav/files/{USERNAME}/{carpeta_destino_remota}/{file.name}"
    
    log(f"📤 Subiendo {file.name} a '{carpeta_destino_remota}'...")
    
    try:
        with open(file, 'rb') as f:
            response = session.put(url, data=f)

        # 4. Procesa la respuesta de Nextcloud
        if response.status_code in [201, 204]:  # 201 Creado, 204 Sobrescrito (Éxito)
            if response.status_code == 201:
                log(f"✅ Subido con éxito: {file.name}")
            else:
                log(f"⚠️  Ya existía y fue actualizado: {file.name}", "warning")
            
            # 5. Si la subida fue exitosa, lo anotamos en nuestro registro
            marcar_como_subido(file.name)
            
            # 6. (LA PARTE CLAVE) Elimina el archivo local si la opción está activada
            if DELETE_AFTER_UPLOAD:
                try:
                    os.remove(file)
                    log(f"🗑️  Archivo local eliminado: {file.name}", "info")
                except OSError as e:
                    log(f"❌ ¡CRÍTICO! No se pudo eliminar el archivo local {file.name}: {e}", "error")
        else:
            log(f"❌ Error al subir {file.name}: {response.status_code} - {response.text}", "error")

    except Exception as e:
        log(f"❌ Excepción crítica subiendo {file.name}: {e}", "error")

# =============================
# FUNCIÓN PRINCIPAL
# =============================
def main():
    """Orquesta todo el proceso."""
    log("🚀 Iniciando script de subida y limpieza...")

    if not all([USERNAME, PASSWORD, NEXTCLOUD_URL]):
        log("❌ Faltan variables de entorno (NEXTCLOUD_USER, NEXTCLOUD_PASS, NEXTCLOUD_URL).", "error")
        return

    if not CARPETA_MEDIA.exists():
        log(f"❌ La carpeta local no existe: {CARPETA_MEDIA}", "error")
        return
        
    if DELETE_AFTER_UPLOAD:
        log("🔴 MODO ELIMINACIÓN ACTIVADO. Los archivos locales se borrarán después de la subida.", "warning")
    else:
        log("🟢 MODO SEGURO. Los archivos locales NO se eliminarán.", "info")

    # Carga la lista de archivos que ya hemos subido antes
    subidos = cargar_subidos()
    log(f"🔎 Se encontraron {len(subidos)} archivos en el registro de subidas.")

    # Busca todos los archivos válidos en la carpeta
    archivos_locales = [
        f for f in CARPETA_MEDIA.glob("*") 
        if f.is_file() and f.suffix.lower() in EXTENSIONES_VALIDAS
    ]
    
    # Filtra para procesar solo los que no están en nuestro registro
    archivos_a_subir = [f for f in archivos_locales if f.name not in subidos]
    
    if not archivos_a_subir:
        log("📭 No hay archivos nuevos para subir. ¡Todo al día!")
        return

    log(f"✨ Se encontraron {len(archivos_a_subir)} archivo(s) nuevo(s) para procesar.")
    
    # Usa una "sesión" para reutilizar la conexión y la autenticación, es más eficiente
    with requests.Session() as session:
        session.auth = (USERNAME, PASSWORD)
        for archivo in archivos_a_subir:
            subir_archivo(archivo, session)
            
    log("🏁 Proceso finalizado.")

# =============================
# EJECUCIÓN
# =============================
if __name__ == "__main__":
    main()
