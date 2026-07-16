import os
import uuid
from datetime import timedelta

from google.cloud import storage

from config_bunker import GCS_BUCKET_NAME, GOOGLE_KEY_PATH


CARPETAS_PERMITIDAS = {
    "doctores",
    "productos",
    "fotosweb",
    "sitios-medicos",
    "documentos/surtido",
    "documentos/entregas",
}

EXTENSIONES_PERMITIDAS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 5 * 1024 * 1024


def extension_permitida(filename: str) -> bool:
    _, ext = os.path.splitext(filename or "")
    return ext.lower() in EXTENSIONES_PERMITIDAS


CARPETAS_PRIVADAS = {"documentos/surtido", "documentos/entregas"}


def _get_bucket():
    # En Cloud Run usa Application Default Credentials de la cuenta de servicio.
    # En desarrollo conserva el JSON local, sin empaquetarlo en la imagen Docker.
    if os.path.exists(GOOGLE_KEY_PATH):
        client = storage.Client.from_service_account_json(GOOGLE_KEY_PATH)
    else:
        client = storage.Client()
    return client.bucket(GCS_BUCKET_NAME)


def _inferir_mime(ext: str) -> str:
    ext = ext.lower()
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".png":
        return "image/png"
    if ext == ".webp":
        return "image/webp"
    return "application/octet-stream"


def _contenido_imagen_valido(archivo_bytes: bytes, ext: str) -> bool:
    ext = ext.lower()
    if ext in {".jpg", ".jpeg"}:
        return archivo_bytes.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return archivo_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".webp":
        return len(archivo_bytes) >= 12 and archivo_bytes[:4] == b"RIFF" and archivo_bytes[8:12] == b"WEBP"
    return False


def orquestar_subida_v92(archivo_bytes: bytes, nombre_original: str, tipo_carpeta: str) -> str:
    """Sube una imagen y devuelve URL pública o referencia privada de GCS."""
    if tipo_carpeta not in CARPETAS_PERMITIDAS:
        raise ValueError(f"Violacion de seguridad: la carpeta {tipo_carpeta} no esta permitida.")

    _, ext = os.path.splitext(nombre_original or "")
    ext = ext.lower()

    if not extension_permitida(nombre_original):
        raise ValueError(f"Archivo bloqueado. Extension recibida: {ext}")

    if len(archivo_bytes) > MAX_BYTES:
        raise ValueError("Archivo excede el tamano maximo permitido de 5 MB.")

    if not _contenido_imagen_valido(archivo_bytes, ext):
        raise ValueError("Archivo bloqueado. El contenido no coincide con una imagen permitida.")

    nuevo_nombre_archivo = f"{tipo_carpeta}/{uuid.uuid4().hex}{ext}"
    bucket = _get_bucket()
    blob = bucket.blob(nuevo_nombre_archivo)
    blob.upload_from_string(archivo_bytes, content_type=_inferir_mime(ext))

    if tipo_carpeta in CARPETAS_PRIVADAS:
        return f"gs://{GCS_BUCKET_NAME}/{nuevo_nombre_archivo}"
    return blob.public_url


def subir_archivo(archivo_bytes: bytes, nombre_original: str, carpeta: str) -> str:
    """Alias compatible para las rutas existentes."""
    return orquestar_subida_v92(archivo_bytes, nombre_original, carpeta)


def eliminar_archivo(url_publica: str) -> bool:
    try:
        prefix_publico = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/"
        prefix_privado = f"gs://{GCS_BUCKET_NAME}/"
        if not url_publica.startswith((prefix_publico, prefix_privado)):
            return False

        blob_name = url_publica.replace(prefix_publico, "").replace(prefix_privado, "")
        bucket = _get_bucket()
        blob = bucket.blob(blob_name)
        blob.delete()
        return True
    except Exception:
        return False


def generar_url_firmada(referencia_gcs: str, minutos: int = 15) -> str | None:
    """Genera acceso temporal para evidencia privada; no guarda enlaces expirables."""
    prefijo = f"gs://{GCS_BUCKET_NAME}/"
    if not referencia_gcs or not referencia_gcs.startswith(prefijo):
        return None
    blob = _get_bucket().blob(referencia_gcs[len(prefijo):])
    return blob.generate_signed_url(expiration=timedelta(minutes=minutos), method="GET")
