import os
import hashlib
from pathlib import Path
from typing import Optional
from markitdown import MarkItDown
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.llm import get_embeddings
from app.db.models import RagDocumento

settings = get_settings()


# ─────────────────────────────────────────────────────────────
# Extensões suportadas pelo MarkItDown
# ─────────────────────────────────────────────────────────────
EXTENSOES_SUPORTADAS = {".txt", ".docx", ".pdf", ".md", ".xlsx", ".pptx"}


# ─────────────────────────────────────────────────────────────
# Converte arquivo para Markdown via MarkItDown
# ─────────────────────────────────────────────────────────────
def converter_para_markdown(caminho: Path) -> str:
    """
    Usa MarkItDown para converter .docx, .txt, .pdf etc. para Markdown.
    Retorna o texto convertido como string.
    """
    md = MarkItDown()
    resultado = md.convert(str(caminho))
    return resultado.text_content


# ─────────────────────────────────────────────────────────────
# Quebra o texto em chunks semânticos
# ─────────────────────────────────────────────────────────────
def criar_chunks(texto: str, nome_arquivo: str) -> list[dict]:
    """
    Divide o texto em chunks com sobreposição para preservar contexto.
    Retorna lista de dicts com conteudo e metadados.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,        # ~600 tokens — bom equilíbrio para Gemini
        chunk_overlap=150,     # sobreposição garante contexto entre chunks
        separators=["\n\n", "\n", ".", "!", "?", " "],
        length_function=len,
    )

    chunks = splitter.split_text(texto)

    return [
        {
            "conteudo": chunk.strip(),
            "chunk_index": i,
            "nome_arquivo": nome_arquivo,
            "metadata": {
                "arquivo": nome_arquivo,
                "chunk": i,
                "total_chunks": len(chunks),
                "hash": hashlib.md5(chunk.encode()).hexdigest(),
            }
        }
        for i, chunk in enumerate(chunks)
        if chunk.strip()  # ignora chunks vazios
    ]


# ─────────────────────────────────────────────────────────────
# Verifica se arquivo já foi indexado (evita reindexação)
# ─────────────────────────────────────────────────────────────
async def arquivo_ja_indexado(db: AsyncSession, nome_arquivo: str) -> bool:
    resultado = await db.execute(
        select(RagDocumento).where(
            RagDocumento.nome_arquivo == nome_arquivo
        ).limit(1)
    )
    return resultado.scalar_one_or_none() is not None


# ─────────────────────────────────────────────────────────────
# Remove indexação anterior de um arquivo
# ─────────────────────────────────────────────────────────────
async def remover_indexacao(db: AsyncSession, nome_arquivo: str) -> None:
    await db.execute(
        delete(RagDocumento).where(
            RagDocumento.nome_arquivo == nome_arquivo
        )
    )
    await db.commit()


# ─────────────────────────────────────────────────────────────
# Indexa um único arquivo no pgvector
# ─────────────────────────────────────────────────────────────
async def indexar_arquivo(
    db: AsyncSession,
    caminho: Path,
    forcar_reindexacao: bool = False
) -> dict:
    """
    Pipeline completo para um arquivo:
    1. Verifica se já indexado
    2. Converte para Markdown
    3. Divide em chunks
    4. Gera embeddings com Gemini
    5. Salva no PostgreSQL/pgvector

    Retorna dict com estatísticas da indexação.
    """
    nome_arquivo = caminho.name

    if await arquivo_ja_indexado(db, nome_arquivo):
        if not forcar_reindexacao:
            return {"arquivo": nome_arquivo, "status": "já indexado", "chunks": 0}
        await remover_indexacao(db, nome_arquivo)

    # 1. Converte para Markdown
    try:
        texto = converter_para_markdown(caminho)
    except Exception as e:
        return {"arquivo": nome_arquivo, "status": f"erro na conversão: {e}", "chunks": 0}

    if not texto.strip():
        return {"arquivo": nome_arquivo, "status": "arquivo vazio", "chunks": 0}

    # 2. Cria chunks
    chunks = criar_chunks(texto, nome_arquivo)

    if not chunks:
        return {"arquivo": nome_arquivo, "status": "sem chunks gerados", "chunks": 0}

    # 3. Gera embeddings em lote (mais eficiente)
    embeddings_model = get_embeddings()
    textos = [c["conteudo"] for c in chunks]

    try:
        embeddings = embeddings_model.embed_documents(textos)
    except Exception as e:
        return {"arquivo": nome_arquivo, "status": f"erro no embedding: {e}", "chunks": 0}

    # 4. Salva no banco
    documentos = [
        RagDocumento(
            nome_arquivo=chunk["nome_arquivo"],
            chunk_index=chunk["chunk_index"],
            conteudo=chunk["conteudo"],
            embedding=embedding,
            metadata_json=chunk["metadata"],
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]

    db.add_all(documentos)
    await db.commit()

    return {
        "arquivo": nome_arquivo,
        "status": "indexado com sucesso",
        "chunks": len(documentos)
    }


# ─────────────────────────────────────────────────────────────
# Indexa todos os arquivos da pasta RAG
# ─────────────────────────────────────────────────────────────
async def indexar_todos_arquivos(
    db: AsyncSession,
    forcar_reindexacao: bool = False
) -> list[dict]:
    """
    Varre a pasta /rag_files e indexa todos os arquivos suportados.
    Chamado no startup da aplicação ou via endpoint admin.
    """
    pasta = Path(settings.rag_files_path)

    if not pasta.exists():
        return [{"status": f"Pasta {pasta} não encontrada"}]

    arquivos = [
        f for f in pasta.iterdir()
        if f.is_file() and f.suffix.lower() in EXTENSOES_SUPORTADAS
    ]

    if not arquivos:
        return [{"status": "Nenhum arquivo suportado encontrado"}]

    resultados = []
    for arquivo in arquivos:
        resultado = await indexar_arquivo(db, arquivo, forcar_reindexacao)
        resultados.append(resultado)
        print(f"[RAG] {resultado}")

    return resultados
