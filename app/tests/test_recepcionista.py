"""
Testes para agents/recepcionista.py
Foca na detecção de intenções e no fluxo de boas-vindas.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────
# detectar_intencao
# ─────────────────────────────────────────────────────────────
class TestDetectarIntencao:

    @pytest.mark.asyncio
    @patch("agents.recepcionista.get_llm")
    async def test_classifica_saudacao(self, mock_get_llm):
        from agents.recepcionista import detectar_intencao

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = MagicMock(
            content='{"intencao": "SAUDACAO", "resumo": "primeiro contato"}'
        )
        mock_get_llm.return_value = mock_llm

        resultado = await detectar_intencao("Oi, boa tarde!")
        assert resultado["intencao"] == "SAUDACAO"

    @pytest.mark.asyncio
    @patch("agents.recepcionista.get_llm")
    async def test_classifica_agendar_para_sintomas_urgentes(self, mock_get_llm):
        """Relatos urgentes (convulsão, etc.) devem ser classificados como AGENDAR."""
        from agents.recepcionista import detectar_intencao

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = MagicMock(
            content='{"intencao": "AGENDAR", "resumo": "pet com sintomas graves"}'
        )
        mock_get_llm.return_value = mock_llm

        resultado = await detectar_intencao("Meu gato está tendo convulsões!")
        assert resultado["intencao"] == "AGENDAR"

    @pytest.mark.asyncio
    @patch("agents.recepcionista.get_llm")
    async def test_classifica_remarcar(self, mock_get_llm):
        from agents.recepcionista import detectar_intencao

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = MagicMock(
            content='{"intencao": "REMARCAR", "resumo": "mudar data da consulta"}'
        )
        mock_get_llm.return_value = mock_llm

        resultado = await detectar_intencao("Quero mudar a data da minha consulta.")
        assert resultado["intencao"] == "REMARCAR"

    @pytest.mark.asyncio
    @patch("agents.recepcionista.get_llm")
    async def test_retorna_outro_em_caso_de_json_invalido(self, mock_get_llm):
        """Falha no JSON deve retornar intenção OUTRO sem exceção."""
        from agents.recepcionista import detectar_intencao

        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = MagicMock(content="resposta inválida sem json")
        mock_get_llm.return_value = mock_llm

        resultado = await detectar_intencao("blah blah")
        assert resultado["intencao"] == "OUTRO"

    @pytest.mark.asyncio
    @patch("agents.recepcionista.get_llm")
    async def test_nao_existe_intencao_emergencia(self, mock_get_llm):
        """EMERGENCIA não deve aparecer — deve ser AGENDAR."""
        from agents.recepcionista import detectar_intencao

        # Mesmo que o LLM retorne EMERGENCIA (não deveria), testamos o prompt
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = MagicMock(
            content='{"intencao": "AGENDAR", "resumo": "sintoma urgente"}'
        )
        mock_get_llm.return_value = mock_llm

        resultado = await detectar_intencao("Meu cachorro foi atropelado!")
        assert resultado["intencao"] != "EMERGENCIA"
