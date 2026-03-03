import httpx
from typing import Optional
from core.config import get_settings

settings = get_settings()


# ─────────────────────────────────────────────────────────────
# Envia mensagem — roteador principal
# ─────────────────────────────────────────────────────────────
async def enviar_mensagem(numero: str, mensagem: str) -> bool:
    """
    Envia mensagem WhatsApp.
    Roteia para Evolution API ou Meta API conforme .env.
    """
    if settings.whatsapp_provider == "evolution":
        return await _enviar_evolution(numero, mensagem)
    else:
        return await _enviar_meta(numero, mensagem)


# ─────────────────────────────────────────────────────────────
# Evolution API (desenvolvimento)
# ─────────────────────────────────────────────────────────────
async def _enviar_evolution(numero: str, mensagem: str) -> bool:
    """
    Envia mensagem via Evolution API.
    O número deve estar no formato: 5583999999999 (sem + ou espaços)
    """
    url = (
        f"{settings.evolution_api_url}/message/sendText/"
        f"{settings.evolution_instance}"
    )

    headers = {
        "apikey": settings.evolution_api_key,
        "Content-Type": "application/json",
    }

    payload = {
        "number": numero,
        "options": {
            "delay": 800,           # simula digitação (ms)
            "presence": "composing" # mostra "digitando..."
        },
        "textMessage": {
            "text": mensagem
        }
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            print(f"[WhatsApp/Evolution] ✅ Mensagem enviada para {numero}")
            return True

    except httpx.HTTPStatusError as e:
        print(f"[WhatsApp/Evolution] ❌ HTTP {e.response.status_code}: {e.response.text}")
        return False
    except Exception as e:
        print(f"[WhatsApp/Evolution] ❌ Erro: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Meta Cloud API (produção)
# ─────────────────────────────────────────────────────────────
async def _enviar_meta(numero: str, mensagem: str) -> bool:
    """
    Envia mensagem via Meta WhatsApp Cloud API.
    Documentação: https://developers.facebook.com/docs/whatsapp/cloud-api
    """
    url = (
        f"https://graph.facebook.com/v19.0/"
        f"{settings.meta_phone_number_id}/messages"
    )

    headers = {
        "Authorization": f"Bearer {settings.meta_whatsapp_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": mensagem
        }
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            print(f"[WhatsApp/Meta] ✅ Mensagem enviada para {numero}")
            return True

    except httpx.HTTPStatusError as e:
        print(f"[WhatsApp/Meta] ❌ HTTP {e.response.status_code}: {e.response.text}")
        return False
    except Exception as e:
        print(f"[WhatsApp/Meta] ❌ Erro: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Parseia webhook recebido — normaliza formato
# ─────────────────────────────────────────────────────────────
def parsear_webhook_evolution(payload: dict) -> Optional[dict]:
    """
    Extrai dados relevantes do webhook da Evolution API.
    Retorna dict padronizado ou None se não for mensagem de texto.
    """
    try:
        # Evolution API v2 — estrutura do webhook
        data = payload.get("data", {})
        key  = data.get("key", {})
        msg  = data.get("message", {})

        # Ignora mensagens enviadas pelo próprio bot
        if key.get("fromMe", False):
            return None

        # Ignora se não for mensagem de texto
        texto = msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text")
        if not texto:
            return None

        numero = key.get("remoteJid", "").replace("@s.whatsapp.net", "")

        return {
            "numero": numero,
            "mensagem": texto.strip(),
            "timestamp": data.get("messageTimestamp"),
        }

    except Exception as e:
        print(f"[WhatsApp/Evolution] ❌ Erro ao parsear webhook: {e}")
        return None


def parsear_webhook_meta(payload: dict) -> Optional[dict]:
    """
    Extrai dados relevantes do webhook da Meta Cloud API.
    Retorna dict padronizado ou None se não for mensagem de texto.
    """
    try:
        entry    = payload.get("entry", [{}])[0]
        changes  = entry.get("changes", [{}])[0]
        value    = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return None

        msg    = messages[0]
        numero = msg.get("from", "")
        tipo   = msg.get("type", "")

        if tipo != "text":
            return None

        texto = msg.get("text", {}).get("body", "").strip()

        return {
            "numero": numero,
            "mensagem": texto,
            "timestamp": msg.get("timestamp"),
        }

    except Exception as e:
        print(f"[WhatsApp/Meta] ❌ Erro ao parsear webhook: {e}")
        return None


def parsear_webhook(payload: dict) -> Optional[dict]:
    """Roteador: parseia webhook conforme o provider configurado."""
    if settings.whatsapp_provider == "evolution":
        return parsear_webhook_evolution(payload)
    return parsear_webhook_meta(payload)
