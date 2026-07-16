import os
import threading
from dataclasses import dataclass
from datetime import date

from config_bunker import (
    AI_PROVIDER,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_PROJECT_ID,
    GOOGLE_KEY_PATH,
    GEMINI_DAILY_REQUEST_LIMIT,
)


_cuota_lock = threading.Lock()
_cuota_dia = None
_cuota_usada = 0


@dataclass(frozen=True)
class ResultadoGemini:
    texto: str
    modelo: str
    tokens_entrada: int = 0
    tokens_salida: int = 0
    tokens_razonamiento: int = 0
    tokens_total: int = 0


def _reservar_llamada_gemini() -> None:
    """Límite por instancia: evita una escalada accidental de costo público."""
    global _cuota_dia, _cuota_usada
    hoy = date.today()
    with _cuota_lock:
        if _cuota_dia != hoy:
            _cuota_dia, _cuota_usada = hoy, 0
        if _cuota_usada >= GEMINI_DAILY_REQUEST_LIMIT:
            raise RuntimeError('Límite diario local de Gemini alcanzado.')
        _cuota_usada += 1


class _GeminiApiModel:
    def __init__(self, model_name: str):
        import google.generativeai as genai

        if not GEMINI_API_KEY:
            raise RuntimeError("Falta GEMINI_API_KEY para usar Gemini API.")
        genai.configure(api_key=GEMINI_API_KEY)
        self._model = genai.GenerativeModel(model_name)

    def generate_content(self, prompt: str, generation_config=None):
        return self._model.generate_content(prompt, generation_config=generation_config)


class _VertexModel:
    def __init__(self, model_name: str):
        import vertexai
        from google.oauth2 import service_account
        from vertexai.generative_models import GenerativeModel

        if not os.path.exists(GOOGLE_KEY_PATH):
            raise FileNotFoundError(f"No se encuentra la llave: {GOOGLE_KEY_PATH}")

        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_KEY_PATH,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        vertexai.init(project=GEMINI_PROJECT_ID, location="us-central1", credentials=creds)
        self._model = GenerativeModel(model_name)

    def generate_content(self, prompt: str, generation_config=None):
        return self._model.generate_content(prompt, generation_config=generation_config)


def crear_modelo_gemini(model_name: str = None):
    nombre_modelo = model_name or GEMINI_MODEL
    if AI_PROVIDER == "vertex":
        return _VertexModel(nombre_modelo)
    return _GeminiApiModel(nombre_modelo)


def _entero_uso(uso, nombre: str) -> int:
    try:
        return max(0, int(getattr(uso, nombre, 0) or 0))
    except (TypeError, ValueError):
        return 0


def generar_texto_medido(
    prompt: str,
    model_name: str = None,
    *,
    max_output_tokens: int | None = None,
    temperature: float | None = None,
    aplicar_limite_local: bool = True,
) -> ResultadoGemini:
    """Genera texto y devuelve uso real sin cambiar la interfaz historica."""
    if aplicar_limite_local:
        _reservar_llamada_gemini()

    nombre_modelo = model_name or GEMINI_MODEL
    generation_config = {}
    if max_output_tokens is not None:
        generation_config["max_output_tokens"] = max(1, int(max_output_tokens))
    if temperature is not None:
        generation_config["temperature"] = float(temperature)

    respuesta = crear_modelo_gemini(nombre_modelo).generate_content(
        prompt,
        generation_config=generation_config or None,
    )
    uso = getattr(respuesta, "usage_metadata", None)
    entrada = _entero_uso(uso, "prompt_token_count")
    salida = _entero_uso(uso, "candidates_token_count")
    razonamiento = _entero_uso(uso, "thoughts_token_count")
    total = _entero_uso(uso, "total_token_count") or entrada + salida + razonamiento
    return ResultadoGemini(
        texto=(getattr(respuesta, "text", "") or "").strip(),
        modelo=str(getattr(respuesta, "model_version", "") or nombre_modelo),
        tokens_entrada=entrada,
        tokens_salida=salida,
        tokens_razonamiento=razonamiento,
        tokens_total=total,
    )


def generar_texto(prompt: str, model_name: str = None) -> str:
    return generar_texto_medido(prompt, model_name).texto
