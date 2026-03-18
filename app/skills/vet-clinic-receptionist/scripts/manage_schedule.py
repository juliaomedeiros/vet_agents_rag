"""
manage_schedule.py
──────────────────
Gerencia agendamentos da clínica de forma independente do banco PostgreSQL.
Usa um arquivo JSON local como persistência simples (schedule_db.json).

Funções públicas:
  schedule()               → agenda nova consulta
  cancel()                 → cancela consulta por ID
  reschedule()             → remarca consulta por ID para nova data/hora
  list_doctor_schedule()   → lista agenda de um médico em uma data
  list_available_slots()   → lista horários livres para um médico em uma data
"""

import json
import os

# ─────────────────────────────────────────────────────────────
# Configurações
# ─────────────────────────────────────────────────────────────
DB_PATH = os.path.join(os.path.dirname(__file__), "schedule_db.json")

SPECIALISTS: dict[str, list[str]] = {
    "Clínica Geral": ["Dr. Daniel Travassos"],
    "Neurologia":    ["Dr. Daniel Travassos"],
}

# Slots de 30min, seg-sex 14h-18h
HORARIOS: list[str] = [
    "14:00", "14:30", "15:00", "15:30",
    "16:00", "16:30", "17:00", "17:30"
]


# ─────────────────────────────────────────────────────────────
# Helpers de persistência
# ─────────────────────────────────────────────────────────────
def load_db() -> list[dict]:
    """Lê o arquivo JSON de agendamentos. Retorna lista vazia se não existir."""
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def save_db(data: list[dict]) -> None:
    """Salva a lista de agendamentos no JSON, criando o diretório se necessário."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# ─────────────────────────────────────────────────────────────
# Lógica interna de slots e conflitos
# ─────────────────────────────────────────────────────────────
def _ocupados(db: list[dict], doctor: str, date: str) -> set[str]:
    """
    Retorna o conjunto de horários bloqueados para um médico em uma data.
    Consultas de 60min bloqueiam também o slot seguinte.
    """
    ocupado: set[str] = set()
    for app in db:
        if app["doctor"] != doctor or app["date"] != date:
            continue
        h = app["time"]
        ocupado.add(h)
        if app.get("duration", 30) == 60 and h in HORARIOS:
            idx = HORARIOS.index(h)
            if idx + 1 < len(HORARIOS):
                ocupado.add(HORARIOS[idx + 1])
    return ocupado


def _tem_conflito(db: list[dict], doctor: str, date: str,
                  time: str, duration: int, exclude_id: int | None = None) -> bool:
    """
    Verifica se há conflito para um médico/data/horário/duração.
    Se exclude_id for fornecido, ignora aquele agendamento (útil no reschedule).
    """
    bloqueados = _ocupados(
        [a for a in db if a["id"] != exclude_id] if exclude_id is not None else db,
        doctor, date
    )
    if time in bloqueados:
        return True
    # Consulta de 1h precisa do slot seguinte livre também
    if duration == 60 and time in HORARIOS:
        idx = HORARIOS.index(time)
        if idx + 1 < len(HORARIOS) and HORARIOS[idx + 1] in bloqueados:
            return True
    return False


def get_available_slots(doctor: str, date: str, duration: int = 30) -> list[str]:
    """Retorna lista de horários livres para um médico em uma data."""
    db = load_db()
    bloqueados = _ocupados(db, doctor, date)

    livres: list[str] = []
    for i, h in enumerate(HORARIOS):
        if h in bloqueados:
            continue
        if duration == 60:
            # Precisa de 2 slots consecutivos livres
            if i + 1 < len(HORARIOS) and HORARIOS[i + 1] not in bloqueados:
                livres.append(h)
        else:
            livres.append(h)
    return livres


# ─────────────────────────────────────────────────────────────
# Funções públicas
# ─────────────────────────────────────────────────────────────
def schedule(tutor: str, pet: str, doctor: str, specialty: str,
             date: str, time: str, primeira_neurologica: bool = False) -> str:
    """Agenda uma nova consulta. Retorna mensagem de resultado."""
    if specialty not in SPECIALISTS:
        return (f"Erro: Especialidade '{specialty}' não encontrada. "
                f"Disponíveis: {list(SPECIALISTS.keys())}")
    if doctor not in SPECIALISTS[specialty]:
        return (f"Erro: {doctor} não atende {specialty}. "
                f"Médicos disponíveis: {SPECIALISTS[specialty]}")
    if time not in HORARIOS:
        return f"Erro: Horário '{time}' inválido. Disponíveis: {HORARIOS}"

    duration = 60 if (specialty == "Neurologia" and primeira_neurologica) else 30
    db = load_db()

    if _tem_conflito(db, doctor, date, time, duration):
        return f"Erro: {doctor} já possui consulta em {date} às {time} (ou slot seguinte ocupado para 1h)."

    new_id = (max(a["id"] for a in db) + 1) if db else 1
    db.append({
        "id":        new_id,
        "tutor":     tutor,
        "pet":       pet,
        "doctor":    doctor,
        "specialty": specialty,
        "date":      date,
        "time":      time,
        "duration":  duration,
    })
    save_db(db)
    return (f"✅ Consulta ID {new_id} agendada!\n"
            f"Tutor: {tutor} | Pet: {pet} | Médico: {doctor}\n"
            f"Especialidade: {specialty} | Data: {date} | Hora: {time} | Duração: {duration}min")


def cancel(app_id: int) -> str:
    """Cancela uma consulta pelo ID."""
    db = load_db()
    for i, app in enumerate(db):
        if app["id"] == app_id:
            removed = db.pop(i)          # remove sem iterar e deletar ao mesmo tempo
            save_db(db)
            return (f"✅ Consulta {app_id} do pet '{removed['pet']}' "
                    f"(Tutor: {removed['tutor']}) cancelada.")
    return f"Erro: Consulta ID {app_id} não encontrada."


def reschedule(app_id: int, new_date: str, new_time: str) -> str:
    """Remarca uma consulta para nova data/hora."""
    if new_time not in HORARIOS:
        return f"Erro: Horário '{new_time}' inválido. Disponíveis: {HORARIOS}"

    db = load_db()
    for i, app in enumerate(db):
        if app["id"] != app_id:
            continue

        duration = app.get("duration", 30)
        if _tem_conflito(db, app["doctor"], new_date, new_time, duration, exclude_id=app_id):
            return (f"Erro: {app['doctor']} já tem consulta em "
                    f"{new_date} às {new_time} (ou slot seguinte ocupado para 1h).")

        # Atualiza em uma cópia para evitar mutação silenciosa na lista original
        updated = {**app, "date": new_date, "time": new_time}
        db[i] = updated
        save_db(db)
        return (f"✅ Consulta {app_id} reagendada!\n"
                f"Pet: {updated['pet']} | Nova data: {new_date} às {new_time}")

    return f"Erro: Consulta ID {app_id} não encontrada."


def list_doctor_schedule(doctor: str, date: str) -> str:
    """Lista a agenda completa de um médico em uma data."""
    db = load_db()
    appointments = [a for a in db if a["doctor"] == doctor and a["date"] == date]
    if not appointments:
        return f"Agenda de {doctor} em {date} está livre."

    res = f"📋 Agenda de {doctor} em {date}:\n"
    for app in sorted(appointments, key=lambda x: x["time"]):
        res += (f"  {app['time']} ({app.get('duration', 30)}min) "
                f"— {app['pet']} / Tutor: {app['tutor']} [ID: {app['id']}]\n")
    return res


def list_available_slots(doctor: str, date: str,
                         primeira_neurologica: bool = False) -> str:
    """Lista os horários disponíveis para um médico em uma data."""
    duration = 60 if primeira_neurologica else 30
    slots = get_available_slots(doctor, date, duration)
    if not slots:
        return f"Sem horários disponíveis para {doctor} em {date}."
    return (f"Horários disponíveis para {doctor} em {date} "
            f"({'1h' if duration == 60 else '30min'}):\n"
            + "\n".join(f"  - {s}" for s in slots))
