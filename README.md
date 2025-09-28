# 📸 Nextcloud Uploader (Python + Termux)

Este script sube automáticamente las fotos y videos de tu cámara de Android a tu servidor **Nextcloud**, usando **Termux**.

## 🚀 Requisitos
- Android con [Termux](https://f-droid.org/packages/com.termux/)
- Servidor Nextcloud accesible en la red (ej: Raspberry Pi)

## 🔧 Instalación
```bash
pkg update && pkg upgrade -y
pkg install python git -y
pip install -r requirements.txt
