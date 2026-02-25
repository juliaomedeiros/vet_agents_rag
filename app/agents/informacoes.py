from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.state import AgenteState
from app.core.llm import get_llm
from sqlalchemy.ext.asyncio import AsyncSession


PROMPT_INFORMACOES = """
Você é a recepcionista de uma clínica veterinária especializada.
Responda a dúvida do cliente de forma simpática, coloquial e precisa.

Use APENAS as informações do contexto abaixo. Se não souber, diga honestamente
e sugira que o cliente ligue para a clínica.

CONTEXTO DA CLÍNICA:
{contexto_clinica}

HISTÓRICO DO CLIENTE:
{historico_cliente}

REGRAS:
- Linguagem coloquial e acolhedora (não seja robótico)
- Use emojis com moderação 🐾🐕🐈
- Máximo 3 parágrafos
- Se mencionar horários ou valores, confirme que podem sofrer alterações
- Nunca invente informações médicas
- Se não souber a resposta, sugira para marcar a consulta e tirar a duvida direto com o medico veterinario" 
- Ao final, pergunte se pode ajudar em mais alguma coisa
"""


async def agente_informacoes(state: AgenteState, db: AsyncSession) -> AgenteState:
    """
    Responde dúvidas sobre a clínica usando RAG.
    """
    llm = get_llm()
    mensagem = state["messages"][-1].content

    prompt = PROMPT_INFORMACOES.format(
        contexto_clinica=state.get("contexto_clinica") or "Sem contexto disponível.",
        historico_cliente=state.get("historico_cliente") or "Primeiro contato.",
    )

    resposta = await llm.ainvoke([
        SystemMessage(content=prompt),
        HumanMessage(content=mensagem)
    ])

    return {**state, "resposta_final": resposta.content}
