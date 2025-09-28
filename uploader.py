# -*- coding: utf-8 -*-
"""
Script mejorado para subir archivos a Nextcloud desde un dispositivo local (como Termux),
organizando los archivos por año y mes, y opcionalmente eliminándolos después.

Características:
- Carga de configuración desde un archivo .env.
- Registro de actividad en un archivo de log y en la consola.
- Mantiene un registro de archivos ya subidos para evitar duplicados.
- Organiza los archivos en carpetas remotas por Año/Mes.
- Interruptor de seguridad para habilitar/deshabilitar la eliminación de archivos locales.
- Barra de progreso visual durante la subida de archivos.
- Lógica encapsulada en una clase para mayor claridad y reutilización.
"""
import os
import requests
import logging
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
from typing import Set, Tuple
from tqdm import tqdm # Importamos tqdm para la barra de progreso

# =============================
# CARGAR VARIABLES DEL .env
# =============================
# Se buscará un archivo 'config.env' en el mismo directorio que el script.
dotenv_path = Path(__file__).resolve().parent / "config.env"
load_dotenv(dotenv_path)

# =============================
# CONFIGURACIÓN (Ahora principalmente desde .env)
# =============================

# --- Configuración del Servidor Nextcloud (desde .env) ---
USERNAME = os.getenv("NEXTCLOUD_USER")
PASSWORD = os.getenv("NEXTCLOUD_PASS")
NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL")
TARGET_FOLDER = os.getenv("NEXTCLOUD_TARGET_FOLDER", "TermuxUploads")

# --- Configuración Local (leída desde .env con valores por defecto) ---
# Directorio local donde se encuentran los archivos a subir
CARPETA_MEDIA = Path(os.getenv("LOCAL_DIR", "/storage/emulated/0/DCIM/Camera"))

# Extensiones de archivo que se considerarán para la subida (formato: .ext1,.ext2)
ext_str = os.getenv("EXTENSIONES_VALIDAS", ".jpg,.jpeg,.png,.mp4,.mov,.gif")
EXTENSIONES_VALIDAS = tuple(ext.strip() for ext in ext_str.split(','))

# ¡IMPORTANTE! Activa la eliminación de archivos locales desde el .env
# Se considera 'true', '1' o 't' (insensible a mayúsculas) como verdadero.
DELETE_AFTER_UPLOAD = os.getenv("DELETE_AFTER_UPLOAD", "False").lower() in ('true', '1', 't')

# --- Archivos de Estado y Log ---
LOG_PATH = Path(__file__).resolve().parent / "subida.log"
UPLOADS_DB_PATH = Path(__file__).resolve().parent / "uploaded_files.txt"

# =============================
# CONFIGURAR LOGGER
# =============================
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding='utf-8' # Asegura que los caracteres especiales se guarden bien
)

def log(mensaje: str, level: str = "info"):
    """Imprime en consola y guarda en el archivo de log."""
    print(mensaje)
    getattr(logging, level.lower())(mensaje)

# =============================
# CLASE PRINCIPAL: NextcloudUploader
# =============================

