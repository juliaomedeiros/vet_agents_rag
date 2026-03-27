import os
import uuid
import pytz
from datetime import datetime, timedelta
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from core.config import get_settings

settings = get_settings()

# Escopo necessário apenas para Calendar (Gmail é via SMTP)
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]


# ─────────────────────────────────────────────────────────────
# Autenticação Google OAuth2
# ─────────────────────────────────────────────────────────────
def get_google_credentials() -> Credentials:
    """
    Gerencia o fluxo OAuth2 do Google.
    Na primeira execução abre o browser para autorização.
    Após isso usa o token salvo automaticamente.
    """
    creds = None
    token_path = settings.google_token_json
    credentials_path = settings.google_credentials_json

    # Carrega token existente
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # Token inválido ou expirado — renova
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Primeira vez — abre browser para autorizar
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Salva token para próximas execuções
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())

    return creds


def get_calendar_service():
    """Retorna cliente autenticado do Google Calendar."""
    creds = get_google_credentials()
    return build("calendar", "v3", credentials=creds)


# ─────────────────────────────────────────────────────────────
# Verifica disponibilidade de horário
# ─────────────────────────────────────────────────────────────
def listar_horarios_disponiveis(
    calendar_id: str,
    dias: int = 30,
    duracao_minutos: int = 30,
) -> list[str]:
    """
    Retorna slots livres dos próximos `dias` dias (Seg–Sex, 14h–18h).
    Usa a API freebusy para detectar ocupações e filtra os slots livres.
    Retorna lista de strings no formato 'DD/MM/AAAA HH:MM'.
    """
    try:
        service = get_calendar_service()

        tz = pytz.timezone("America/Fortaleza")
        agora = datetime.now(tz)
        fim_periodo = agora + timedelta(days=dias)

        body = {
            "timeMin": agora.isoformat(),
            "timeMax": fim_periodo.isoformat(),
            "items": [{"id": calendar_id}],
        }
        resultado = service.freebusy().query(body=body).execute()
        periodos_ocupados = resultado["calendars"][calendar_id]["busy"]

        # Converte períodos ocupados para intervalos datetime aware (Brasília)
        ocupados = []
        for p in periodos_ocupados:
            inicio = datetime.fromisoformat(p["start"].replace("Z", "+00:00")).astimezone(tz)
            fim = datetime.fromisoformat(p["end"].replace("Z", "+00:00")).astimezone(tz)
            ocupados.append((inicio, fim))

        # Gera todos os slots possíveis e filtra os livres
        slots_livres = []
        dia_atual = agora.replace(hour=0, minute=0, second=0, microsecond=0)

        while dia_atual <= fim_periodo:
            # Apenas dias úteis (Seg=0 … Sex=4)
            if dia_atual.weekday() < 5:
                for hora in range(14, 18):
                    for minuto in (0, 30):
                        slot_inicio = dia_atual.replace(hour=hora, minute=minuto, second=0, microsecond=0)
                        slot_fim = slot_inicio + timedelta(minutes=duracao_minutos)

                        # Ignora slots já passados
                        if slot_inicio <= agora:
                            continue

                        # Verifica conflito com períodos ocupados
                        livre = all(
                            slot_fim <= ocp_inicio or slot_inicio >= ocp_fim
                            for ocp_inicio, ocp_fim in ocupados
                        )
                        if livre:
                            slots_livres.append(slot_inicio.strftime("%d/%m/%Y %H:%M"))

            dia_atual += timedelta(days=1)

        return slots_livres

    except HttpError as e:
        print(f"[Calendar] Erro ao listar horários: {e}")
        return []


def verificar_disponibilidade(
    calendar_id: str,
    data_hora: datetime,
    duracao_minutos: int = 60
) -> bool:
    """
    Verifica se o veterinário está disponível no horário solicitado.
    Retorna True se disponível, False se ocupado.
    """
    try:
        service = get_calendar_service()
        tz = pytz.timezone("America/Fortaleza")
        inicio = data_hora.astimezone(tz).isoformat()
        fim = (data_hora + timedelta(minutes=duracao_minutos)).astimezone(tz).isoformat()

        # freebusy query — mais eficiente que listar eventos
        body = {
            "timeMin": inicio,
            "timeMax": fim,
            "items": [{"id": calendar_id}],
        }

        resultado = service.freebusy().query(body=body).execute()
        ocupado = resultado["calendars"][calendar_id]["busy"]

        return len(ocupado) == 0  # True = disponível

    except HttpError as e:
        print(f"[Calendar] Erro ao verificar disponibilidade: {e}")
        return True  # em caso de erro, permite o agendamento


