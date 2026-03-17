import uuid
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import SystemMessage, HumanMessage

from agents.state import AgenteState
from core.llm import get_llm
from db.models import Cliente, Sessao
from rag.memory import montar_contexto_completo
from skills.loader import load_skill
import json
import re


# ─────────────────────────────────────────────────────────────
# Carrega o skill do recepcionista uma única vez (cache em memória)
# ─────────────────────────────────────────────────────────────
_SKILL = load_skill("vet-clinic-receptionist")

PROMPT_INTENCAO = f"""{_SKILL["persona"]}

---

Sua tarefa neste momento é analisar a mensagem do cliente e identificar a INTENÇÃO.

Responda APENAS com JSON:
{{
  "intencao": "SAUDACAO|INFORMACAO|AGENDAR|REMARCAR|CANCELAR|EMERGENCIA|OUTRO",
  "resumo": "resumo em uma linha do que o cliente quer"
}}

Definições:
- SAUDACAO: oi, olá, primeiro contato sem pedido específico
- INFORMACAO: quer saber sobre serviços, valores, horários, médicos, especialidades
- AGENDAR: quer marcar uma consulta
- REMARCAR: quer mudar data/hora de consulta existente
- CANCELAR: quer cancelar uma consulta
- EMERGENCIA: relato de situação grave (atropelamento, convulsão, sangramento, falta de ar)
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


async def obter_ou_criar_sessao_ativa(
    db: AsyncSession,
    cliente_id: uuid.UUID
) -> tuple[Sessao, bool]:
    """Cria uma nova sessão ou recupera sessão ativa para o cliente."""
    resultado = await db.execute(
        select(Sessao)
        .where(Sessao.cliente_id == cliente_id, Sessao.ativa == True)
        .order_by(Sessao.iniciada_em.desc())
        .limit(1)
    )
    sessao = resultado.scalar_one_or_none()
    if sessao:
        return sessao, False

    sessao = Sessao(cliente_id=cliente_id)
    db.add(sessao)
    await db.commit()
    await db.refresh(sessao)
    return sessao, True


async def detectar_intencao(mensagem: str) -> dict:
    """Usa o Gemini para classificar a intenção da mensagem (guiado pelo skill)."""
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
    4. Detecta intenção da mensagem (usando persona do skill)
    5. Gera boas-vindas (se for primeiro contato/saudação) usando o skill
    6. Detecta emergência e responde imediatamente se necessário
    """
    whatsapp = state["whatsapp"]
    mensagem = state["messages"][-1].content
    llm = get_llm()

    # 1. Identifica cliente
    cliente, cliente_novo = await identificar_ou_criar_cliente(db, whatsapp)

    # 2. Cria ou recupera sessão
    sessao, sessao_nova = await obter_ou_criar_sessao_ativa(db, cliente.id)

    # 3. Contexto RAG + memória
    contexto = await montar_contexto_completo(db, cliente.id, mensagem)

    # 4. Detecta intenção
    resultado_intencao = await detectar_intencao(mensagem)
    intencao = resultado_intencao.get("intencao", "OUTRO")

    # 5. Resposta imediata para EMERGENCIA (skill define essa regra)
    if intencao == "EMERGENCIA":
        resposta_emergencia = (
            "🚨 *Atenção! Isso parece uma emergência!*\n\n"
            "Por favor, dirija-se *imediatamente* à nossa clínica — "
            "temos atendimento de urgência disponível *24 horas*. "
            "Não é necessário agendar.\n\n"
            "📍 Rua dos Animais Felizes, 123 — Jardim Pet, São Paulo.\n\n"
            "Se precisar de orientação enquanto vem até aqui, estou aqui! 🐾"
        )
        return {
            **state,
            "cliente_id": str(cliente.id),
            "sessao_id": str(sessao.id),
            "cliente_nome": cliente.nome,
            "cliente_novo": cliente_novo,
            "intencao": intencao,
            "contexto_clinica": contexto["contexto_clinica"],
            "historico_cliente": contexto["historico_cliente"],
            "resposta_final": resposta_emergencia,
        }

    # 6. Resposta de boas-vindas usando o template do skill
    resposta_bv = None
    if sessao_nova and (intencao == "SAUDACAO" or cliente_novo):
        nome = cliente.nome or "Tutor"
        historico_info = (
            f"\nHistórico do cliente:\n{contexto['historico_cliente']}"
            if contexto["tem_historico"] else ""
        )

        # Usa a persona do skill + template de boas-vindas do assets/
        welcome_template = _SKILL["assets"].get("welcome_template", "")

        prompt_bv = f"""{_SKILL["persona"]}

---

## Contexto do Atendimento

{'Este é o PRIMEIRO contato deste cliente.' if cliente_novo else f'O cliente {nome} já nos visitou antes.'}
{historico_info}

## Contexto da Clínica (RAG)
{contexto["contexto_clinica"] or "Sem contexto adicional disponível."}

## Template de Boas-Vindas a Seguir
{welcome_template}

## Instruções
- Adapte o template acima ao contexto do cliente.
- Use linguagem coloquial, calorosa e profissional.
- Seja extremamente breve e conciso (não gaste tokens desnecessariamente).
- SEMPRE termine a frase e NUNCA deixe frases incompletas ou cortadas.
- Use emojis com moderação. 🐾
- Nunca invente informações que não estão no contexto.
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
