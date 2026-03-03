import json
import re
import uuid
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.state import AgenteState
from app.core.llm import get_llm
from app.db.models import Consulta, Veterinario, TipoConsulta, StatusConsulta

from app.integrations.google_calendar import (
    criar_evento_calendario,
    remarcar_evento,
    cancelar_evento,
)
from app.integrations.email_sender import (
    notificar_agendamento,
    notificar_remarcacao,
    notificar_cancelamento,
)

PROMPT_COLETAR_DADOS = """
Você é a recepcionista de uma clínica veterinária coletando dados para agendamento.
Analise a conversa e extraia as informações disponíveis.

Responda APENAS com JSON:
{{
  "nome_tutor": "nome ou null",
  "nome_pet": "nome do animal ou null",
  "especie": "cão/gato/outro ou null",
  "tipo_consulta": "clinica_geral|clinica_cirurgica|ortopedia|neurologia_clinica|neurocirurgia|neuro_oncologia ou null",
  "data": "DD/MM/AAAA ou null",
  "hora": "HH:MM ou null",
  "motivo": "motivo da consulta ou null",
  "dados_completos": true/false,
  "proximo_passo": "o que perguntar ao cliente para completar os dados"
}}

Conversa atual:
{historico}

Contexto da clínica:
{contexto}
"""

PROMPT_CONFIRMAR = """
Você é a recepcionista de uma clínica veterinária.
Com base nos dados coletados, gere uma mensagem de CONFIRMAÇÃO de agendamento
para enviar ao cliente. Use linguagem coloquial e acolhedora.

Dados da consulta:
{dados}

Inclua: nome do pet, tipo de consulta, data, hora e nome do veterinário.
Informe que um e-mail foi enviado ao veterinário.
Finalize perguntando se precisa de mais alguma coisa. 🐾
"""

PROMPT_REMARCAR = """
Você é a recepcionista de uma clínica veterinária.
O cliente quer REMARCAR uma consulta.

Consultas agendadas do cliente:
{consultas}

Mensagem do cliente: {mensagem}

Extraia a nova data/hora desejada e qual consulta remarca, leve em consideraçao o horario que a clinica funciona e os dias da semana que ela esta aberta.
Responda APENAS com JSON:
{{
  "consulta_id": "UUID da consulta a remarcar ou null",
  "nova_data": "DD/MM/AAAA ou null",
  "nova_hora": "HH:MM ou null",
  "dados_completos": true/false,
  "proximo_passo": "o que perguntar se faltar dados"
}}
"""


async def buscar_consultas_cliente(
    db: AsyncSession,
    cliente_id: str
) -> list[Consulta]:
    """Busca consultas ativas (agendadas/confirmadas) do cliente."""
    resultado = await db.execute(
        select(Consulta).where(
            Consulta.cliente_id == uuid.UUID(cliente_id),
            Consulta.status.in_([StatusConsulta.agendada, StatusConsulta.confirmada])
        ).order_by(Consulta.data_hora)
    )
    return resultado.scalars().all()


async def buscar_veterinario_principal(db: AsyncSession) -> Veterinario:
    """Retorna o primeiro veterinário ativo."""
    resultado = await db.execute(
        select(Veterinario).where(Veterinario.ativo == True).limit(1)
    )
    return resultado.scalar_one_or_none()


