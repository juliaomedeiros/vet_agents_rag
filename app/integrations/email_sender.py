import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from typing import Optional

from core.config import get_settings

settings = get_settings()


# ─────────────────────────────────────────────────────────────
# Envia e-mail via SMTP
# ─────────────────────────────────────────────────────────────
def enviar_email(
    destinatario: str,
    assunto: str,
    corpo_html: str,
    corpo_texto: str = "",
) -> bool:
    """
    Envia e-mail via SMTP (Gmail).
    Retorna True se enviado com sucesso.
    """
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"]    = settings.smtp_user
        msg["To"]      = destinatario

        # Fallback texto puro
        if corpo_texto:
            msg.attach(MIMEText(corpo_texto, "plain", "utf-8"))

        # HTML principal
        msg.attach(MIMEText(corpo_html, "html", "utf-8"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as servidor:
            servidor.ehlo()
            servidor.starttls()
            servidor.login(settings.smtp_user, settings.smtp_password)
            servidor.sendmail(
                settings.smtp_user,
                destinatario,
                msg.as_string()
            )

        print(f"[Email] ✅ Enviado para {destinatario}: {assunto}")
        return True

    except Exception as e:
        print(f"[Email] ❌ Erro ao enviar: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Templates de e-mail
# ─────────────────────────────────────────────────────────────
def _template_base(titulo: str, cor: str, conteudo: str) -> str:
    """Template HTML base para todos os e-mails."""
    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }}
    .container {{ max-width: 600px; margin: 0 auto; background: white;
                  border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
    .header {{ background: {cor}; color: white; padding: 24px; text-align: center; }}
    .header h1 {{ margin: 0; font-size: 22px; }}
    .body {{ padding: 28px; color: #333; line-height: 1.6; }}
    .info-box {{ background: #f8f9fa; border-left: 4px solid {cor};
                 padding: 16px; border-radius: 4px; margin: 16px 0; }}
    .info-row {{ display: flex; margin: 8px 0; }}
    .info-label {{ font-weight: bold; min-width: 140px; color: #555; }}
    .footer {{ background: #f8f9fa; padding: 16px; text-align: center;
               font-size: 12px; color: #999; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header"><h1>🐾 {titulo}</h1></div>
    <div class="body">{conteudo}</div>
    <div class="footer">VetAgent — Sistema de Atendimento Veterinário Automatizado</div>
  </div>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────
# E-mail: Nova consulta agendada
# ─────────────────────────────────────────────────────────────
def notificar_agendamento(
    email_veterinario: str,
    nome_veterinario: str,
    nome_cliente: str,
    whatsapp_cliente: str,
    nome_pet: str,
    especie_pet: str,
    tipo_consulta: str,
    data_hora: datetime,
    motivo: str,
    consulta_id: str,
) -> bool:
    assunto = f"📅 Nova Consulta Agendada — {nome_pet} ({data_hora.strftime('%d/%m/%Y às %H:%M')})"

    conteudo = f"""
    <p>Olá, <strong>Dr(a). {nome_veterinario}</strong>! 👋</p>
    <p>Uma nova consulta foi agendada via WhatsApp pelo VetAgent.</p>

    <div class="info-box">
      <div class="info-row">
        <span class="info-label">👤 Tutor:</span>
        <span>{nome_cliente or 'Não informado'}</span>
      </div>
      <div class="info-row">
        <span class="info-label">📱 WhatsApp:</span>
        <span>{whatsapp_cliente}</span>
      </div>
      <div class="info-row">
        <span class="info-label">🐶 Pet:</span>
        <span>{nome_pet or 'Não informado'} ({especie_pet or 'espécie não informada'})</span>
      </div>
      <div class="info-row">
        <span class="info-label">🏥 Tipo de Consulta:</span>
        <span>{tipo_consulta}</span>
      </div>
      <div class="info-row">
        <span class="info-label">📅 Data e Hora:</span>
        <span><strong>{data_hora.strftime('%d/%m/%Y às %H:%M')}</strong></span>
      </div>
      <div class="info-row">
        <span class="info-label">📋 Motivo:</span>
        <span>{motivo or 'Não informado'}</span>
      </div>
      <div class="info-row">
        <span class="info-label">🔖 ID da Consulta:</span>
        <span style="font-size:11px; color:#999;">{consulta_id}</span>
      </div>
    </div>

    <p>O evento já foi criado no seu <strong>Google Agenda</strong>. ✅</p>
    <p>Até breve! 🐾</p>
    """

    html = _template_base("Nova Consulta Agendada", "#2E7D32", conteudo)
    return enviar_email(email_veterinario, assunto, html)


# ─────────────────────────────────────────────────────────────
# E-mail: Consulta remarcada
# ─────────────────────────────────────────────────────────────
def notificar_remarcacao(
    email_veterinario: str,
    nome_veterinario: str,
    nome_cliente: str,
    whatsapp_cliente: str,
    nome_pet: str,
    tipo_consulta: str,
    data_hora_antiga: datetime,
    data_hora_nova: datetime,
    consulta_id: str,
) -> bool:
    assunto = f"🔄 Consulta Remarcada — {nome_pet} ({data_hora_nova.strftime('%d/%m/%Y às %H:%M')})"

    conteudo = f"""
    <p>Olá, <strong>Dr(a). {nome_veterinario}</strong>! 👋</p>
    <p>Uma consulta foi <strong>remarcada</strong> pelo cliente via WhatsApp.</p>

    <div class="info-box">
      <div class="info-row">
        <span class="info-label">👤 Tutor:</span>
        <span>{nome_cliente or 'Não informado'}</span>
      </div>
      <div class="info-row">
        <span class="info-label">📱 WhatsApp:</span>
        <span>{whatsapp_cliente}</span>
      </div>
      <div class="info-row">
        <span class="info-label">🐶 Pet:</span>
        <span>{nome_pet or 'Não informado'}</span>
      </div>
      <div class="info-row">
        <span class="info-label">🏥 Tipo:</span>
        <span>{tipo_consulta}</span>
      </div>
      <div class="info-row">
        <span class="info-label">❌ Data Anterior:</span>
        <span style="text-decoration:line-through; color:#e53935;">
          {data_hora_antiga.strftime('%d/%m/%Y às %H:%M')}
        </span>
      </div>
      <div class="info-row">
        <span class="info-label">✅ Nova Data:</span>
        <span style="color:#2E7D32; font-weight:bold;">
          {data_hora_nova.strftime('%d/%m/%Y às %H:%M')}
        </span>
      </div>
      <div class="info-row">
        <span class="info-label">🔖 ID da Consulta:</span>
        <span style="font-size:11px; color:#999;">{consulta_id}</span>
      </div>
    </div>

    <p>O evento no <strong>Google Agenda</strong> já foi atualizado. ✅</p>
    """

    html = _template_base("Consulta Remarcada", "#F57C00", conteudo)
    return enviar_email(email_veterinario, assunto, html)


# ─────────────────────────────────────────────────────────────
# E-mail: Consulta cancelada
# ─────────────────────────────────────────────────────────────
def notificar_cancelamento(
    email_veterinario: str,
    nome_veterinario: str,
    nome_cliente: str,
    whatsapp_cliente: str,
    nome_pet: str,
    tipo_consulta: str,
    data_hora: datetime,
    consulta_id: str,
) -> bool:
    assunto = f"❌ Consulta Cancelada — {nome_pet} ({data_hora.strftime('%d/%m/%Y às %H:%M')})"

    conteudo = f"""
    <p>Olá, <strong>Dr(a). {nome_veterinario}</strong>! 👋</p>
    <p>Uma consulta foi <strong>cancelada</strong> pelo cliente via WhatsApp.</p>

    <div class="info-box">
      <div class="info-row">
        <span class="info-label">👤 Tutor:</span>
        <span>{nome_cliente or 'Não informado'}</span>
      </div>
      <div class="info-row">
        <span class="info-label">📱 WhatsApp:</span>
        <span>{whatsapp_cliente}</span>
      </div>
      <div class="info-row">
        <span class="info-label">🐶 Pet:</span>
        <span>{nome_pet or 'Não informado'}</span>
      </div>
      <div class="info-row">
        <span class="info-label">🏥 Tipo:</span>
        <span>{tipo_consulta}</span>
      </div>
      <div class="info-row">
        <span class="info-label">📅 Data Cancelada:</span>
        <span style="color:#e53935;">
          {data_hora.strftime('%d/%m/%Y às %H:%M')}
        </span>
      </div>
      <div class="info-row">
        <span class="info-label">🔖 ID da Consulta:</span>
        <span style="font-size:11px; color:#999;">{consulta_id}</span>
      </div>
    </div>

    <p>O evento foi <strong>removido do Google Agenda</strong>. ✅</p>
    <p>O horário já está disponível para novos agendamentos.</p>
    """

    html = _template_base("Consulta Cancelada", "#C62828", conteudo)
    return enviar_email(email_veterinario, assunto, html)
