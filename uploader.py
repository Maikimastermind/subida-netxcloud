import os
import requests
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta
from pathlib import Path

# =============================
# CARGAR VARIABLES DEL .env
# =============================
dotenv_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path)

USERNAME = os.getenv("NEXTCLOUD_USER")
PASSWORD = os.getenv("NEXTCLOUD_PASS")
NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL")

# =============================
# CONFIGURACIÓN LOCAL
# =============================

CARPETA_MEDIA = Path("/storage/emulated/0/DCIM/Camera")
EXTENSIONES_VALIDAS = (".jpg", ".jpeg", ".png", ".mp4", ".mov")
MINUTOS_RECIENTES = 30
LOG_PATH = Path(__file__).resolve().parent / "subida.log"

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
    print(mensaje)
    getattr(logging, nivel)(mensaje)

# =============================
# FUNCIONES
# =============================

def es_reciente(file: Path, minutos: int = 30) -> bool:
    tiempo_mod = datetime.fromtimestamp(file.stat().st_mtime)
    return datetime.now() - tiempo_mod < timedelta(minutes=minutos)

def subir_archivo(file: Path):
    nombre_archivo = file.name
    url = f"{NEXTCLOUD_URL.rstrip('/')}/{nombre_archivo}"
    try:
        with open(file, 'rb') as f:
            response = requests.put(url, data=f, auth=(USERNAME, PASSWORD))

        if response.status_code == 201:
            log(f"✅ Subido: {nombre_archivo}")
        elif response.status_code == 204:
            log(f"⚠️ Ya existía y se actualizó: {nombre_archivo}", "warning")
        else:
            log(f"❌ Error subiendo {nombre_archivo}: {response.status_code} - {response.text}", "error")

    except Exception as e:
        log(f"❌ Excepción subiendo {nombre_archivo}: {e}", "error")

def main():
    log("🚀 Iniciando subida de archivos recientes...")

    if not CARPETA_MEDIA.exists():
        log(f"❌ Ruta no encontrada: {CARPETA_MEDIA}", "error")
        return

    archivos = list(CARPETA_MEDIA.glob("*"))
    recientes = [f for f in archivos if f.suffix.lower() in EXTENSIONES_VALIDAS and es_reciente(f, MINUTOS_RECIENTES)]

    if not recientes:
        log("📭 No hay archivos nuevos recientes para subir.")
        return

    log(f"📤 Subiendo {len(recientes)} archivo(s) reciente(s)...")
    for archivo in recientes:
        subir_archivo(archivo)

# =============================
# EJECUCIÓN
# =============================
if __name__ == "__main__":
    main()
