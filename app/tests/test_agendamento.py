"""
Testes para agents/agendamento.py
Foca na lógica de agendar, remarcar e cancelar (com mocks de DB e Calendar).
"""
import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from langchain_core.messages import HumanMessage, AIMessage


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────
def make_state(intencao: str = "AGENDAR", messages: list = None) -> dict:
    return {
        "whatsapp": "5511999990000",
        "cliente_id": str(uuid.uuid4()),
        "sessao_id": str(uuid.uuid4()),
        "cliente_nome": "João",
        "cliente_novo": False,
        "messages": messages or [HumanMessage(content="quero agendar uma consulta")],
        "intencao": intencao,
        "contexto_clinica": "",
        "historico_cliente": "",
        "dados_agendamento": None,
        "consulta_id": None,
        "entrada_bloqueada": False,
        "saida_bloqueada": False,
        "motivo_bloqueio": None,
        "resposta_final": None,
    }


def make_consulta(
    tipo_value: str = "clinica_geral",
    data_hora: datetime = None,
    google_event_id: str = "evt_123",
) -> MagicMock:
    c = MagicMock()
    c.id = uuid.uuid4()
    c.tipo = MagicMock(value=tipo_value)
    c.data_hora = data_hora or datetime(2026, 4, 15, 14, 0)
    c.google_event_id = google_event_id
    c.motivo = "mancando"
    c.status = "agendada"
    return c


def make_vet() -> MagicMock:
    v = MagicMock()
    v.id = uuid.uuid4()
    v.nome = "Dr. Daniel Travassos"
    v.email = "daniel@clinica.com"
    v.google_calendar_id = "primary"
    return v


# ─────────────────────────────────────────────────────────────
# Testes — CANCELAR
# ─────────────────────────────────────────────────────────────
class TestCancelar:

    @pytest.mark.asyncio
    @patch("agents.agendamento.buscar_veterinario_principal")
    @patch("agents.agendamento.buscar_consultas_cliente")
    async def test_cancela_consulta_unica(
        self, mock_buscar, mock_vet, monkeypatch
    ):
        from agents.agendamento import agente_agendamento
        from db.models import StatusConsulta

        consulta = make_consulta()
        mock_buscar.return_value = [consulta]
        mock_vet.return_value = make_vet()

        db = AsyncMock()
        state = make_state("CANCELAR")

        with (
            patch("agents.agendamento.cancelar_evento"),
            patch("agents.agendamento.notificar_cancelamento"),
        ):
            resultado = await agente_agendamento(state, db)

        assert "cancelada" in resultado["resposta_final"].lower()

    @pytest.mark.asyncio
    @patch("agents.agendamento.buscar_veterinario_principal")
    @patch("agents.agendamento.buscar_consultas_cliente")
    async def test_sem_consulta_retorna_mensagem_adequada(
        self, mock_buscar, mock_vet
    ):
        from agents.agendamento import agente_agendamento

        mock_buscar.return_value = []
        mock_vet.return_value = make_vet()

        db = AsyncMock()
        state = make_state("CANCELAR")
        resultado = await agente_agendamento(state, db)

        assert resultado["resposta_final"] is not None
        assert len(resultado["resposta_final"]) > 0

    @pytest.mark.asyncio
    @patch("agents.agendamento.buscar_veterinario_principal")
    @patch("agents.agendamento.buscar_consultas_cliente")
    async def test_multiplas_consultas_pede_confirmacao(
        self, mock_buscar, mock_vet
    ):
        from agents.agendamento import agente_agendamento

        consulta1 = make_consulta("clinica_geral", datetime(2026, 4, 15, 14, 0))
        consulta2 = make_consulta("neurologia", datetime(2026, 4, 20, 15, 0))
        mock_buscar.return_value = [consulta1, consulta2]
        mock_vet.return_value = make_vet()

        db = AsyncMock()
        state = make_state("CANCELAR")
        resultado = await agente_agendamento(state, db)

        # Deve pedir qual consulta cancelar
        assert "consulta" in resultado["resposta_final"].lower()


