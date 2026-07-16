class AgenteAuditor:
    """Revisa salud de Calendar, OAuth y jobs con datos persistentes."""

    def _contar_auditoria(self, cur, condicion: str, por_actor: bool = False) -> int:
        identidad = (
            "COALESCE(NULLIF(actor, ''), tipo_evento)"
            if por_actor
            else "COALESCE(NULLIF(detalle->>'id_radar', ''), "
                 "NULLIF(detalle->>'google_event_id', ''), actor || ':' || tipo_evento)"
        )
        cur.execute(f"""
            SELECT COUNT(DISTINCT {identidad}) AS total
            FROM AUDITORIA_SEGURIDAD a
            WHERE fecha_evento >= NOW() - INTERVAL '24 hours'
              AND ({condicion})
        """)
        return cur.fetchone()['total'] or 0

    def generar_micro_reporte(self, cur) -> str:
        cur.execute("""
            SELECT COUNT(*) AS total
            FROM RADAR_EVENTOS_CITAS
            WHERE UPPER(COALESCE(estatus_confirmacion, '')) IN ('PENDIENTE', 'CONFIRMADO')
              AND google_event_id IS NULL
        """)
        citas_sin_id = cur.fetchone()['total'] or 0

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM TOKENS_OAUTH
            WHERE updated_at < NOW() - INTERVAL '50 days'
        """)
        tokens_viejos = cur.fetchone()['total'] or 0

        cur.execute("""
            SELECT EXTRACT(EPOCH FROM (NOW() - fecha_evento)) / 3600 AS horas
            FROM AUDITORIA_SEGURIDAD
            WHERE tipo_evento = 'EJECUCION_JOB'
              AND actor = 'auditoria_calendar'
              AND detalle->>'ok' = 'true'
            ORDER BY fecha_evento DESC
            LIMIT 1
        """)
        auditoria = cur.fetchone()
        horas_auditoria = float(auditoria['horas']) if auditoria and auditoria['horas'] is not None else None

        fallas_oauth = self._contar_auditoria(cur, """
            tipo_evento <> 'EJECUCION_JOB'
            AND (
                tipo_evento IN (
                    'CONFIRMACION_TOKEN_GOOGLE_FALLIDO',
                    'RECORDATORIO_TOKEN_GOOGLE_FALLIDO',
                    'TOKEN_GOOGLE_FALTANTE',
                    'GOOGLE_SIN_TOKEN',
                    'GOOGLE_SIN_PERMISOS',
                    'CANCELACION_GOOGLE_AUTORIZACION_FALLIDA',
                    'CORREO_CITA_REGISTRADA_TOKEN_FALLIDO'
                )
                OR (
                    tipo_evento IN (
                        'CONFIRMACION_ENVIO_FALLIDO',
                        'RECORDATORIO_CONFIRMADO_FALLIDO',
                        'CALENDAR_CONFIRMADA_FALLIDA',
                        'CANCELACION_GOOGLE_FALLIDA',
                        'GOOGLE_CONSULTA_FALLIDA'
                    )
                    AND LOWER(COALESCE(detalle::text, '')) LIKE ANY (ARRAY[
                        '%%invalid_grant%%',
                        '%%expired or revoked%%',
                        '%%debe reconectarse%%',
                        '%%no hay registros de token oauth%%'
                    ])
                )
            )
            AND NOT EXISTS (
                SELECT 1
                FROM TOKENS_OAUTH t
                WHERE LOWER(TRIM(t.correo_doctor)) = LOWER(TRIM(a.actor))
                  AND t.updated_at >= a.fecha_evento
            )
        """, por_actor=True)

        fallas_calendar = self._contar_auditoria(cur, """
            tipo_evento IN (
                'CALENDAR_CONFIRMADA_FALLIDA',
                'CANCELACION_GOOGLE_FALLIDA',
                'GOOGLE_CONSULTA_FALLIDA'
            )
            AND NOT (LOWER(COALESCE(detalle::text, '')) LIKE ANY (ARRAY[
                '%%invalid_grant%%',
                '%%expired or revoked%%',
                '%%debe reconectarse%%',
                '%%no hay registros de token oauth%%'
            ]))
            AND NOT (
                tipo_evento = 'CANCELACION_GOOGLE_FALLIDA'
                AND EXISTS (
                    SELECT 1
                    FROM AUDITORIA_SEGURIDAD recuperacion
                    WHERE recuperacion.fecha_evento > a.fecha_evento
                      AND recuperacion.tipo_evento IN (
                          'CANCELACION_AUTOMATICA_NO_CONFIRMADA',
                          'AGENDA_EVENTO_LIBERADO'
                      )
                      AND NULLIF(recuperacion.detalle->>'id_radar', '') = NULLIF(a.detalle->>'id_radar', '')
                )
            )
        """)

        fallas_gmail = self._contar_auditoria(cur, """
            tipo_evento IN (
                'CONFIRMACION_ENVIO_FALLIDO',
                'RECORDATORIO_CONFIRMADO_FALLIDO',
                'CORREO_CITA_REGISTRADA_FALLIDO'
            )
            AND LOWER(COALESCE(detalle::text, '')) NOT LIKE '%%no hay correo%%'
            AND NOT (LOWER(COALESCE(detalle::text, '')) LIKE ANY (ARRAY[
                '%%invalid_grant%%',
                '%%expired or revoked%%',
                '%%debe reconectarse%%',
                '%%no hay registros de token oauth%%'
            ]))
        """)

        alertas = []
        criticas = []
        if citas_sin_id:
            alertas.append(f'{citas_sin_id} citas sin google_event_id')
        if tokens_viejos:
            alertas.append(f'{tokens_viejos} tokens OAuth sin actualizacion reciente')
        if horas_auditoria is None or horas_auditoria > 2:
            criticas.append('Auditor Calendar sin ejecucion correcta reciente')
        if fallas_oauth:
            criticas.append(f'{fallas_oauth} falla(s) de token o permisos Google')
        if fallas_calendar:
            criticas.append(f'{fallas_calendar} falla(s) de Google Calendar')
        if fallas_gmail:
            criticas.append(f'{fallas_gmail} falla(s) de Gmail')

        if criticas:
            return 'ERROR_SISTEMA: ' + ', '.join(criticas + alertas) + '.'
        if alertas:
            return 'ATENCION: ' + ', '.join(alertas) + '.'
        return 'OK: Calendar, OAuth y Auditor Calendar al dia.'
