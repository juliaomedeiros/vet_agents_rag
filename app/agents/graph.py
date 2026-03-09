from langgraph.graph import StateGraph, END
from sqlalchemy.ext.asyncio import AsyncSession

from agents.state import AgenteState
from agents.guardrails import guardrail_entrada, guardrail_saida
from agents.recepcionista import recepcionista
from agents.informacoes import agente_informacoes
from agents.agendamento import agente_agendamento


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
    if state.get("resposta_final"):
        return "guardrail_saida"

    intencao = state.get("intencao", "OUTRO")

    if intencao == "INFORMACAO":
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
    async def node_guardrail_entrada(s):
        return await guardrail_entrada(s)

    async def node_recepcionista(s):
        return await recepcionista(s, db)

    async def node_informacoes(s):
        return await agente_informacoes(s, db)

    async def node_agendamento(s):
        return await agente_agendamento(s, db)

    async def node_guardrail_saida(s):
        return await guardrail_saida(s)

    grafo.add_node("guardrail_entrada", node_guardrail_entrada)
    grafo.add_node("recepcionista", node_recepcionista)
    grafo.add_node("informacoes", node_informacoes)
    grafo.add_node("agendamento", node_agendamento)
    grafo.add_node("guardrail_saida", node_guardrail_saida)

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
    from langchain_core.messages import HumanMessage, AIMessage
    from db.models import Cliente, Sessao, Mensagem, OrigemMensagem
    from sqlalchemy import select
    import uuid

    # Identifica sessão ativa e histórico
    history = []
    res_cliente = await db.execute(select(Cliente).where(Cliente.whatsapp == whatsapp))
    cliente = res_cliente.scalar_one_or_none()
    
    if cliente:
        res_sessao = await db.execute(
            select(Sessao)
            .where(Sessao.cliente_id == cliente.id, Sessao.ativa == True)
            .order_by(Sessao.iniciada_em.desc())
            .limit(1)
        )
        sessao_ativa = res_sessao.scalar_one_or_none()
        if sessao_ativa:
            res_msg = await db.execute(select(Mensagem).where(Mensagem.sessao_id == sessao_ativa.id).order_by(Mensagem.criado_em.desc()).limit(10))
            for m in reversed(res_msg.scalars().all()):
                if m.origem == OrigemMensagem.cliente:
                    history.append(HumanMessage(content=m.conteudo))
                else:
                    history.append(AIMessage(content=m.conteudo))

    grafo = criar_grafo(db)

    estado_inicial: AgenteState = {
        "whatsapp": whatsapp,
        "cliente_id": None,
        "sessao_id": None,
        "cliente_nome": None,
        "cliente_novo": False,
        "messages": (historico_mensagens or history) + [HumanMessage(content=mensagem)],
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
    resposta = resultado.get("resposta_final", "Desculpe, tive um problema. Pode repetir? 😅")

    sessao_id = resultado.get("sessao_id")
    cliente_id = resultado.get("cliente_id")
    if sessao_id and cliente_id:
        msg_user = Mensagem(sessao_id=uuid.UUID(sessao_id), cliente_id=uuid.UUID(cliente_id), origem=OrigemMensagem.cliente, conteudo=mensagem)
        msg_bot  = Mensagem(sessao_id=uuid.UUID(sessao_id), cliente_id=uuid.UUID(cliente_id), origem=OrigemMensagem.agente, conteudo=resposta)
        db.add_all([msg_user, msg_bot])
        await db.commit()

    return resposta