# ─────────────────────────────────────────────────────────────
# Testes — REMARCAR
# ─────────────────────────────────────────────────────────────
class TestRemarcar:

    @pytest.mark.asyncio
    @patch("agents.agendamento.buscar_veterinario_principal")
    @patch("agents.agendamento.buscar_consultas_cliente")
    @patch("agents.agendamento.listar_horarios_disponiveis")
    @patch("agents.agendamento.get_llm")
    async def test_remarcar_com_dados_completos(
        self, mock_llm, mock_horarios, mock_buscar, mock_vet
    ):
        from agents.agendamento import agente_agendamento

        consulta = make_consulta()
        mock_buscar.return_value = [consulta]
        mock_vet.return_value = make_vet()
        mock_horarios.return_value = ["28/04/2026 14:00", "28/04/2026 14:30"]

        llm_instance = AsyncMock()
        llm_instance.ainvoke.return_value = MagicMock(content=json.dumps({
            "consulta_id": str(consulta.id),
            "nova_data": "28/04/2026",
            "nova_hora": "14:00",
            "dados_completos": True,
            "proximo_passo": "",
        }))
        mock_llm.return_value = llm_instance

        db = AsyncMock()
        state = make_state("REMARCAR", [HumanMessage(content="quero remarcar para dia 28")])

        with (
            patch("agents.agendamento.remarcar_evento"),
            patch("agents.agendamento.notificar_remarcacao"),
        ):
            resultado = await agente_agendamento(state, db)

        assert "remarcada" in resultado["resposta_final"].lower()

    @pytest.mark.asyncio
    @patch("agents.agendamento.buscar_veterinario_principal")
    @patch("agents.agendamento.buscar_consultas_cliente")
    @patch("agents.agendamento.listar_horarios_disponiveis")
    @patch("agents.agendamento.get_llm")
    async def test_remarcar_sem_dados_retorna_pergunta(
        self, mock_llm, mock_horarios, mock_buscar, mock_vet
    ):
        from agents.agendamento import agente_agendamento

        consulta = make_consulta()
        mock_buscar.return_value = [consulta]
        mock_vet.return_value = make_vet()
        mock_horarios.return_value = ["28/04/2026 14:00"]

        llm_instance = AsyncMock()
        llm_instance.ainvoke.return_value = MagicMock(content=json.dumps({
            "dados_completos": False,
            "proximo_passo": "Qual data prefere?",
        }))
        mock_llm.return_value = llm_instance

        db = AsyncMock()
        state = make_state("REMARCAR", [HumanMessage(content="quero remarcar")])
        resultado = await agente_agendamento(state, db)

        assert resultado["resposta_final"] is not None


# ─────────────────────────────────────────────────────────────
# Testes — AGENDAR
# ─────────────────────────────────────────────────────────────
class TestAgendar:

    @pytest.mark.asyncio
    @patch("agents.agendamento.buscar_veterinario_principal")
    @patch("agents.agendamento.listar_horarios_disponiveis")
    @patch("agents.agendamento.get_llm")
    async def test_retorna_pergunta_quando_dados_incompletos(
        self, mock_llm, mock_horarios, mock_vet
    ):
        from agents.agendamento import agente_agendamento

        mock_vet.return_value = make_vet()
        mock_horarios.return_value = ["28/04/2026 14:00"]

        llm_instance = AsyncMock()
        # Primeira invocação: coleta de dados (incompleto)
        # Segunda invocação: resposta intermediária
        llm_instance.ainvoke.side_effect = [
            MagicMock(content=json.dumps({
                "dados_completos": False,
                "precisa_template_tutor": False,
                "proximo_passo": "O que está acontecendo com seu pet?",
            })),
            MagicMock(content="O que está acontecendo com seu pet? 🐾"),
        ]
        mock_llm.return_value = llm_instance

        db = AsyncMock()
        state = make_state("AGENDAR")
        resultado = await agente_agendamento(state, db)

        assert resultado["resposta_final"] is not None
        assert resultado.get("consulta_id") is None  # não criou consulta

    @pytest.mark.asyncio
    @patch("agents.agendamento.buscar_veterinario_principal")
    @patch("agents.agendamento.listar_horarios_disponiveis")
    @patch("agents.agendamento.get_llm")
    async def test_exibe_template_tutor_quando_necessario(
        self, mock_llm, mock_horarios, mock_vet
    ):
        from agents.agendamento import agente_agendamento, TEMPLATE_TUTOR

        mock_vet.return_value = make_vet()
        mock_horarios.return_value = ["28/04/2026 14:00"]

        template_simulado = f"Para finalizar, preciso dos seus dados:\n{TEMPLATE_TUTOR}"
        llm_instance = AsyncMock()
        llm_instance.ainvoke.side_effect = [
            MagicMock(content=json.dumps({
                "dados_completos": False,
                "precisa_template_tutor": True,
                "proximo_passo": "Informe os dados do tutor.",
            })),
            MagicMock(content=template_simulado),
        ]
        mock_llm.return_value = llm_instance

        db = AsyncMock()
        state = make_state("AGENDAR", [HumanMessage(content="quero dia 28 às 14h")])
        resultado = await agente_agendamento(state, db)

        assert "Nome do Tutor" in resultado["resposta_final"]
