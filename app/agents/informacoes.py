from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgenteState
from core.llm import get_llm
from sqlalchemy.ext.asyncio import AsyncSession


PROMPT_INFORMACOES = """
Você é a recepcionista de uma clínica veterinária especializada.
Responda a dúvida do cliente de forma simpática, coloquial e precisa.

A clinica oferece os tipos de atendimento abaixo:



- Consulta Clínica Geral (clínica geral, clinica cirúrgica, ortopedia)

- Consulta Neurológica (neurologia clínica de căes e gatos, neurocirurgia avançada, neuro-oncologia);

- Retorno de consulta clínica geral (valor= pode ser concedido um retorno gratuito até 30 dias após a data da consulta)

- Retorno de consulta neurológica (valor= pode ser concedido um retorno gratuito até 60 dias após a data da consulta)


Use as informações acima e as informações do contexto abaixo. Se não souber, diga honestamente
e sugira que o cliente ligue para a clínica.

CONTEXTO DA CLÍNICA:
{contexto_clinica}

HISTÓRICO GERAL DO CLIENTE:
{historico_cliente}

HISTÓRICO RECENTE DA CONVERSA:
{historico_recente}

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

    historico_recente = "\n".join([
        f"{'Cliente' if m.type == 'human' else 'Agente'}: {m.content}"
        for m in state["messages"][-6:]
    ])

    prompt = PROMPT_INFORMACOES.format(
        contexto_clinica=state.get("contexto_clinica") or "Sem contexto disponível.",
        historico_cliente=state.get("historico_cliente") or "Primeiro contato.",
        historico_recente=historico_recente,
    )

    resposta = await llm.ainvoke([
        SystemMessage(content=prompt),
        HumanMessage(content=mensagem)
    ])

    return {**state, "resposta_final": resposta.content}