class NextcloudUploader:
    """Gestiona la conexión, estado y subida de archivos a Nextcloud."""

    def __init__(self, base_url: str, username: str, password: str):
        """Inicializa el cliente con las credenciales y una sesión de requests."""
        if not all([base_url, username, password]):
            raise ValueError("URL, usuario y contraseña de Nextcloud no pueden estar vacíos.")
        
        self.base_url = f"{base_url.rstrip('/')}/remote.php/dav/files/{username}"
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.uploaded_files_db = UPLOADS_DB_PATH
        self.uploaded_files: Set[str] = self._cargar_subidos()

    def _cargar_subidos(self) -> Set[str]:
        """Lee la lista de archivos ya subidos desde el archivo de estado."""
        if not self.uploaded_files_db.exists():
            return set()
        try:
            with open(self.uploaded_files_db, 'r', encoding='utf-8') as f:
                return {line.strip() for line in f if line.strip()}
        except IOError as e:
            log(f"Error al leer el registro de archivos subidos: {e}", "error")
            return set()

    def _marcar_como_subido(self, filename: str):
        """Añade un archivo a la lista de subidos para no volver a procesarlo."""
        try:
            with open(self.uploaded_files_db, 'a', encoding='utf-8') as f:
                f.write(f"{filename}\n")
            self.uploaded_files.add(filename)
        except IOError as e:
            log(f"Error al guardar en el registro de subidos: {e}", "error")

    def _crear_carpeta_remota(self, remote_path: str) -> bool:
        """Crea una carpeta (y sus padres) en Nextcloud si no existen."""
        parts = Path(remote_path).parts
        current_path = ""
        for part in parts:
            current_path = f"{current_path}/{part}" if current_path else part
            url = f"{self.base_url}/{current_path}"
            
            # Con PROPFIND verificamos si la carpeta ya existe
            response = self.session.request("PROPFIND", url, headers={'Depth': '0'})
            
            if response.status_code == 404:
                log(f"📁 Creando carpeta remota: {current_path}")
                mkcol_response = self.session.request("MKCOL", url)
                if mkcol_response.status_code not in [201, 405]: # 201: Creado, 405: Ya existe
                    log(f"❌ Error creando carpeta {current_path}: {mkcol_response.text}", "error")
                    return False
        return True

    def subir_archivo(self, file_path: Path) -> bool:
        """Sube un único archivo a Nextcloud."""
        try:
            # Organiza en carpetas por Año/Mes para mantener todo ordenado
            fecha_mod = datetime.fromtimestamp(file_path.stat().st_mtime)
            ano = fecha_mod.strftime("%Y")
            mes = fecha_mod.strftime("%m")
            
            carpeta_destino_remota = f"{TARGET_FOLDER.strip('/')}/{ano}/{mes}"
            
            if not self._crear_carpeta_remota(carpeta_destino_remota):
                log(f"No se pudo crear la estructura de carpetas para {file_path.name}. Saltando archivo.", "error")
                return False

            url_destino = f"{self.base_url}/{carpeta_destino_remota}/{file_path.name}"
            
            with open(file_path, 'rb') as f:
                response = self.session.put(url_destino, data=f)

            if response.status_code in [201, 204]:  # 201 Creado, 204 Sobrescrito (Éxito)
                self._marcar_como_subido(file_path.name)
                
                if DELETE_AFTER_UPLOAD:
                    try:
                        os.remove(file_path)
                        log(f"🗑️ Archivo local eliminado: {file_path.name}", "info")
                    except OSError as e:
                        log(f"❌ ¡CRÍTICO! No se pudo eliminar el archivo local {file_path.name}: {e}", "error")
                return True
            else:
                log(f"❌ Error al subir {file_path.name}: {response.status_code} - {response.text}", "error")
                return False

        except requests.exceptions.RequestException as e:
            log(f"❌ Error de red subiendo {file_path.name}: {e}", "error")
            return False
        except Exception as e:
            log(f"❌ Excepción crítica subiendo {file_path.name}: {e}", "error")
            return False

    def run(self):
        """Ejecuta el proceso completo de escaneo y subida."""
        log("🚀 Iniciando script de subida y limpieza...")

        if not CARPETA_MEDIA.exists():
            log(f"❌ La carpeta local no existe: {CARPETA_MEDIA}", "error")
            return
            
        if DELETE_AFTER_UPLOAD:
            log("🔴 MODO ELIMINACIÓN ACTIVADO. Los archivos se borrarán después de subir.", "warning")
        else:
            log("🟢 MODO SEGURO. Los archivos locales NO se eliminarán.", "info")

        log(f"🔎 Se encontraron {len(self.uploaded_files)} archivos en el registro de subidas.")

        archivos_locales = [
            f for f in CARPETA_MEDIA.iterdir()
            if f.is_file() and f.suffix.lower() in EXTENSIONES_VALIDAS
        ]
        
        archivos_a_subir = [f for f in archivos_locales if f.name not in self.uploaded_files]
        
        if not archivos_a_subir:
            log("📭 No hay archivos nuevos para subir. ¡Todo al día!")
            return

        log(f"✨ Se encontraron {len(archivos_a_subir)} archivo(s) nuevo(s) para procesar.")
        
        # Usamos tqdm para crear una barra de progreso
        archivos_exitosos = 0
        with tqdm(total=len(archivos_a_subir), desc="Subiendo archivos", unit="file") as pbar:
            for archivo in archivos_a_subir:
                pbar.set_postfix_str(archivo.name, refresh=True)
                if self.subir_archivo(archivo):
                    archivos_exitosos += 1
                pbar.update(1)
        
        log(f"✅ Subida completada. {archivos_exitosos}/{len(archivos_a_subir)} archivos subidos con éxito.")
        log("🏁 Proceso finalizado.")

# =============================
# EJECUCIÓN
# =============================
def main():
    """Punto de entrada principal del script."""
    try:
        uploader = NextcloudUploader(
            base_url=NEXTCLOUD_URL,
            username=USERNAME,
            password=PASSWORD
        )
        uploader.run()
    except ValueError as e:
        log(f"❌ Error de configuración: {e}", "critical")
    except Exception as e:
        log(f"❌ Ocurrió un error inesperado en la ejecución: {e}", "critical")
        
if __name__ == "__main__":
    main()

