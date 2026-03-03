import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db.models import Consulta, StatusConsulta
from app.core.config import get_settings
from app.core.langsmith import configurar_langsmith
from app.core.llm import get_llm
from app.db.session import AsyncSessionLocal, get_db
from app.agents.graph import processar_mensagem
from app.integrations.whatsapp import parsear_webhook, enviar_mensagem
from app.rag.ingestor import indexar_todos_arquivos
from app.integrations.google_calendar import listar_proximos_eventos


settings = get_settings()

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Modelos Pydantic para webhooks
# ─────────────────────────────────────────────────────────────
class WebhookPayload(BaseModel):
    """Payload genérico para webhook WhatsApp."""
    pass


class StatusResponse(BaseModel):
    """Resposta de status do sistema."""
    status: str = "OK"
    version: str = "1.0.0"
    gemini_model: str = settings.gemini_model
    whatsapp_provider: str = settings.whatsapp_provider
    app_env: str = settings.app_env


# ─────────────────────────────────────────────────────────────
# Startup/Shutdown
# ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Executa ao iniciar e parar a aplicação.
    - Configura LangSmith
    - Indexa arquivos RAG
    """
    # Startup
    logger.info("🚀 Iniciando VetAgent...")
    configurar_langsmith()

    # Indexa RAG (apenas em desenvolvimento)
    if settings.app_env == "development":
        logger.info("📚 Indexando arquivos RAG...")
        async with AsyncSessionLocal() as db:
            resultados = await indexar_todos_arquivos(db)
            logger.info(f"RAG indexado: {resultados}")

    yield

    # Shutdown
    logger.info("🛑 VetAgent encerrado.")


# ─────────────────────────────────────────────────────────────
# FastAPI App principal
# ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="VetAgent 🐾",
    description="Assistente de atendimento veterinário via WhatsApp com IA",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS para dashboard e testes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────
# Endpoint: Health Check
# ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """Endpoint de saúde do sistema."""
    return {"status": "healthy", "service": "vet-agent"}


# ─────────────────────────────────────────────────────────────
# Endpoint: Status detalhado
# ─────────────────────────────────────────────────────────────
@app.get("/status", response_model=StatusResponse)
async def status():
    """Status completo do sistema."""
    return StatusResponse()


# ─────────────────────────────────────────────────────────────
# Webhook WhatsApp (POST)
# ─────────────────────────────────────────────────────────────
@app.post("/webhook/whatsapp")
async def webhook_whatsapp(
    payload: WebhookPayload,
    db: AsyncSessionLocal = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    Webhook principal — recebe mensagens do WhatsApp e responde automaticamente.
    
    Evolution API: POST http://localhost:8000/webhook/whatsapp
    Meta API: configure webhook apontando para esta URL
    """
    try:
        # Parseia o webhook (Evolution ou Meta)
        webhook_data = parsear_webhook(payload.dict())
        
        if not webhook_data:
            logger.info("[Webhook] Mensagem ignorada (não é texto)")
            return {"status": "ignored"}

        numero = webhook_data["numero"]
        mensagem = webhook_data["mensagem"]

        logger.info(f"[WhatsApp] Mensagem de {numero}: {mensagem[:50]}...")

        # Processa com os agentes LangGraph
        resposta = await processar_mensagem(numero, mensagem, db)

        if resposta:
            # Envia resposta em background (não bloqueia o webhook)
            background_tasks.add_task(enviar_mensagem, numero, resposta)
            logger.info(f"[WhatsApp] Resposta enviada para {numero}")
            return {"status": "processed", "resposta": resposta[:100] + "..."}

        return {"status": "no_response"}

    except Exception as e:
        logger.error(f"[Webhook] Erro: {e}")
        return HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────
# Webhook WhatsApp (GET) — Verificação Meta
# ─────────────────────────────────────────────────────────────
@app.get("/webhook/whatsapp")
async def webhook_verificacao(
    hub_mode: Optional[str] = None,
    hub_challenge: Optional[str] = None,
    hub_verify_token: Optional[str] = None
):
    """
    Verificação do webhook da Meta WhatsApp Cloud API.
    
    GET /webhook/whatsapp?hub_mode=subscribe&hub_challenge=abc123&hub_verify_token=xyz
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        logger.info("[Meta] Webhook verificado com sucesso!")
        return hub_challenge
    
    raise HTTPException(status_code=403, detail="Token de verificação inválido")


# ─────────────────────────────────────────────────────────────
# Endpoint Admin: Reindexar RAG
# ─────────────────────────────────────────────────────────────
@app.post("/admin/rag/reindexar")
async def admin_reindexar_rag(
    forcar: bool = True,
    db: AsyncSessionLocal = Depends(get_db)
):
    """
    Reindexa todos os arquivos da pasta rag_files/.
    Útil quando novos arquivos são adicionados ou alterados.
    """
    resultados = await indexar_todos_arquivos(db, forcar_reindexacao=forcar)
    return {
        "status": "success",
        "resultados": resultados,
        "total_indexados": len([r for r in resultados if r.get("status") == "indexado com sucesso"])
    }


# ─────────────────────────────────────────────────────────────
# Endpoint Admin: Próximos eventos (para dashboard)
# ─────────────────────────────────────────────────────────────
@app.get("/admin/calendario/proximos")
async def admin_proximos_eventos(
    calendar_id: str = "primary",
    max_resultados: int = 20
):
    """
    Lista os próximos eventos do Google Calendar.
    Usado pelo dashboard Streamlit.
    """
    eventos = listar_proximos_eventos(calendar_id, max_resultados)
    return {"eventos": eventos}


# ─────────────────────────────────────────────────────────────
# Endpoint Admin: Status das consultas
# ─────────────────────────────────────────────────────────────
@app.get("/admin/consultas")
async def admin_listar_consultas(
    dias_futuro: int = 7,
    db: AsyncSessionLocal = Depends(get_db)
):
    """
    Lista consultas agendadas para os próximos X dias.
    """
    from sqlalchemy import func, and_
    from datetime import datetime, timedelta
    from app.db.models import Consulta, StatusConsulta

    ate_data = datetime.utcnow() + timedelta(days=dias_futuro)

    resultado = await db.execute(
        select(Consulta)
        .where(
            and_(
                Consulta.data_hora >= datetime.utcnow(),
                Consulta.data_hora <= ate_data,
                Consulta.status.in_([StatusConsulta.agendada, StatusConsulta.confirmada])
            )
        )
        .order_by(Consulta.data_hora)
    )

    consultas = resultado.scalars().all()
    return {
        "total": len(consultas),
        "consultas": [
            {
                "id": str(c.id),
                "cliente_whatsapp": c.cliente.whatsapp,
                "pet": c.pet.nome if c.pet else "Não informado",
                "tipo": c.tipo.value,
                "data_hora": c.data_hora.isoformat(),
                "google_event_id": c.google_event_id,
            }
            for c in consultas
        ]
    }


# ─────────────────────────────────────────────────────────────
# Endpoint: Teste de mensagem (para debug)
# ─────────────────────────────────────────────────────────────
@app.post("/test/mensagem")
async def test_mensagem(
    numero: str,
    mensagem: str,
    db: AsyncSessionLocal = Depends(get_db)
):
    """
    Endpoint de teste — simula mensagem recebida do WhatsApp.
    Útil para testar o agente sem configurar webhook.
    """
    resposta = await processar_mensagem(numero, mensagem, db)
    return {
        "input": {"numero": numero, "mensagem": mensagem},
        "output": resposta
    }


# ─────────────────────────────────────────────────────────────
# Docs e OpenAPI
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.app_env == "development",
        log_level="info"
    )