# ─────────────────────────────────────────────────────────────
# NÓ: Agendamento
# ─────────────────────────────────────────────────────────────
async def agente_agendamento(state: AgenteState, db: AsyncSession) -> AgenteState:
    """
    Gerencia o fluxo de agendar, remarcar ou cancelar consultas.
    Coleta dados progressivamente via conversa.
    """
    llm = get_llm()
    intencao = state.get("intencao", "AGENDAR")
    mensagem = state["messages"][-1].content
    cliente_id = state.get("cliente_id")

    # ── CANCELAR ────────────────────────────────────────────
    if intencao == "CANCELAR":
        consultas = await buscar_consultas_cliente(db, cliente_id)

        if not consultas:
            return {
                **state,
                "resposta_final": (
                    "Não estou conseguindo encontrar nenhuma consulta agendada pra você no momento. 🤔 "
                    "Posso marcar uma nova consulta para você?"
                )
            }

        lista = "\n".join([
            f"- {c.tipo.value} em {c.data_hora.strftime('%d/%m/%Y às %H:%M')}"
            for c in consultas
        ])

        # Confirma cancelamento e atualiza banco
        await db.execute(
            update(Consulta)
            .where(Consulta.id == consultas[0].id)
            .values(status=StatusConsulta.cancelada, atualizado_em=datetime.utcnow())
        )
        await db.commit()

        return {
            **state,
            "resposta_final": (
                f"Tudo certo! 😊 Sua consulta foi cancelada.\n\n"
                f"Se quiser agendar uma nova consulta, é só entrar em contato conosco! "
                f"Cuide bem do seu pet! 🐾"
            ),
            "consulta_id": str(consultas[0].id),
        }

    # ── REMARCAR ────────────────────────────────────────────
    if intencao == "REMARCAR":
        consultas = await buscar_consultas_cliente(db, cliente_id)

        if not consultas:
            return {
                **state,
                "resposta_final": (
                    "Não encontrei consultas agendadas para remarcar. 😅 "
                    "Quer agendar uma nova consulta?"
                )
            }

        lista_json = [
            {
                "id": str(c.id),
                "tipo": c.tipo.value,
                "data": c.data_hora.strftime("%d/%m/%Y"),
                "hora": c.data_hora.strftime("%H:%M"),
            }
            for c in consultas
        ]

        resposta = await llm.ainvoke([
            SystemMessage(content=PROMPT_REMARCAR.format(
                consultas=json.dumps(lista_json, ensure_ascii=False),
                mensagem=mensagem
            )),
            HumanMessage(content=mensagem)
        ])

        try:
            conteudo = re.sub(r"```json\n?|\n?```", "", resposta.content).strip()
            dados = json.loads(conteudo)
        except Exception:
            dados = {"dados_completos": False, "proximo_passo": "Qual data prefere?"}

        if not dados.get("dados_completos"):
            return {
                **state,
                "resposta_final": dados.get("proximo_passo", "Qual data e hora prefere?")
            }

        # Atualiza data no banco
        if dados.get("consulta_id") and dados.get("nova_data") and dados.get("nova_hora"):
            nova_dt = datetime.strptime(
                f"{dados['nova_data']} {dados['nova_hora']}", "%d/%m/%Y %H:%M"
            )
            await db.execute(
                update(Consulta)
                .where(Consulta.id == uuid.UUID(dados["consulta_id"]))
                .values(
                    data_hora=nova_dt,
                    status=StatusConsulta.remarcada,
                    atualizado_em=datetime.utcnow()
                )
            )
            await db.commit()

            return {
                **state,
                "consulta_id": dados["consulta_id"],
                "resposta_final": (
                    f"Prontinho! ✅ Sua consulta foi remarcada para "
                    f"{dados['nova_data']} às {dados['nova_hora']}. "
                    f"O veterinário já foi notificado por e-mail! 🐾"
                )
            }

    # ── AGENDAR ─────────────────────────────────────────────
    # Monta histórico da conversa para extração de dados
    historico = "\n".join([
        f"{'Cliente' if m.type == 'human' else 'Agente'}: {m.content}"
        for m in state["messages"][-6:]  # últimas 6 mensagens
    ])

    resposta = await llm.ainvoke([
        SystemMessage(content=PROMPT_COLETAR_DADOS.format(
            historico=historico,
            contexto=state.get("contexto_clinica", "")
        )),
        HumanMessage(content=mensagem)
    ])

    try:
        conteudo = re.sub(r"```json\n?|\n?```", "", resposta.content).strip()
        dados = json.loads(conteudo)
    except Exception:
        dados = {"dados_completos": False, "proximo_passo": "Pode me dizer o nome do seu pet e qual tipo de consulta precisa?"}

    # Dados incompletos — continua coletando
    if not dados.get("dados_completos"):
        return {
            **state,
            "dados_agendamento": dados,
            "resposta_final": dados.get(
                "proximo_passo",
                "Pode me passar mais alguns detalhes para finalizar o agendamento? 😊"
            )
        }

    # Dados completos — cria consulta no banco
    vet = await buscar_veterinario_principal(db)
    data_hora = datetime.strptime(
        f"{dados['data']} {dados['hora']}", "%d/%m/%Y %H:%M"
    )

    tipo_map = {
        "clinica_geral": TipoConsulta.clinica_geral,
        "clinica_cirurgica": TipoConsulta.clinica_cirurgica,
        "ortopedia": TipoConsulta.ortopedia,
        "neurologia_clinica": TipoConsulta.neurologia_clinica,
        "neurocirurgia": TipoConsulta.neurocirurgia,
        "neuro_oncologia": TipoConsulta.neuro_oncologia,
    }

    consulta = Consulta(
        cliente_id=uuid.UUID(cliente_id),
        veterinario_id=vet.id,
        tipo=tipo_map.get(dados.get("tipo_consulta", "clinica_geral"), TipoConsulta.clinica_geral),
        data_hora=data_hora,
        motivo=dados.get("motivo"),
        status=StatusConsulta.agendada,
    )
    db.add(consulta)
    await db.commit()
    await db.refresh(consulta)

# Cria evento no Google Calendar
google_event_id = criar_evento_calendario(
    calendar_id=vet.google_calendar_id or "primary",
    titulo=f"Consulta {dados.get('nome_pet', 'Pet')} — {dados.get('tipo_consulta', '')}",
    data_hora=data_hora,
    duracao_minutos=30,
    nome_cliente=dados.get("nome_tutor", ""),
    whatsapp_cliente=whatsapp,
    nome_pet=dados.get("nome_pet", ""),
    tipo_consulta=dados.get("tipo_consulta", ""),
    motivo=dados.get("motivo", ""),
)

# Atualiza o google_event_id na consulta
if google_event_id:
    await db.execute(
        update(Consulta)
        .where(Consulta.id == consulta.id)
        .values(google_event_id=google_event_id, email_enviado=True)
    )
    await db.commit()

# Envia e-mail ao veterinário
notificar_agendamento(
    email_veterinario=vet.email,
    nome_veterinario=vet.nome,
    nome_cliente=dados.get("nome_tutor", ""),
    whatsapp_cliente=whatsapp,
    nome_pet=dados.get("nome_pet", ""),
    especie_pet=dados.get("especie", ""),
    tipo_consulta=dados.get("tipo_consulta", ""),
    data_hora=data_hora,
    motivo=dados.get("motivo", ""),
    consulta_id=str(consulta.id),
)

    return {
        **state,
        "consulta_id": str(consulta.id),
        "dados_agendamento": dados,
        "resposta_final": confirmacao.content,
    }
