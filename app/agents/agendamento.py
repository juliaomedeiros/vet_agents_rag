import json
import re
import uuid
import pytz
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import SystemMessage, HumanMessage

from agents.state import AgenteState
from core.llm import get_llm
from db.models import Consulta, Veterinario, TipoConsulta, StatusConsulta
from integrations.google_calendar import (
    criar_evento_calendario,
    remarcar_evento,
    cancelar_evento,
    listar_horarios_disponiveis,
)
from integrations.email_sender import (
    notificar_agendamento,
    notificar_remarcacao,
    notificar_cancelamento,
)
from skills.loader import load_skill

# ─────────────────────────────────────────────────────────────
# Skill
# ─────────────────────────────────────────────────────────────
_SKILL = load_skill("vet-clinic-receptionist")
_CLINIC_INFO = _SKILL["references"].get("clinic_info", "")
_SPECIALTIES = _SKILL["references"].get("specialties", "")

# Template de dados do tutor exibido ao cliente
TEMPLATE_TUTOR = """Por favor, preencha os dados abaixo para concluir o agendamento:

*Nome do Tutor:*
*Nome do Pet:*
*Sexo do Pet:*
*Espécie:*
*Raça:*"""

# ─────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────
PROMPT_COLETAR_DADOS = f"""{_SKILL["persona"]}

---

Você é responsável por coletar dados para agendamento, seguindo esta SEQUÊNCIA OBRIGATÓRIA:

1. Entender o que o pet tem (triagem/relato).
2. Informar o tipo de consulta adequado com base no relato.
3. Mostrar datas disponíveis (fornecidas no contexto — NÃO invente datas).
4. Solicitar a escolha de data/hora pelo cliente.
5. Solicitar dados do tutor via template (quando data já estiver definida).
6. Confirmar agendamento.

📅 DATA E HORA ATUAL: {{data_hoje}}
📋 HORÁRIOS DISPONÍVEIS NOS PRÓXIMOS 30 DIAS (Google Calendar):
{{horarios_disponiveis}}

⚠️ REGRAS CRÍTICAS:
- Use APENAS os horários da lista acima — jamais sugira horário que não esteja na lista.
- Se a lista estiver vazia, informe que não há vagas e peça para o cliente entrar em contato no dia seguinte.
- Quando faltar dados do tutor (após data definida), solicite usando o template fixo abaixo — não improvise.
- Nunca deixe frases incompletas ou cortadas. Escreva frases inteiras até o fim.
- O campo "proximo_passo" deve conter uma instrução clara e COMPLETA para o próximo contato.
- Se o cliente já descreveu o sintoma/problema no histórico ou na mensagem atual, RECONHEÇA isso e não pergunte novamente. Siga para o próximo passo (identificar tipo de consulta).
- Relatos urgentes (convulsão, paralisia etc.): acolha com empatia e informe que o veterinário precisará avaliar — siga para agendamento normalmente.

TEMPLATE DE DADOS DO TUTOR (use exatamente este formato quando precisar coletar):
{TEMPLATE_TUTOR}

Responda APENAS com JSON:
{{{{
  "nome_tutor": "nome ou null",
  "nome_pet": "nome do animal ou null",
  "sexo_pet": "macho/fêmea ou null",
  "especie": "cão/gato/outro ou null",
  "raca": "raça ou null",
  "tipo_consulta": "clinica_geral|neurologia|retorno_clinica_geral|retorno_neurologia|segmento_neurologia|coleta_exames ou null",
  "data": "DD/MM/AAAA ou null",
  "hora": "HH:MM ou null",
  "motivo": "motivo da consulta ou null",
  "dados_completos": true/false,
  "precisa_template_tutor": true/false,
  "proximo_passo": "instrução interna COMPLETA: o que fazer/perguntar agora (MÍNIMO 10 PALAVRAS)"
}}}}

Informações da clínica:
{_CLINIC_INFO}

Especialidades e Médicos:
{_SPECIALTIES}

Contexto RAG:
{{contexto}}

Conversa atual:
{{historico}}
"""

