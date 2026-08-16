import unittest

from agentes.contexto_asistente import (
    CONTEXT_MAX_FOLLOWUPS,
    CONTEXT_TTL_SECONDS,
    consumir_contexto,
    contexto_habilitado_para_doctor,
    crear_contexto,
    es_follow_up,
    huella_contextual,
    resolver_continuidad,
    validar_contexto,
)
from agentes.asistente_panel import clasificar_local, explicacion_operativa


class ContextoAsistenteTest(unittest.TestCase):
    def test_edicion_ambigua_de_demo_conserva_contexto_de_cita(self):
        pregunta = "Edite una cita y ahora me sale raro"

        self.assertEqual(
            clasificar_local(pregunta, continuidad_edicion=True),
            "editar_flujo",
        )

        explicacion = explicacion_operativa(
            "editar_flujo",
            "48h",
            {"id_radar": "demo", "tipo_evento": "CITA_PACIENTE"},
            contexto_interfaz="editar_cita",
            continuidad_edicion=True,
        )
        respuesta = " ".join(str(valor) for valor in explicacion.values())
        self.assertIn("cita que tienes abierta", respuesta)
        self.assertNotIn("Nueva cita", respuesta)

    def test_edicion_ambigua_fuera_de_demo_mantiene_clasificacion_anterior(self):
        self.assertEqual(
            clasificar_local("Edite una cita y ahora me sale raro"),
            "cita",
        )

    def setUp(self):
        self.actor = huella_contextual("actor-demo", "test-secret")
        self.doctora = huella_contextual("dr.demo@doko.test", "test-secret")
        self.cita = huella_contextual("cita-demo", "test-secret")

    def contexto(self, **cambios):
        datos = {
            "actor_hash": self.actor,
            "doctor_hash": self.doctora,
            "categoria": "correo_no_llego",
            "origen": "gemini_intent",
            "id_radar_hash": None,
            "ahora": 1_000,
        }
        datos.update(cambios)
        return crear_contexto(**datos)

    def test_feature_flag_es_exacto_y_falla_cerrado(self):
        self.assertTrue(contexto_habilitado_para_doctor(
            "DR.DEMO@DOKO.TEST", "dr.demo@doko.test"
        ))
        self.assertFalse(contexto_habilitado_para_doctor(
            "doctora.real@doko.test", "dr.demo@doko.test"
        ))
        self.assertFalse(contexto_habilitado_para_doctor(
            "dr.demo@doko.test", ""
        ))

    def test_contexto_es_estructurado_sin_texto_libre(self):
        contexto = self.contexto()
        self.assertEqual(set(contexto), {
            "version", "actor", "doctora", "categoria", "referente",
            "id_radar_hash", "origen", "turnos_restantes", "creado_en",
            "expira_en",
        })
        self.assertEqual(contexto["turnos_restantes"], CONTEXT_MAX_FOLLOWUPS)
        self.assertEqual(
            contexto["expira_en"] - contexto["creado_en"],
            CONTEXT_TTL_SECONDS,
        )
        serializado = repr(contexto).lower()
        for prohibido in ("pregunta", "respuesta", "paciente", "medicamento"):
            self.assertNotIn(prohibido, serializado)

    def test_rechaza_categoria_inventada_y_error_de_gemini(self):
        self.assertIsNone(self.contexto(categoria="categoria_inventada"))
        self.assertIsNone(self.contexto(origen="gemini_error"))
        self.assertIsNone(self.contexto(actor_hash=""))
        self.assertIsNone(self.contexto(doctor_hash=""))

    def test_caduca_por_tiempo_sin_ventana_deslizante(self):
        contexto = self.contexto()
        vigente = validar_contexto(
            contexto,
            actor_hash=self.actor,
            doctor_hash=self.doctora,
            id_radar_hash=None,
            evento_vigente=True,
            ahora=1_599,
        )
        self.assertIsNotNone(vigente)
        self.assertIsNone(validar_contexto(
            contexto,
            actor_hash=self.actor,
            doctor_hash=self.doctora,
            id_radar_hash=None,
            evento_vigente=True,
            ahora=1_600,
        ))
        self.assertEqual(consumir_contexto(contexto)["expira_en"], 1_600)

    def test_maximo_dos_followups(self):
        contexto = self.contexto()
        primero = consumir_contexto(contexto)
        segundo = consumir_contexto(primero)
        self.assertEqual(primero["turnos_restantes"], 1)
        self.assertIsNone(segundo)

    def test_aislamiento_por_actor_y_doctora(self):
        contexto = self.contexto()
        otro_actor = huella_contextual("otro-actor", "test-secret")
        otra_doctora = huella_contextual("otra@doko.test", "test-secret")
        self.assertIsNone(validar_contexto(
            contexto,
            actor_hash=otro_actor,
            doctor_hash=self.doctora,
            id_radar_hash=None,
            evento_vigente=True,
            ahora=1_001,
        ))
        self.assertIsNone(validar_contexto(
            contexto,
            actor_hash=self.actor,
            doctor_hash=otra_doctora,
            id_radar_hash=None,
            evento_vigente=True,
            ahora=1_001,
        ))

    def test_cita_debe_seguir_siendo_la_misma_y_vigente(self):
        contexto = self.contexto(id_radar_hash=self.cita)
        otra_cita = huella_contextual("otra-cita", "test-secret")
        self.assertIsNone(validar_contexto(
            contexto,
            actor_hash=self.actor,
            doctor_hash=self.doctora,
            id_radar_hash=otra_cita,
            evento_vigente=True,
            ahora=1_001,
        ))
        self.assertIsNone(validar_contexto(
            contexto,
            actor_hash=self.actor,
            doctor_hash=self.doctora,
            id_radar_hash=self.cita,
            evento_vigente=False,
            ahora=1_001,
        ))

    def test_detecta_followup_pero_no_pregunta_autosuficiente(self):
        contexto = self.contexto()
        for pregunta in (
            "Cuales pueden ser las causas?",
            "Y eso que significa?",
            "Por que?",
        ):
            self.assertTrue(es_follow_up(
                pregunta, contexto_valido=contexto
            ), pregunta)
        for pregunta in (
            "Cuales citas estan canceladas?",
            "Como funciona la confirmacion por correo?",
            "Y cuanto cuesta el servicio?",
        ):
            self.assertFalse(es_follow_up(
                pregunta, contexto_valido=contexto
            ), pregunta)

    def test_una_accion_nunca_usa_contexto(self):
        contexto = self.contexto()
        self.assertFalse(es_follow_up(
            "Y la cancelas?",
            contexto_valido=contexto,
            accion_detectada=True,
        ))

    def test_demo_continua_categoria_y_recalcula_hechos_fuera_del_contexto(self):
        contexto = self.contexto()
        categoria, usado, restante = resolver_continuidad(
            habilitado=True,
            pregunta="Cuales pueden ser las causas?",
            categoria_actual="fuera_alcance",
            contexto_valido=contexto,
        )
        self.assertEqual(categoria, "correo_no_llego")
        self.assertTrue(usado)
        self.assertEqual(restante["turnos_restantes"], 1)
        self.assertNotIn("hechos", restante)

    def test_pregunta_autosuficiente_reemplaza_contexto(self):
        categoria, usado, restante = resolver_continuidad(
            habilitado=True,
            pregunta="Como funciona la confirmacion por correo?",
            categoria_actual="confirmacion",
            contexto_valido=self.contexto(),
        )
        self.assertEqual(categoria, "confirmacion")
        self.assertFalse(usado)
        self.assertIsNone(restante)

    def test_doctoras_reales_conservan_comportamiento_anterior(self):
        contexto = self.contexto()
        categoria, usado, restante = resolver_continuidad(
            habilitado=False,
            pregunta="Cuales pueden ser las causas?",
            categoria_actual="fuera_alcance",
            contexto_valido=contexto,
        )
        self.assertEqual(categoria, "fuera_alcance")
        self.assertFalse(usado)
        self.assertEqual(restante, contexto)

    def test_huellas_no_exponen_identificadores(self):
        huella = huella_contextual("paciente@example.com", "test-secret")
        self.assertEqual(len(huella), 32)
        self.assertNotIn("paciente", huella)
        self.assertNotIn("example", huella)


if __name__ == "__main__":
    unittest.main()