# ─────────────────────────────────────────────────────────────
# Cria evento no Google Calendar
# ─────────────────────────────────────────────────────────────
def criar_evento_calendario(
    calendar_id: str,
    titulo: str,
    data_hora: datetime,
    duracao_minutos: int = 30,
    descricao: str = "",
    nome_cliente: str = "",
    whatsapp_cliente: str = "",
    nome_pet: str = "",
    tipo_consulta: str = "",
    motivo: str = "",
) -> Optional[str]:
    """
    Cria um evento no Google Calendar do veterinário.
    Retorna o ID do evento criado ou None em caso de erro.
    """
    try:
        service = get_calendar_service()

        inicio = data_hora
        fim = data_hora + timedelta(minutes=duracao_minutos)

        # Descrição estruturada do evento
        descricao_completa = f"""
🐾 CONSULTA VETERINÁRIA

👤 Tutor: {nome_cliente or 'Não informado'}
📱 WhatsApp: {whatsapp_cliente or 'Não informado'}
🐶 Pet: {nome_pet or 'Não informado'}
🏥 Tipo: {tipo_consulta or 'Não informado'}
📋 Motivo: {motivo or 'Não informado'}

---
Agendado via VetAgent (WhatsApp)
        """.strip()

        evento = {
            "summary": f"🐾 {titulo}",
            "description": descricao_completa,
            "start": {
                "dateTime": inicio.isoformat(),
                "timeZone": "America/Fortaleza",
            },
            "end": {
                "dateTime": fim.isoformat(),
                "timeZone": "America/Fortaleza",
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "email", "minutes": 60},   # 1h antes
                    {"method": "popup", "minutes": 15},   # 15min antes
                ],
            },
            "colorId": "2",  # verde — agendado
        }

        resultado = service.events().insert(
            calendarId=calendar_id,
            body=evento,
            sendUpdates="all",  # envia convites por e-mail
        ).execute()

        event_id = resultado.get("id")
        print(f"[Calendar] ✅ Evento criado: {event_id}")
        return event_id

    except HttpError as e:
        print(f"[Calendar] ❌ Erro ao criar evento: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Atualiza evento (remarcação)
# ─────────────────────────────────────────────────────────────
def remarcar_evento(
    calendar_id: str,
    event_id: str,
    nova_data_hora: datetime,
    duracao_minutos: int = 30,
) -> bool:
    """
    Atualiza a data/hora de um evento existente no Calendar.
    Retorna True se sucesso, False se erro.
    """
    try:
        service = get_calendar_service()

        # Busca evento atual
        evento = service.events().get(
            calendarId=calendar_id,
            eventId=event_id
        ).execute()

        # Atualiza horários
        novo_inicio = nova_data_hora
        novo_fim = nova_data_hora + timedelta(minutes=duracao_minutos)

        evento["start"] = {
            "dateTime": novo_inicio.isoformat(),
            "timeZone": "America/Fortaleza",
        }
        evento["end"] = {
            "dateTime": novo_fim.isoformat(),
            "timeZone": "America/Fortaleza",
        }
        evento["colorId"] = "5"  # amarelo — remarcado
        evento["summary"] = evento["summary"].replace("🐾", "🔄")

        service.events().update(
            calendarId=calendar_id,
            eventId=event_id,
            body=evento,
            sendUpdates="all",
        ).execute()

        print(f"[Calendar] ✅ Evento remarcado: {event_id}")
        return True

    except HttpError as e:
        print(f"[Calendar] ❌ Erro ao remarcar evento: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Cancela evento
# ─────────────────────────────────────────────────────────────
def cancelar_evento(calendar_id: str, event_id: str) -> bool:
    """
    Cancela (deleta) um evento do Google Calendar.
    Retorna True se sucesso, False se erro.
    """
    try:
        service = get_calendar_service()

        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id,
            sendUpdates="all",
        ).execute()

        print(f"[Calendar] ✅ Evento cancelado: {event_id}")
        return True

    except HttpError as e:
        print(f"[Calendar] ❌ Erro ao cancelar evento: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Lista próximos eventos (usado pelo dashboard)
# ─────────────────────────────────────────────────────────────
def listar_proximos_eventos(
    calendar_id: str,
    max_resultados: int = 20
) -> list[dict]:
    """
    Retorna os próximos eventos do veterinário.
    Usado pelo dashboard Streamlit.
    """
    try:
        service = get_calendar_service()

        agora = datetime.utcnow().isoformat() + "Z"

        resultado = service.events().list(
            calendarId=calendar_id,
            timeMin=agora,
            maxResults=max_resultados,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        eventos = resultado.get("items", [])

        return [
            {
                "id": e.get("id"),
                "titulo": e.get("summary", ""),
                "inicio": e.get("start", {}).get("dateTime", ""),
                "fim": e.get("end", {}).get("dateTime", ""),
                "descricao": e.get("description", ""),
            }
            for e in eventos
        ]

    except HttpError as e:
        print(f"[Calendar] ❌ Erro ao listar eventos: {e}")
        return []
