from functools import lru_cache
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from core.config import get_settings

settings = get_settings()


@lru_cache()
def get_llm() -> ChatGoogleGenerativeAI:
    """
    Singleton do Gemini LLM.
    Usado pelos agentes para gerar respostas.
    """
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        temperature=0.3,        # respostas mais consistentes para atendimento
        max_output_tokens=2048,
        convert_system_message_to_human=True,  # compatibilidade Gemini
    )


@lru_cache()
def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """
    Singleton do Gemini Embeddings.
    Usado pelo RAG para indexação e busca semântica.
    """
    return GoogleGenerativeAIEmbeddings(
        model=settings.gemini_embedding_model,
        google_api_key=settings.gemini_api_key,
        task_type="retrieval_document",  # otimizado para RAG
    )
