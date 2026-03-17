import json
import argparse
import os

# Simulação de um banco de dados de agendamentos em JSON
DB_PATH = os.path.join(os.path.dirname(__file__), "schedule_db.json")

def load_db():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def save_db(data):
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_specialists():
    # Simulação de base de especialistas (só pra referência interna do script, os doutores de specialties.md)
    return {
        "Clínica Geral": ["Dr. Carlos Miranda", "Dra. Ana Silva"],
        "Ortopedia": ["Dr. Roberto Mendes"],
        "Neurologia": ["Dra. Fernanda Torres"],
        "Dermatologia": ["Dra. Beatriz Costa"],
        "Cardiologia": ["Dr. João Paulo"]
    }

def schedule(tutor, pet, doctor, specialty, date, time):
    db = load_db()
    
    # Validação simples de especialidade
    specs = load_specialists()
    if specialty not in specs:
        return f"Erro: Especialidade '{specialty}' não encontrada. Verifique o nome correto."
    if doctor not in specs[specialty]:
        return f"Erro: O(a) médico(a) {doctor} não atende pela especialidade {specialty}."

    # Verifica conflito
    for app in db:
        if app['doctor'] == doctor and app['date'] == date and app['time'] == time:
            return f"Erro: O médico {doctor} já possui consulta marcada no dia {date} às {time}."
    
    # Pega max ID
    new_id = 1
    if db:
        new_id = max(app['id'] for app in db) + 1

    new_app = {
        "id": new_id,
        "tutor": tutor,
        "pet": pet,
        "doctor": doctor,
        "specialty": specialty,
        "date": date,
        "time": time
    }
    db.append(new_app)
    save_db(db)
    return f"Sucesso! Consulta ID {new_app['id']} agendada. Tutor: {tutor}, Pet: {pet}, Médico: {doctor}, Especialidade: {specialty}, Data: {date}, Hora: {time}."

def cancel(app_id):
    db = load_db()
    for app in db:
        if app['id'] == app_id:
            db.remove(app)
            save_db(db)
            return f"Sucesso: Consulta {app_id} do pet {app['pet']} (Tutor: {app['tutor']}) foi cancelada."
    return f"Erro: Consulta com ID {app_id} não encontrada."

def list_doctor_schedule(doctor, date):
    db = load_db()
    appointments = [app for app in db if app['doctor'] == doctor and app['date'] == date]
    if not appointments:
        return f"A agenda do(a) {doctor} no dia {date} está livre."
    
    res = f"Consultas do(a) {doctor} no dia {date}:\n"
    for app in appointments:
        res += f" - {app['time']}: {app['pet']} (Tutor: {app['tutor']}) [ID: {app['id']}]\n"
    return res

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gerenciar agendamentos da clínica")
    parser.add_argument("--action", choices=["schedule", "cancel", "list_doctor"], required=True)
    parser.add_argument("--tutor", type=str, help="Nome do tutor (para schedule)")
    parser.add_argument("--pet", type=str, help="Nome do pet (para schedule)")
    parser.add_argument("--doctor", type=str, help="Nome do veterinário")
    parser.add_argument("--specialty", type=str, help="Especialidade (para schedule)")
    parser.add_argument("--date", type=str, help="Data formato YYYY-MM-DD")
    parser.add_argument("--time", type=str, help="Horário formato HH:MM (para schedule)")
    parser.add_argument("--id", type=int, help="ID da consulta (para cancel)")

    args = parser.parse_args()

    if args.action == "schedule":
        if not all([args.tutor, args.pet, args.doctor, args.specialty, args.date, args.time]):
            print("Erro: Faltam parâmetros para agendar (tutor, pet, doctor, specialty, date, time).")
        else:
            print(schedule(args.tutor, args.pet, args.doctor, args.specialty, args.date, args.time))
    elif args.action == "cancel":
        if not args.id:
            print("Erro: ID da consulta é obrigatório para cancelar.")
        else:
            print(cancel(args.id))
    elif args.action == "list_doctor":
        if not all([args.doctor, args.date]):
            print("Erro: Médico e data são obrigatórios para listar a agenda.")
        else:
            print(list_doctor_schedule(args.doctor, args.date))