PROMPT_RESPOSTA_INTERMEDIARIA = f"""{_SKILL["persona"]}

---

Transforme a instrução interna abaixo em uma mensagem conversacional para o cliente.

Instrução interna: {{proximo_passo}}
Precisa exibir template de dados?: {{precisa_template}}

REGRAS:
- Reescreva de forma natural, acolhedora e empática.
- Se precisa_template for true, inclua o template exatamente como está abaixo, após sua mensagem.
- Seja breve (máximo 2 frases antes do template).
- SEMPRE termine cada frase. NUNCA deixe textos cortados no meio da palavra ou da ideia.
- Se o template de dados for exibido, ele deve vir APÓS uma saudação ou mensagem completa.

Template de dados (inclua quando precisa_template for true):
{TEMPLATE_TUTOR}
"""

PROMPT_CONFIRMAR = f"""{_SKILL["persona"]}

---

Gere uma mensagem de CONFIRMAÇÃO de agendamento para o cliente.

Template base:
{_SKILL["assets"].get("appointment_confirmation", "")}

Dados da consulta:
{{dados}}

REGRAS:
- Inclua: nome do pet, espécie, tipo de consulta, data, hora e veterinário.
- Seja direto e conciso.
- SEMPRE termine cada frase. NUNCA deixe textos cortados.
- Finalize perguntando se precisa de mais alguma coisa. 🐾
"""

PROMPT_REMARCAR = _SKILL["persona"] + """

---

O cliente quer REMARCAR uma consulta.

📅 DATA E HORA ATUAL: {data_hoje}
📋 HORÁRIOS DISPONÍVEIS (Google Calendar):
{horarios_disponiveis}

Consultas agendadas do cliente:
{consultas}

Mensagem do cliente: {mensagem}

REGRAS:
- Use APENAS horários da lista acima para a nova data.
- Se a lista estiver vazia, informe que não há vagas e peça contato no dia seguinte.
- Nunca deixe frases incompletas.
- Extraia a nova data/hora desejada e qual consulta remarca, leve em consideração
o horário que a clínica funciona e os dias da semana que ela está aberta. Horário de funcionamento: Segunda a Sexta das 14h00 às 18h00.

Responda APENAS com JSON:
{{
  "consulta_id": "UUID da consulta a remarcar ou null",
  "nova_data": "DD/MM/AAAA ou null",
  "nova_hora": "HH:MM ou null",
  "dados_completos": true/false,
  "proximo_passo": "o que perguntar se faltar dados"
}}
"""


# ─────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────
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


def formatar_horarios(slots: list[str]) -> str:
    """Formata lista de slots para exibição no prompt."""
    if not slots:
        return "⚠️ Nenhum horário disponível nos próximos 30 dias."
    # Limita a 40 slots para mostrar pelo menos 5 dias (8 slots/dia)
    exibir = slots[:40]
    resto = len(slots) - len(exibir)
    texto = "\n".join(f"• {s}" for s in exibir)
    if resto > 0:
        texto += f"\n... e mais {resto} horários disponíveis."
    return texto


