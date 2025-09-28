def upload_file(file_path):
    """Sube un archivo a Nextcloud vía WebDAV y lo elimina si es exitoso."""
    file_name = os.path.basename(file_path)
    url = NEXTCLOUD_URL + file_name
    with open(file_path, "rb") as f:
        response = requests.put(url, data=f, auth=(USERNAME, PASSWORD))
        if response.status_code in (200, 201, 204):
            print(f"✔️ Subido: {file_name}")
            save_uploaded_file(file_path)

            # Borrar el archivo local
            try:
                os.remove(file_path)
                print(f"🗑️ Borrado del dispositivo: {file_name}")
            except Exception as e:
                print(f"⚠️ No se pudo borrar {file_name}: {e}")

        else:
            print(f"❌ Error subiendo {file_name}: {response.status_code} - {response.text}")
