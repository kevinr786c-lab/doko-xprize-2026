"""Prueba de carga segura para Asistente Doko y búsquedas de agenda.

No envía correos, no modifica citas y no llama Google ni Gemini. La prueba usa
el consultorio indicado en ``DOKO_LOAD_TEST_DOCTOR`` y solo imprime métricas
agregadas, nunca datos de pacientes.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

from agentes.asistente_panel import interpretar_busqueda_agenda
from app_elite import app
from helpers.jwt_auth import generar_jwt
import routes.panel as panel_routes


TZ_TIJUANA = ZoneInfo("America/Tijuana")


def percentile(values: list[float], proportion: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * proportion)))
    return ordered[index]


def summarize(name: str, samples: list[dict]) -> dict:
    durations = [sample["duration_ms"] for sample in samples]
    statuses: dict[str, int] = {}
    for sample in samples:
        status = str(sample["status"])
        statuses[status] = statuses.get(status, 0) + 1
    successful = sum(1 for sample in samples if sample["ok"])
    return {
        "scenario": name,
        "requests": len(samples),
        "successful": successful,
        "errors": len(samples) - successful,
        "statuses": statuses,
        "latency_ms": {
            "min": round(min(durations, default=0.0), 2),
            "p50": round(statistics.median(durations), 2) if durations else 0.0,
            "p95": round(percentile(durations, 0.95), 2),
            "max": round(max(durations, default=0.0), 2),
        },
    }


def run_concurrent(name: str, total: int, concurrency: int, operation) -> dict:
    samples: list[dict] = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(operation) for _ in range(total)]
        for future in as_completed(futures):
            try:
                samples.append(future.result())
            except Exception as exc:  # pragma: no cover - diagnóstico de carga
                samples.append({
                    "ok": False,
                    "status": type(exc).__name__,
                    "duration_ms": 0.0,
                })
    summary = summarize(name, samples)
    elapsed = max(time.perf_counter() - started, 0.0001)
    summary["throughput_rps"] = round(total / elapsed, 2)
    return summary


def parser_operation() -> dict:
    started = time.perf_counter()
    now = datetime.now(TZ_TIJUANA)
    result = interpretar_busqueda_agenda("Quién viene mañana", now)
    return {
        "ok": bool(result and result.get("tipo") == "buscar_agenda"),
        "status": "local",
        "duration_ms": (time.perf_counter() - started) * 1000,
    }


def make_http_operation(path: str, method: str, token: str, payload: dict | None = None):
    def operation() -> dict:
        started = time.perf_counter()
        with app.test_client() as client:
            headers = {"Authorization": f"Bearer {token}"}
            if method == "POST":
                response = client.post(path, json=payload or {}, headers=headers)
            else:
                response = client.get(path, headers=headers)
            data = response.get_json(silent=True) or {}
        ok = response.status_code == 200
        if path == "/panel/asistente":
            ok = ok and data.get("categoria") == "buscar_agenda"
            ok = ok and data.get("fuente") == "reglas"
            ok = ok and data.get("uso_ia", {}).get("gemini") is False
        return {
            "ok": ok,
            "status": response.status_code,
            "duration_ms": (time.perf_counter() - started) * 1000,
        }

    return operation


def make_production_read_operation(token: str):
    import requests

    url = "https://doko.lat/panel/agenda?modo_asistente=1&dia_mes=19"

    def operation() -> dict:
        started = time.perf_counter()
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        data = response.json() if "application/json" in response.headers.get("content-type", "") else {}
        return {
            "ok": response.status_code == 200 and isinstance(data.get("opciones_fecha"), list),
            "status": response.status_code,
            "duration_ms": (time.perf_counter() - started) * 1000,
        }

    return operation


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga segura del Asistente Doko")
    parser.add_argument("--requests", type=int, default=40)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--confirm-read-only", action="store_true")
    parser.add_argument("--production-read", action="store_true")
    args = parser.parse_args()
    if not args.confirm_read_only:
        parser.error("Agrega --confirm-read-only para confirmar el modo seguro.")
    if not 1 <= args.concurrency <= 8:
        parser.error("La concurrencia segura debe estar entre 1 y 8.")
    if not 1 <= args.requests <= 200:
        parser.error("Las solicitudes deben estar entre 1 y 200.")

    doctor = os.environ.get("DOKO_LOAD_TEST_DOCTOR", "").strip().lower()
    if not doctor:
        parser.error(
            "Define DOKO_LOAD_TEST_DOCTOR con un consultorio de prueba autorizado."
        )
    token = generar_jwt(doctor)

    if args.production_read:
        scenario = run_concurrent(
            "production_agenda_day_options",
            args.requests,
            args.concurrency,
            make_production_read_operation(token),
        )
        report = {
            "safe_mode": {
                "writes": False,
                "google_calls": False,
                "gemini_calls": False,
                "patient_data_printed": False,
            },
            "target": "production_read_only",
            "concurrency": args.concurrency,
            "scenarios": [scenario],
            "passed": scenario["errors"] == 0,
        }
        print(json.dumps(report, indent=2, ensure_ascii=True))
        return 0 if report["passed"] else 1

    # Protecciones explícitas: ninguna prueba puede consumir API o telemetría.
    panel_routes.registrar_regla = lambda *args, **kwargs: None
    panel_routes.clasificar_con_gemini = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("Gemini no debe ejecutarse en esta prueba")
    )
    panel_routes._sincronizar_google_por_busqueda = lambda *args, **kwargs: None
    panel_routes._sincronizar_google_para_dia = lambda *args, **kwargs: None

    scenarios = [
        run_concurrent("parser_local", args.requests * 10, args.concurrency, parser_operation),
        run_concurrent(
            "assistant_search",
            args.requests,
            args.concurrency,
            make_http_operation(
                "/panel/asistente",
                "POST",
                token,
                {"pregunta": "Quién viene mañana", "contexto_interfaz": "modulo_asistente"},
            ),
        ),
        run_concurrent(
            "agenda_day_options",
            args.requests,
            args.concurrency,
            make_http_operation("/panel/agenda?modo_asistente=1&dia_mes=19", "GET", token),
        ),
        run_concurrent(
            "agenda_exact_date_google_mocked",
            args.requests,
            args.concurrency,
            make_http_operation("/panel/agenda?modo_asistente=1&fecha=2026-07-19", "GET", token),
        ),
    ]
    report = {
        "safe_mode": {
            "writes": False,
            "google_calls": False,
            "gemini_calls": False,
            "patient_data_printed": False,
        },
        "concurrency": args.concurrency,
        "scenarios": scenarios,
        "passed": all(scenario["errors"] == 0 for scenario in scenarios),
    }
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
