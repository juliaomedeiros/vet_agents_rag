import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

st.set_page_config(
    page_title="VetAgent Dashboard",
    page_icon="🐾",
    layout="wide"
)

# ─────────────────────────────────────────
# Conexão com banco
# ─────────────────────────────────────────
DB_URL = os.getenv("DATABASE_URL", "").replace(
    "postgresql+asyncpg", "postgresql"
).replace("asyncpg", "psycopg2")

@st.cache_resource
def get_engine():
    return create_engine(DB_URL)

def query(sql):
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn)

# ─────────────────────────────────────────
# Header
# ─────────────────────────────────────────
st.title("🐾 VetAgent — Painel da Clínica")
st.caption(f"Atualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

# ─────────────────────────────────────────
# Métricas principais
# ─────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

try:
    total_agendamentos = query("SELECT COUNT(*) as total FROM consultas").iloc[0]["total"]
    hoje = query("SELECT COUNT(*) as total FROM consultas WHERE DATE(data_hora) = CURRENT_DATE").iloc[0]["total"]
    pendentes = query("SELECT COUNT(*) as total FROM consultas WHERE status = 'agendada'").iloc[0]["total"]
    confirmados = query("SELECT COUNT(*) as total FROM consultas WHERE status = 'confirmada'").iloc[0]["total"]

    col1.metric("📅 Total Agendamentos", total_agendamentos)
    col2.metric("📆 Consultas Hoje", hoje)
    col3.metric("⏳ Pendentes", pendentes)
    col4.metric("✅ Confirmados", confirmados)

except Exception as e:
    col1.error(f"Erro ao carregar métricas: {e}")

st.divider()

# ─────────────────────────────────────────
# Agendamentos de hoje
# ─────────────────────────────────────────
st.subheader("📋 Agendamentos de Hoje")

try:
    df_hoje = query("""
        SELECT
            to_char(c.data_hora, 'HH24:MI') as horario,
            cl.nome as tutor,
            p.nome as pet,
            c.tipo as servico,
            c.status,
            cl.whatsapp as telefone
        FROM consultas c
        JOIN clientes cl ON cl.id = c.cliente_id
        LEFT JOIN pets p ON p.id = c.pet_id
        WHERE DATE(c.data_hora) = CURRENT_DATE
        ORDER BY c.data_hora
    """)

    if df_hoje.empty:
        st.info("Nenhum agendamento para hoje.")
    else:
        st.dataframe(
            df_hoje,
            use_container_width=True,
            hide_index=True,
            column_config={
                "status": st.column_config.SelectboxColumn(
                    options=["agendada", "confirmada", "remarcada", "cancelada", "realizada"]
                )
            }
        )
except Exception as e:
    st.error(f"Erro: {e}")

st.divider()

# ─────────────────────────────────────────
# Gráficos
# ─────────────────────────────────────────
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("📊 Agendamentos por Status")
    try:
        df_status = query("""
            SELECT status, COUNT(*) as total
            FROM consultas
            GROUP BY status
        """)
        fig = px.pie(df_status, names="status", values="total",
                     color_discrete_sequence=px.colors.qualitative.Set3)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Erro: {e}")

with col_b:
    st.subheader("📈 Agendamentos Últimos 7 Dias")
    try:
        df_semana = query("""
            SELECT DATE(data_hora) as dia, COUNT(*) as total
            FROM consultas
            WHERE data_hora >= NOW() - INTERVAL '7 days'
            GROUP BY dia
            ORDER BY dia
        """)
        fig2 = px.bar(df_semana, x="dia", y="total",
                      color_discrete_sequence=["#4CAF50"])
        st.plotly_chart(fig2, use_container_width=True)
    except Exception as e:
        st.error(f"Erro: {e}")

st.divider()

# ─────────────────────────────────────────
# Histórico de conversas
# ─────────────────────────────────────────
st.subheader("💬 Últimas Conversas")

try:
    df_conv = query("""
        SELECT
            cl.whatsapp as telefone,
            m.conteudo as mensagem,
            m.origem as origem,
            to_char(m.criado_em, 'DD/MM HH24:MI') as horario
        FROM mensagens m
        JOIN clientes cl ON cl.id = m.cliente_id
        ORDER BY m.criado_em DESC
        LIMIT 20
    """)
    if df_conv.empty:
        st.info("Nenhuma conversa registrada ainda.")
    else:
        st.dataframe(df_conv, use_container_width=True, hide_index=True)
except Exception as e:
    st.error(f"Erro: {e}")
