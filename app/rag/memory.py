import uuid
from datetime import datetime
from sqlalchemy import text, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import get_embeddings, get_llm
from app.db.models import MemoriaCliente, Sessao, Mensagem, OrigemMensagem
from langchain_core.messages import HumanMessage, SystemMessage


# ─────────────────────────────────────────────────────────────
# Salva memória vetorial de uma sessão encerrada
# ─────────────────────────────────────────────────────────────
async def salvar_memoria_sessao(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    sessao_id: uuid.UUID,
) -> None:
    """
    Ao final de uma sessão, gera um resumo semântico da conversa
    e armazena como vetor na tabela memoria_clientes.
    Isso permite que sessões futuras recuperem histórico relevante.
    """
    # Recupera mensagens da sessão
    resultado = await db.execute(
        select(Mensagem)
        .where(Mensagem.sessao_id == sessao_id)
        .order_by(Mensagem.criado_em)
    )
    mensagens = resultado.scalars().all()

    if not mensagens:
        return

    # Monta histórico para o LLM resumir
    historico = "\n".join([
        f"{'Cliente' if m.origem == OrigemMensagem.cliente else 'Agente'}: {m.conteudo}"
        for m in mensagens
    ])

    # Gera resumo com Gemini
    llm = get_llm()
    resposta = await llm.ainvoke([
        SystemMessage(content=(
            "Você é um assistente que resume conversas de atendimento veterinário. "
            "Crie um resumo CONCISO (máximo 200 palavras) destacando: "
            "nome do cliente e pet, motivo do contato, consultas agendadas/canceladas, "
            "informações relevantes mencionadas e pendências. "
            "Seja objetivo e use linguagem profissional."
        )),
        HumanMessage(content=f"Resumo esta conversa:\n\n{historico}")
    ])

    resumo = resposta.content

    # Gera embedding do resumo
    embeddings_model = get_embeddings()
    vetor = embeddings_model.embed_query(resumo)

    # Salva no banco
    memoria = MemoriaCliente(
        cliente_id=cliente_id,
        sessao_id=sessao_id,
        resumo=resumo,
        embedding=vetor,
    )
    db.add(memoria)

    # Marca sessão como encerrada
    await db.execute(
        update(Sessao)
        .where(Sessao.id == sessao_id)
        .values(ativa=False, encerrada_em=datetime.utcnow())
    )

    await db.commit()


# ─────────────────────────────────────────────────────────────
# Recupera memórias relevantes de um cliente
# ─────────────────────────────────────────────────────────────
async def recuperar_memoria_cliente(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    pergunta: str,
    top_k: int = 3,
    threshold: float = 0.70
) -> list[dict]:
    """
    Busca memórias anteriores do cliente relevantes para a conversa atual.
    Usa similaridade semântica entre a pergunta atual e os resumos anteriores.
    """
    embeddings_model = get_embeddings()
    vetor = embeddings_model.embed_query(pergunta)

    resultado = await db.execute(
        text("""
            SELECT
                resumo,
                criado_em,
                1 - (embedding <=> CAST(:vetor AS vector)) AS similaridade
            FROM memoria_clientes
            WHERE
                cliente_id = :cliente_id
                AND 1 - (embedding <=> CAST(:vetor AS vector)) >= :threshold
            ORDER BY embedding <=> CAST(:vetor AS vector)
            LIMIT :top_k
        """),
        {
            "vetor": str(vetor),
            "cliente_id": str(cliente_id),
            "threshold": threshold,
            "top_k": top_k,
        }
    )

    linhas = resultado.fetchall()

    return [
        {
            "resumo": row.resumo,
            "data": row.criado_em.strftime("%d/%m/%Y"),
            "similaridade": round(float(row.similaridade), 4),
        }
        for row in linhas
    ]


# ─────────────────────────────────────────────────────────────
# Formata memórias para injetar no prompt
# ─────────────────────────────────────────────────────────────
def formatar_memorias(memorias: list[dict]) -> str:
    if not memorias:
        return ""

    partes = ["📋 *Histórico anterior deste cliente:*\n"]
    for m in memorias:
        partes.append(
            f"[{m['data']} | relevância: {m['similaridade']}]\n{m['resumo']}"
        )

    return "\n\n".join(partes)


# ─────────────────────────────────────────────────────────────
# Contexto completo: RAG docs + memória do cliente
# ─────────────────────────────────────────────────────────────
async def montar_contexto_completo(
    db: AsyncSession,
    cliente_id: uuid.UUID,
    pergunta: str,
) -> dict:
    """
    Agrega contexto da base de conhecimento (RAG)
    e histórico do cliente (memória vetorial).
    Retorna dict pronto para injetar no prompt dos agentes.
    """
    from app.rag.retriever import buscar_contexto, formatar_contexto

    # Busca em paralelo para melhorar performance
    import asyncio
    chunks_task = buscar_contexto(db, pergunta)
    memoria_task = recuperar_memoria_cliente(db, cliente_id, pergunta)

    chunks, memorias = await asyncio.gather(chunks_task, memoria_task)

    return {
        "contexto_clinica": formatar_contexto(chunks),
        "historico_cliente": formatar_memorias(memorias),
        "tem_historico": len(memorias) > 0,
        "tem_contexto": len(chunks) > 0,
    }
