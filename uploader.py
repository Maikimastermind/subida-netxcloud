import os
import requests
from pathlib import Path
import socket
from dotenv import load_dotenv

# Cargar configuración desde config.env
load_dotenv("config.env")

NEXTCLOUD_URL = os.getenv("NEXTCLOUD_URL")  # ej: http://192.168.1.50:8080/remote.php/webdav/Fotos/
USERNAME = os.getenv("NEXTCLOUD_USER")
PASSWORD = os.getenv("NEXTCLOUD_PASS")
LOCAL_DIR = os.getenv("LOCAL_DIR", "/sdcard/DCIM/Camera")
LOG_FILE = "uploaded_files.txt"


def is_wifi_connected():
    """Verifica si hay conexión a internet vía WiFi (ping DNS simple)."""
    try:
        socket.setdefaulttimeout(3)
        socket.gethostbyname("nextcloud.com")
        return True
    except socket.error:
        return False


def load_uploaded_files():
    """Carga lista de archivos ya subidos."""
    if not Path(LOG_FILE).exists():
        return set()
    with open(LOG_FILE, "r") as f:
        return set(line.strip() for line in f)


def save_uploaded_file(file_path):
    """Guarda archivo como subido en el log."""
    with open(LOG_FILE, "a") as f:
        f.write(file_path + "\n")


def upload_file(file_path):
    """Sube un archivo a Nextcloud vía WebDAV y lo elimina si es exitoso."""
    file_name = os.path.basename(file_path)
    url = NEXTCLOUD_URL + file_name
    with open(file_path, "rb") as f:
        response = requests.put(url, data=f, auth=(USERNAME, PASSWORD))
        if response.status_code in (200, 201, 204):
            print(f"✔️ Subido: {file_name}")
            save_uploaded_file(file_path)

            # Intentar borrar archivo local
            try:
                os.remove(file_path)
                print(f"🗑️ Borrado del dispositivo: {file_name}")
            except Exception as e:
                print(f"⚠️ No se pudo borrar {file_name}: {e}")
        else:
            print(f"❌ Error subiendo {file_name}: {response.status_code} - {response.text}")


def main():
    if not is_wifi_connected():
        print("⚠️ No hay conexión WiFi. Espera a conectarte para subir archivos.")
        return

    uploaded_files = load_uploaded_files()
    local_dir = Path(LOCAL_DIR)

    for file in local_dir.glob("*.*"):
        if str(file) not in uploaded_files:
            upload_file(str(file))


if __name__ == "__main__":
    main()
