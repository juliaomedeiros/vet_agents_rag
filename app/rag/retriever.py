from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.llm import get_embeddings
from db.models import RagDocumento


# ─────────────────────────────────────────────────────────────
# Busca semântica nos documentos da clínica
# ─────────────────────────────────────────────────────────────
async def buscar_contexto(
    db: AsyncSession,
    pergunta: str,
    top_k: int = 5,
    threshold: float = 0.30
) -> list[dict]:
    """
    Realiza busca por similaridade de cosseno no pgvector.

    Args:
        pergunta: texto da mensagem do cliente
        top_k: número máximo de chunks retornados
        threshold: similaridade mínima (0 a 1) — descarta chunks irrelevantes

    Returns:
        Lista de dicts com conteudo e score de similaridade
    """
    embeddings_model = get_embeddings()
    vetor_pergunta = embeddings_model.embed_query(pergunta)

    # Busca vetorial com operador pgvector (<=>  = distância de cosseno)
    resultado = await db.execute(
        text("""
            SELECT
                conteudo,
                nome_arquivo,
                metadata_json,
                1 - (embedding <=> CAST(:vetor AS vector)) AS similaridade
            FROM rag_documentos
            WHERE 1 - (embedding <=> CAST(:vetor AS vector)) >= :threshold
            ORDER BY embedding <=> CAST(:vetor AS vector)
            LIMIT :top_k
        """),
        {
            "vetor": str(vetor_pergunta),
            "threshold": threshold,
            "top_k": top_k
        }
    )

    linhas = resultado.fetchall()

    return [
        {
            "conteudo": row.conteudo,
            "arquivo": row.nome_arquivo,
            "metadata": row.metadata_json,
            "similaridade": round(float(row.similaridade), 4),
        }
        for row in linhas
    ]


# ─────────────────────────────────────────────────────────────
# Formata contexto recuperado para injetar no prompt
# ─────────────────────────────────────────────────────────────
def formatar_contexto(chunks: list[dict]) -> str:
    """
    Transforma os chunks recuperados em texto estruturado
    para ser inserido no prompt do agente.
    """
    if not chunks:
        return "Nenhuma informação relevante encontrada na base de conhecimento."

    partes = []
    for i, chunk in enumerate(chunks, 1):
        partes.append(
            f"[Fonte {i} — {chunk['arquivo']} | similaridade: {chunk['similaridade']}]\n"
            f"{chunk['conteudo']}"
        )

    return "\n\n---\n\n".join(partes)


# ─────────────────────────────────────────────────────────────
# Busca completa: recupera + formata (atalho para os agentes)
# ─────────────────────────────────────────────────────────────
async def recuperar_contexto_formatado(
    db: AsyncSession,
    pergunta: str,
    top_k: int = 5,
    threshold: float = 0.30
) -> str:
    chunks = await buscar_contexto(db, pergunta, top_k, threshold)
    return formatar_contexto(chunks)
