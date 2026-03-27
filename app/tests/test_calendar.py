"""
Testes para integrations/google_calendar.py
Foca na função listar_horarios_disponiveis().
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from integrations.google_calendar import listar_horarios_disponiveis


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def make_freebusy_response(calendar_id: str, busy_periods: list[dict]) -> dict:
    """Monta resposta mockada da API freebusy."""
    return {"calendars": {calendar_id: {"busy": busy_periods}}}


# ─────────────────────────────────────────────────────────────
# Testes
# ─────────────────────────────────────────────────────────────
class TestListarHorariosDisponiveis:

    @patch("integrations.google_calendar.get_calendar_service")
    def test_retorna_slots_quando_agenda_livre(self, mock_service):
        """Com agenda completamente livre, deve retornar vários slots."""
        mock_freebusy = MagicMock()
        mock_freebusy.query.return_value.execute.return_value = make_freebusy_response(
            "primary", []  # nenhum período ocupado
        )
        mock_service.return_value.freebusy.return_value = mock_freebusy

        slots = listar_horarios_disponiveis("primary", dias=7)

        assert len(slots) > 0
        # todos os slots devem estar no formato DD/MM/AAAA HH:MM
        for s in slots:
            datetime.strptime(s, "%d/%m/%Y %H:%M")

    @patch("integrations.google_calendar.get_calendar_service")
    def test_slots_apenas_em_dias_uteis(self, mock_service):
        """Não deve haver slots em sábado ou domingo."""
        mock_freebusy = MagicMock()
        mock_freebusy.query.return_value.execute.return_value = make_freebusy_response(
            "primary", []
        )
        mock_service.return_value.freebusy.return_value = mock_freebusy

        slots = listar_horarios_disponiveis("primary", dias=14)

        for s in slots:
            dt = datetime.strptime(s, "%d/%m/%Y %H:%M")
            assert dt.weekday() < 5, f"Slot em fim de semana encontrado: {s}"

    @patch("integrations.google_calendar.get_calendar_service")
    def test_slots_dentro_do_horario_comercial(self, mock_service):
        """Todos os slots devem estar entre 14h e 18h."""
        mock_freebusy = MagicMock()
        mock_freebusy.query.return_value.execute.return_value = make_freebusy_response(
            "primary", []
        )
        mock_service.return_value.freebusy.return_value = mock_freebusy

        slots = listar_horarios_disponiveis("primary", dias=7)

        for s in slots:
            dt = datetime.strptime(s, "%d/%m/%Y %H:%M")
            assert 14 <= dt.hour < 18, f"Slot fora do horário comercial: {s}"

    @patch("integrations.google_calendar.get_calendar_service")
    def test_exclui_periodos_ocupados(self, mock_service):
        """Slots que colidem com períodos ocupados não devem aparecer."""
        # Ocupa um dia inteiro de amanhã
        amanha = (datetime.now() + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        busy = [
            {
                "start": amanha.replace(hour=14).isoformat() + "Z",
                "end": amanha.replace(hour=18).isoformat() + "Z",
            }
        ]
        mock_freebusy = MagicMock()
        mock_freebusy.query.return_value.execute.return_value = make_freebusy_response(
            "primary", busy
        )
        mock_service.return_value.freebusy.return_value = mock_freebusy

        slots = listar_horarios_disponiveis("primary", dias=2)

        # Nenhum slot deve ser de amanhã
        amanha_str = amanha.strftime("%d/%m/%Y")
        slots_amanha = [s for s in slots if s.startswith(amanha_str)]
        assert len(slots_amanha) == 0, f"Slots em dia ocupado: {slots_amanha}"

    @patch("integrations.google_calendar.get_calendar_service")
    def test_retorna_lista_vazia_quando_agenda_cheia(self, mock_service):
        """Com todos os dias ocupados (incluindo hoje), deve retornar lista vazia."""
        agora = datetime.now()
        busy = []
        for i in range(0, 31):  # começa em 0 para bloquear também o dia atual
            dia = agora + timedelta(days=i)
            busy.append({
                "start": dia.replace(hour=13, minute=0, second=0, microsecond=0).isoformat() + "Z",
                "end": dia.replace(hour=18, minute=30, second=0, microsecond=0).isoformat() + "Z",
            })

        mock_freebusy = MagicMock()
        mock_freebusy.query.return_value.execute.return_value = make_freebusy_response(
            "primary", busy
        )
        mock_service.return_value.freebusy.return_value = mock_freebusy

        slots = listar_horarios_disponiveis("primary", dias=30)
        assert slots == []

    @patch("integrations.google_calendar.get_calendar_service")
    def test_retorna_lista_vazia_em_caso_de_erro(self, mock_service):
        """Em caso de HttpError, deve retornar lista vazia sem exceção."""
        from googleapiclient.errors import HttpError
        from unittest.mock import Mock

        resp = Mock()
        resp.status = 403
        resp.reason = "Forbidden"
        mock_service.return_value.freebusy.return_value.query.return_value.execute.side_effect = (
            HttpError(resp=resp, content=b"Forbidden")
        )

        slots = listar_horarios_disponiveis("primary", dias=7)
        assert slots == []
