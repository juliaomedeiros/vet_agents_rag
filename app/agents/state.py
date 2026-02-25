from typing import Optional, Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
import uuid


class AgenteState(TypedDict):
    # ── Identificação ────────────────────────────────
    whatsapp: str                          # número do cliente
    cliente_id: Optional[str]             # UUID após identificação
    sessao_id: Optional[str]              # UUID da sessão atual
    cliente_nome: Optional[str]           # nome do cliente se já conhecido
    cliente_novo: bool                    # primeiro contato?

    # ── Mensagens (LangGraph gerencia o histórico) ───
    messages: Annotated[list, add_messages]

    # ── Intenção detectada ───────────────────────────
    intencao: Optional[str]               # SAUDACAO | INFORMACAO | AGENDAR
                                          # REMARCAR | CANCELAR | OUTRO

    # ── Contexto RAG ────────────────────────────────
    contexto_clinica: Optional[str]       # chunks recuperados da base
    historico_cliente: Optional[str]      # memória vetorial do cliente

    # ── Agendamento ──────────────────────────────────
    dados_agendamento: Optional[dict]     # pet, tipo, data, hora, motivo
    consulta_id: Optional[str]            # UUID após agendar

    # ── Guardrails ───────────────────────────────────
    entrada_bloqueada: bool               # guardrail de entrada bloqueou?
    saida_bloqueada: bool                 # guardrail de saída bloqueou?
    motivo_bloqueio: Optional[str]        # motivo do bloqueio

    # ── Resposta final ───────────────────────────────
    resposta_final: Optional[str]         # texto a enviar ao cliente