# ─────────────────────────────────────────────────────────────
# NÓ: Agendamento
# ─────────────────────────────────────────────────────────────
async def agente_agendamento(state: AgenteState, db: AsyncSession) -> AgenteState:
    """
    Gerencia o fluxo de agendar, remarcar ou cancelar consultas.
    Sequência: triagem → tipo de consulta → datas (Calendar) → dados do tutor → confirmação.
    """
    llm = get_llm()
    intencao = state.get("intencao", "AGENDAR")
    mensagem = state["messages"][-1].content
    cliente_id = state.get("cliente_id")
    whatsapp = state.get("whatsapp", "")

    tz = pytz.timezone("America/Fortaleza")
    agora = datetime.now(tz)
    DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira",
                   "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    data_hoje = (
        f"{DIAS_SEMANA[agora.weekday()]}, {agora.strftime('%d/%m/%Y')} — "
        f"horário atual (Brasília): {agora.strftime('%H:%M')}"
    )

    vet = await buscar_veterinario_principal(db)

    # ── CANCELAR ────────────────────────────────────────────
    if intencao == "CANCELAR":
        consultas = await buscar_consultas_cliente(db, cliente_id)

        if not consultas:
            return {
                **state,
                "resposta_final": (
                    "Não encontrei nenhuma consulta agendada para você. 🤔 "
                    "Posso marcar uma nova consulta?"
                )
            }

        # Se há mais de uma, pede confirmação de qual cancelar
        if len(consultas) > 1:
            lista = "\n".join(
                f"• {c.tipo.value} — {c.data_hora.strftime('%d/%m/%Y às %H:%M')}"
                for c in consultas
            )
            dados_agend = state.get("dados_agendamento") or {}
            consulta_id_escolhida = dados_agend.get("cancelar_consulta_id")

            if not consulta_id_escolhida:
                return {
                    **state,
                    "resposta_final": (
                        f"Você tem mais de uma consulta agendada. Qual deseja cancelar?\n\n{lista}\n\n"
                        "Por favor, informe a data da consulta que deseja cancelar."
                    )
                }
            consulta = next(
                (c for c in consultas if str(c.id) == consulta_id_escolhida),
                consultas[0]
            )
        else:
            consulta = consultas[0]

        await db.execute(
            update(Consulta)
            .where(Consulta.id == consulta.id)
            .values(status=StatusConsulta.cancelada, atualizado_em=datetime.utcnow())
        )
        await db.commit()

        if consulta.google_event_id and vet:
            cancelar_evento(
                calendar_id=vet.google_calendar_id or "primary",
                event_id=consulta.google_event_id,
            )
            notificar_cancelamento(
                email_veterinario=vet.email,
                nome_veterinario=vet.nome,
                nome_cliente=state.get("cliente_nome") or "",
                whatsapp_cliente=whatsapp,
                nome_pet=consulta.motivo or "",
                tipo_consulta=consulta.tipo.value,
                data_hora=consulta.data_hora,
                consulta_id=str(consulta.id),
            )

        return {
            **state,
            "resposta_final": (
                "Tudo certo! 😊 Sua consulta foi cancelada.\n\n"
                "Se quiser agendar uma nova consulta, é só entrar em contato conosco! "
                "Cuide bem do seu pet! 🐾"
            ),
            "consulta_id": str(consulta.id),
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

        slots = listar_horarios_disponiveis(
            calendar_id=vet.google_calendar_id or "primary" if vet else "primary"
        )
        horarios_str = formatar_horarios(slots)

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
                mensagem=mensagem,
                data_hoje=data_hoje,
                horarios_disponiveis=horarios_str,
            )),
            HumanMessage(content=mensagem)
        ])

        try:
            conteudo = re.sub(r"```json\n?|\n?```", "", resposta.content).strip()
            dados = json.loads(conteudo)
        except Exception:
            dados = {"dados_completos": False, "proximo_passo": "Qual data prefere para remarcar?"}

        if not dados.get("dados_completos"):
            return {
                **state,
                "resposta_final": dados.get("proximo_passo", "Qual data e hora prefere para remarcar? 😊")
            }

        consulta_id = dados.get("consulta_id")
        nova_data = dados.get("nova_data")
        nova_hora = dados.get("nova_hora")

        if consulta_id and nova_data and nova_hora:
            tz = pytz.timezone("America/Fortaleza")
            nova_dt = tz.localize(datetime.strptime(f"{nova_data} {nova_hora}", "%d/%m/%Y %H:%M"))

            await db.execute(
                update(Consulta)
                .where(Consulta.id == uuid.UUID(consulta_id))
                .values(
                    data_hora=nova_dt,
                    status=StatusConsulta.remarcada,
                    atualizado_em=datetime.utcnow()
                )
            )
            await db.commit()

            # Busca a consulta remarcada pelo id correto
            consulta_remarcada = next(
                (c for c in consultas if str(c.id) == consulta_id),
                consultas[0]
            )
            if consulta_remarcada.google_event_id and vet:
                remarcar_evento(
                    calendar_id=vet.google_calendar_id or "primary",
                    event_id=consulta_remarcada.google_event_id,
                    nova_data_hora=nova_dt,
                )
                notificar_remarcacao(
                    email_veterinario=vet.email,
                    nome_veterinario=vet.nome,
                    nome_cliente=state.get("cliente_nome") or "",
                    whatsapp_cliente=whatsapp,
                    nome_pet="",
                    tipo_consulta=consulta_remarcada.tipo.value,
                    data_hora_antiga=consulta_remarcada.data_hora,
                    data_hora_nova=nova_dt,
                    consulta_id=consulta_id,
                )

            return {
                **state,
                "consulta_id": consulta_id,
                "resposta_final": (
                    f"Prontinho! ✅ Consulta remarcada para {nova_data} às {nova_hora}. "
                    f"O veterinário já foi notificado. 🐾"
                )
            }

    # ── AGENDAR ─────────────────────────────────────────────
    # Busca horários disponíveis do Google Calendar
    slots = listar_horarios_disponiveis(
        calendar_id=vet.google_calendar_id or "primary" if vet else "primary"
    )
    horarios_str = formatar_horarios(slots)

    # Histórico exclui a última mensagem (que é o 'mensagem' atual) para evitar redundância
    historico = "\n".join([
        f"{'Cliente' if m.type == 'human' else 'Agente'}: {m.content}"
        for m in state["messages"][:-1][-8:]
    ])

    resposta = await llm.ainvoke([
        SystemMessage(content=PROMPT_COLETAR_DADOS.format(
            historico=historico,
            contexto=state.get("contexto_clinica", ""),
            data_hoje=data_hoje,
            horarios_disponiveis=horarios_str,
            _CLINIC_INFO=_CLINIC_INFO,
            _SPECIALTIES=_SPECIALTIES,
        )),
        HumanMessage(content=mensagem)
    ])

    try:
        conteudo = re.sub(r"```json\n?|\n?```", "", resposta.content).strip()
        dados = json.loads(conteudo)
    except Exception:
        dados = {
            "dados_completos": False,
            "precisa_template_tutor": False,
            "proximo_passo": "Pode me contar o que está acontecendo com seu pet?",
        }

    if not dados.get("dados_completos"):
        instrucao = dados.get("proximo_passo", "Faltam informações para concluir o agendamento.")
        precisa_template = dados.get("precisa_template_tutor", False)

        resposta_intermediaria = await llm.ainvoke([
            SystemMessage(content=PROMPT_RESPOSTA_INTERMEDIARIA.format(
                proximo_passo=instrucao,
                precisa_template="sim" if precisa_template else "não",
            )),
            HumanMessage(content=mensagem)
        ])
        return {
            **state,
            "dados_agendamento": dados,
            "resposta_final": resposta_intermediaria.content,
        }

    # Dados completos — cria consulta no banco
    tz = pytz.timezone("America/Fortaleza")
    data_hora = tz.localize(datetime.strptime(f"{dados['data']} {dados['hora']}", "%d/%m/%Y %H:%M"))

    tipo_map = {
        "clinica_geral": TipoConsulta.clinica_geral,
        "neurologia": TipoConsulta.neurologia_clinica,
        "retorno_clinica_geral": TipoConsulta.clinica_geral,
        "retorno_neurologia": TipoConsulta.neurologia_clinica,
        "segmento_neurologia": TipoConsulta.neurologia_clinica,
        "coleta_exames": TipoConsulta.clinica_geral,
    }
    tipo_raw = dados.get("tipo_consulta", "clinica_geral")
    duracao = 60 if tipo_raw == "neurologia" else 30

    consulta = Consulta(
        cliente_id=uuid.UUID(cliente_id),
        veterinario_id=vet.id,
        tipo=tipo_map.get(tipo_raw, TipoConsulta.clinica_geral),
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
        titulo=f"Consulta {dados.get('nome_pet', 'Pet')} — {tipo_raw}",
        data_hora=data_hora,
        duracao_minutos=duracao,
        nome_cliente=dados.get("nome_tutor", ""),
        whatsapp_cliente=whatsapp,
        nome_pet=dados.get("nome_pet", ""),
        tipo_consulta=tipo_raw,
        motivo=dados.get("motivo", ""),
    )

    if google_event_id:
        await db.execute(
            update(Consulta)
            .where(Consulta.id == consulta.id)
            .values(google_event_id=google_event_id, email_enviado=True)
        )
        await db.commit()

    # Notifica veterinário por e-mail
    notificar_agendamento(
        email_veterinario=vet.email,
        nome_veterinario=vet.nome,
        nome_cliente=dados.get("nome_tutor", ""),
        whatsapp_cliente=whatsapp,
        nome_pet=dados.get("nome_pet", ""),
        especie_pet=dados.get("especie", ""),
        tipo_consulta=tipo_raw,
        data_hora=data_hora,
        motivo=dados.get("motivo", ""),
        consulta_id=str(consulta.id),
    )

    # Gera mensagem de confirmação para o cliente
    confirmacao = await llm.ainvoke([
        SystemMessage(content=PROMPT_CONFIRMAR.format(
            dados=json.dumps({
                **dados,
                "veterinario": vet.nome,
            }, ensure_ascii=False)
        )),
        HumanMessage(content="Gere a confirmação")
    ])

    return {
        **state,
        "consulta_id": str(consulta.id),
        "dados_agendamento": dados,
        "resposta_final": confirmacao.content,
    }
