import os
from app.core.config import get_settings

settings = get_settings()


def configurar_langsmith() -> None:
    """
    Configura as variáveis de ambiente do LangSmith.
    Chamado uma vez no startup da aplicação (main.py).
    O LangSmith intercepta automaticamente todas as
    chamadas LangChain/LangGraph após essa configuração.
    """
    if not settings.langchain_api_key:
        print("[LangSmith] ⚠️  API Key não configurada — tracing desativado")
        return

    os.environ["LANGCHAIN_TRACING_V2"]  = str(settings.langchain_tracing_v2).lower()
    os.environ["LANGCHAIN_ENDPOINT"]    = settings.langchain_endpoint
    os.environ["LANGCHAIN_API_KEY"]     = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"]     = settings.langchain_project

    print(f"[LangSmith] ✅ Tracing ativo — projeto: {settings.langchain_project}")
