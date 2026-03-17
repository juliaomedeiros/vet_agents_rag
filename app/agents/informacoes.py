from langchain_core.messages import SystemMessage, HumanMessage
from agents.state import AgenteState
from core.llm import get_llm
from sqlalchemy.ext.asyncio import AsyncSession
from skills.loader import load_skill


# ─────────────────────────────────────────────────────────────
# Carrega o skill para usar como base de persona e referências
# ─────────────────────────────────────────────────────────────
_SKILL = load_skill("vet-clinic-receptionist")

# Referências do skill usadas para enriquecer as respostas
_CLINIC_INFO = _SKILL["references"].get("clinic_info", "")
_SPECIALTIES = _SKILL["references"].get("specialties", "")


PROMPT_INFORMACOES = f"""{_SKILL["persona"]}

---

## Referência: Informações da Clínica
{_CLINIC_INFO}

## Referência: Especialidades e Corpo Clínico
{_SPECIALTIES}

---

## Contexto Adicional (Base de Conhecimento RAG da Clínica)
{{contexto_clinica}}

## Histórico do Cliente
{{historico_cliente}}

## Histórico Recente da Conversa
{{historico_recente}}

## Instruções para esta Resposta
- Responda a dúvida do cliente de forma simpática, coloquial e muito precisa.
- Use as informações das referências acima e do contexto RAG.
- Se a dúvida for sobre sintomas ou saúde do animal, direcione para a especialidade certa conforme `Especialidades e Corpo Clínico`, mas JAMAIS dê diagnóstico.
- Se não souber, diga honestamente e sugira que o cliente ligue ou passe pela clínica.
- Linguagem coloquial e acolhedora (não seja robótico).
- Use emojis com moderação 🐾🐕🐈
- Seja direto e muito conciso (não gaste tokens desnecessariamente).
- SEMPRE termine a frase e NUNCA deixe falas incompletas ou cortadas no final.
- Máximo 2 parágrafos.
- Se mencionar horários ou valores, confirme que podem sofrer alterações.
- Nunca invente informações médicas.
- Ao final, pergunte se pode ajudar em mais alguma coisa.
"""


async def agente_informacoes(state: AgenteState, db: AsyncSession) -> AgenteState:
    """
    Responde dúvidas sobre a clínica usando:
    - Persona e referências do skill (clinic_info, specialties)
    - Contexto RAG da clínica
    - Histórico do cliente (memória vetorial)
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
