from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgenteState
from app.agents.guardrails import guardrail_entrada, guardrail_saida
from app.agents.recepcionista import recepcionista
from app.agents.informacoes import agente_informacoes
from app.agents.agendamento import agente_agendamento


# ─────────────────────────────────────────────────────────────
# Funções de roteamento condicional
# ─────────────────────────────────────────────────────────────
def rotear_apos_guardrail_entrada(state: AgenteState) -> str:
    """Se guardrail bloqueou → encerra. Caso contrário → recepcionista."""
    if state.get("entrada_bloqueada"):
        return "guardrail_saida"
    return "recepcionista"


def rotear_apos_recepcionista(state: AgenteState) -> str:
    """Roteia baseado na intenção detectada."""
    intencao = state.get("intencao", "OUTRO")

    if intencao == "SAUDACAO":
        return "guardrail_saida"  # boas-vindas já geradas
    elif intencao == "INFORMACAO":
        return "informacoes"
    elif intencao in ["AGENDAR", "REMARCAR", "CANCELAR"]:
        return "agendamento"
    else:
        return "informacoes"  # fallback para informações


def rotear_apos_guardrail_saida(state: AgenteState) -> str:
    """Sempre encerra após guardrail de saída."""
    return END


# ─────────────────────────────────────────────────────────────
# Monta o grafo
# ─────────────────────────────────────────────────────────────
def criar_grafo(db: AsyncSession) -> StateGraph:
    """
    Cria e compila o grafo LangGraph com todos os agentes.
    O db é injetado via closure em cada nó.
    """
    grafo = StateGraph(AgenteState)

    # ── Adiciona nós ────────────────────────────────────────
    grafo.add_node("guardrail_entrada",
        lambda s: guardrail_entrada(s))

    grafo.add_node("recepcionista",
        lambda s: recepcionista(s, db))

    grafo.add_node("informacoes",
        lambda s: agente_informacoes(s, db))

    grafo.add_node("agendamento",
        lambda s: agente_agendamento(s, db))

    grafo.add_node("guardrail_saida",
        lambda s: guardrail_saida(s))

    # ── Define ponto de entrada ─────────────────────────────
    grafo.set_entry_point("guardrail_entrada")

    # ── Edges condicionais ──────────────────────────────────
    grafo.add_conditional_edges(
        "guardrail_entrada",
        rotear_apos_guardrail_entrada,
        {
            "recepcionista": "recepcionista",
            "guardrail_saida": "guardrail_saida",
        }
    )

    grafo.add_conditional_edges(
        "recepcionista",
        rotear_apos_recepcionista,
        {
            "guardrail_saida": "guardrail_saida",
            "informacoes": "informacoes",
            "agendamento": "agendamento",
        }
    )

    # ── Edges diretos ───────────────────────────────────────
    grafo.add_edge("informacoes", "guardrail_saida")
    grafo.add_edge("agendamento", "guardrail_saida")
    grafo.add_edge("guardrail_saida", END)

    return grafo.compile()


# ─────────────────────────────────────────────────────────────
# Executa o grafo com uma mensagem
# ─────────────────────────────────────────────────────────────
async def processar_mensagem(
    whatsapp: str,
    mensagem: str,
    db: AsyncSession,
    historico_mensagens: list = None
) -> str:
    """
    Ponto de entrada principal — chamado pelo webhook FastAPI.
    Retorna a resposta final para enviar ao cliente via WhatsApp.
    """
    from langchain_core.messages import HumanMessage

    grafo = criar_grafo(db)

    estado_inicial: AgenteState = {
        "whatsapp": whatsapp,
        "cliente_id": None,
        "sessao_id": None,
        "cliente_nome": None,
        "cliente_novo": False,
        "messages": (historico_mensagens or []) + [HumanMessage(content=mensagem)],
        "intencao": None,
        "contexto_clinica": None,
        "historico_cliente": None,
        "dados_agendamento": None,
        "consulta_id": None,
        "entrada_bloqueada": False,
        "saida_bloqueada": False,
        "motivo_bloqueio": None,
        "resposta_final": None,
    }

    resultado = await grafo.ainvoke(estado_inicial)
    return resultado.get("resposta_final", "Desculpe, tive um problema. Pode repetir? 😅")
