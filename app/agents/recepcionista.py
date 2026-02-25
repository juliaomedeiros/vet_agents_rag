import uuid
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.state import AgenteState
from app.core.llm import get_llm
from app.db.models import Cliente, Sessao
from app.rag.memory import montar_contexto_completo
import json
import re


PROMPT_INTENCAO = """
Você é a recepcionista da Clínica Veterinária.
Analise a mensagem do cliente e identifique a INTENÇÃO.

Responda APENAS com JSON:
{
  "intencao": "SAUDACAO|INFORMACAO|AGENDAR|REMARCAR|CANCELAR|OUTRO",
  "resumo": "resumo em uma linha do que o cliente quer"
}

Definições:
- SAUDACAO: oi, olá, primeiro contato sem pedido específico
- INFORMACAO: quer saber sobre serviços, valores, horários, médicos, especialidades
- AGENDAR: quer marcar uma consulta
- REMARCAR: quer mudar data/hora de consulta existente
- CANCELAR: quer cancelar uma consulta
- OUTRO: dúvida geral que não se encaixa nas anteriores
"""


async def identificar_ou_criar_cliente(
    db: AsyncSession,
    whatsapp: str
) -> tuple[Cliente, bool]:
    """
    Busca cliente pelo WhatsApp.
    Se não existir, cria um novo.
    Retorna (cliente, é_novo).
    """
    resultado = await db.execute(
        select(Cliente).where(Cliente.whatsapp == whatsapp)
    )
    cliente = resultado.scalar_one_or_none()

    if cliente:
        # Atualiza último contato
        await db.execute(
            update(Cliente)
            .where(Cliente.id == cliente.id)
            .values(ultimo_contato=datetime.utcnow())
        )
        await db.commit()
        return cliente, False

    # Cria novo cliente
    novo_cliente = Cliente(whatsapp=whatsapp)
    db.add(novo_cliente)
    await db.commit()
    await db.refresh(novo_cliente)
    return novo_cliente, True


async def criar_sessao(
    db: AsyncSession,
    cliente_id: uuid.UUID
) -> Sessao:
    """Cria uma nova sessão de conversa para o cliente."""
    sessao = Sessao(cliente_id=cliente_id)
    db.add(sessao)
    await db.commit()
    await db.refresh(sessao)
    return sessao


async def detectar_intencao(mensagem: str) -> dict:
    """Usa o Gemini para classificar a intenção da mensagem."""
    llm = get_llm()
    resposta = await llm.ainvoke([
        SystemMessage(content=PROMPT_INTENCAO),
        HumanMessage(content=mensagem)
    ])
    try:
        conteudo = re.sub(r"```json\n?|\n?```", "", resposta.content).strip()
        return json.loads(conteudo)
    except Exception:
        return {"intencao": "OUTRO", "resumo": mensagem}


# ─────────────────────────────────────────────────────────────
# NÓ: Recepcionista
# ─────────────────────────────────────────────────────────────
async def recepcionista(state: AgenteState, db: AsyncSession) -> AgenteState:
    """
    1. Identifica/cria cliente no banco
    2. Cria ou recupera sessão ativa
    3. Carrega contexto RAG + memória do cliente
    4. Detecta intenção da mensagem
    5. Gera boas-vindas se for primeiro contato
    """
    whatsapp = state["whatsapp"]
    mensagem = state["messages"][-1].content
    llm = get_llm()

    # 1. Identifica cliente
    cliente, cliente_novo = await identificar_ou_criar_cliente(db, whatsapp)

    # 2. Cria sessão
    sessao = await criar_sessao(db, cliente.id)

    # 3. Contexto RAG + memória
    contexto = await montar_contexto_completo(db, cliente.id, mensagem)

    # 4. Detecta intenção
    resultado_intencao = await detectar_intencao(mensagem)
    intencao = resultado_intencao.get("intencao", "OUTRO")

    # 5. Resposta de boas-vindas (só se for SAUDACAO ou cliente novo)
    resposta_bv = None
    if intencao == "SAUDACAO" or cliente_novo:
        nome = cliente.nome or "Tutor"
        historico_info = (
            f"\nHistórico do cliente:\n{contexto['historico_cliente']}"
            if contexto["tem_historico"] else ""
        )

        prompt_bv = f"""
Você é a recepcionista da Clínica Veterinária, simpática e acolhedora.
Use linguagem coloquial, calorosa e profissional.
{'Este é o PRIMEIRO contato deste cliente.' if cliente_novo else f'O cliente {nome} já nos visitou antes.'}
{historico_info}

Dê boas-vindas e pergunte como pode ajudar.
Seja breve (máximo 2 linhas). Use emojis com moderação. 🐾
"""
        resposta_llm = await llm.ainvoke([
            SystemMessage(content=prompt_bv),
            HumanMessage(content=mensagem)
        ])
        resposta_bv = resposta_llm.content

    updates = {
        "cliente_id": str(cliente.id),
        "sessao_id": str(sessao.id),
        "cliente_nome": cliente.nome,
        "cliente_novo": cliente_novo,
        "intencao": intencao,
        "contexto_clinica": contexto["contexto_clinica"],
        "historico_cliente": contexto["historico_cliente"],
    }

    if resposta_bv:
        updates["resposta_final"] = resposta_bv

    return {**state, **updates}
