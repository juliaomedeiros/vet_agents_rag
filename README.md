# 🐾 VetAgent — Assistente de Atendimento Veterinário com IA

Sistema completo de atendimento automatizado para clínicas veterinárias via WhatsApp,
construído com agentes de IA usando LangGraph, Google Gemini, RAG com pgvector e
dashboard Streamlit para o veterinário.

---

## 📋 Índice

- [Visão Geral](#-visão-geral)
- [Arquitetura](#-arquitetura)
- [Tecnologias](#-tecnologias)
- [Pré-requisitos](#-pré-requisitos)
- [Instalação e Configuração](#-instalação-e-configuração)
- [Adicionando Arquivos ao RAG](#-adicionando-arquivos-ao-rag)
- [Rodando o Projeto](#-rodando-o-projeto)
- [Módulos do Sistema](#-módulos-do-sistema)
- [Variáveis de Ambiente](#-variáveis-de-ambiente)
- [Dashboard](#-dashboard)
- [Deploy em Produção](#-deploy-em-produção)
- [Estrutura de Pastas](#-estrutura-de-pastas)

---

## 🎯 Visão Geral

O VetAgent é um sistema de atendimento inteligente que:

- 💬 Conversa com clientes via **WhatsApp** de forma natural e coloquial
- 📅 **Agenda, remarca e cancela** consultas diretamente no Google Calendar do veterinário
- 📧 Envia **e-mail de notificação** ao veterinário a cada movimentação de consulta
- 🧠 Usa **RAG** (Retrieval-Augmented Generation) para responder dúvidas com base nos documentos da clínica
- 👤 **Reconhece clientes recorrentes** pelo número de WhatsApp via memória vetorial
- 🛡️ Possui **guardrails** de entrada e saída contra linguagem ofensiva e prompt injection
- 📊 Oferece **dashboard Streamlit** para o veterinário monitorar atendimentos
- 🔍 Integra com **LangSmith** para observabilidade completa dos agentes

---

## 🏗️ Arquitetura

Mensagem WhatsApp
│
▼
┌─────────────┐ bloqueada ┌──────────────┐
│ Guardrails │ ─────────────────► │ Bloqueio │
│ (entrada) │ └──────────────┘
└─────────────┘
│ ok
▼
┌─────────────┐
│Recepcionista│ ── identifica cliente + detecta intenção
└─────────────┘
│
├── INFORMACAO ──► AgentInformacoes (RAG)
├── AGENDAR ──► AgentAgendamento (Google Calendar)
├── REMARCAR ──► AgentAgendamento
└── CANCELAR ──► AgentAgendamento
│
▼
┌─────────────┐
│ Guardrails │ ── valida saída
│ (saída) │
└─────────────┘
│
Resposta ao cliente


---

## 🛠️ Tecnologias

| Camada | Tecnologia |
|---|---|
| LLM | Google Gemini 1.5 Pro |
| Agentes | LangGraph + LangChain |
| Embeddings | Google text-embedding-004 |
| Vector Store | pgvector (PostgreSQL) |
| API Web | FastAPI |
| Dashboard | Streamlit |
| Banco de dados | PostgreSQL 16 |
| Conversão de docs | MarkItDown (Microsoft) |
| WhatsApp (dev) | Evolution API |
| WhatsApp (prod) | Meta Cloud API |
| Observabilidade | LangSmith |
| Infraestrutura | Docker + Docker Compose |
| Produção | VPS Hetzner + Nginx + Certbot |

---

## ✅ Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) e Docker Compose instalados
- [Git](https://git-scm.com/)
- **Google Gemini API Key** → [aistudio.google.com](https://aistudio.google.com)
- **LangSmith Account** (gratuito) → [smith.langchain.com](https://smith.langchain.com)
- **Google Cloud Project** com Calendar API e Gmail API ativadas
- **Evolution API** rodando localmente (dev) ou conta Meta Business (produção)

---

## 🚀 Instalação e Configuração

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/vet-agent.git
cd vet-agent

2. Configure as variáveis de ambiente
bash
cp .env.example .env
Edite o .env com suas credenciais:

text
# Obrigatório para começar
GEMINI_API_KEY=sua_chave_aqui
POSTGRES_PASSWORD=uma_senha_segura

# Opcional em dev (ativa observabilidade)
LANGCHAIN_API_KEY=sua_chave_langsmith
⚠️ Nunca versione o arquivo .env. Ele já está no .gitignore.

3. Crie as pastas necessárias
bash
mkdir -p rag_files
mkdir -p app/credentials
4. Adicione as credenciais do Google
Baixe o credentials.json do seu projeto no
Google Cloud Console e coloque em:

text
app/credentials/google_credentials.json
📁 Adicionando Arquivos ao RAG
Os arquivos de conhecimento da clínica ficam na pasta rag_files/ na raiz do projeto.

Formatos suportados: .txt .docx .pdf .md .xlsx .pptx

bash
# Copie seus arquivos para a pasta
cp /caminho/dos/seus/arquivos/* ./rag_files/

# Exemplos do que incluir:
# - servicos_e_especialidades.docx
# - horarios_de_atendimento.txt
# - faq_clientes.docx
# - protocolo_de_consulta.pdf
# - informacoes_da_clinica.txt
💡 O volume Docker sincroniza a pasta automaticamente com o container.
Os arquivos são indexados automaticamente na primeira vez que a app sobe.

Para forçar reindexação após alterar arquivos:

bash
curl -X POST http://localhost:8000/admin/rag/reindexar
▶️ Rodando o Projeto
Desenvolvimento
bash
# Passo 1 — Sobe apenas o banco de dados
docker compose up postgres -d

# Aguarda ficar healthy (~10 segundos)
docker compose ps

# Passo 2 — Verifica as tabelas criadas
docker exec -it vet_postgres psql -U vet_user -d vet_clinic -c "\dt"

# Passo 3 — Quando todos os módulos estiverem prontos,
# sobe todos os serviços
docker compose up -d

# Acompanha os logs
docker compose logs -f app
Verificando os serviços
Serviço	URL
API FastAPI	http://localhost:8000
Docs da API (Swagger)	http://localhost:8000/docs
Dashboard Streamlit	http://localhost:8501
PostgreSQL	localhost:5432
Parando o sistema
bash
# Para os containers (mantém os dados)
docker compose down

# Para e REMOVE os dados (reset completo)
docker compose down -v
📦 Módulos do Sistema
O projeto foi construído em módulos progressivos.
Adicione cada módulo conforme a documentação:

#	Módulo	Arquivos principais	Status
1	Infraestrutura Base	docker-compose.yml, .env, config.py, Dockerfiles	✅
2	Banco de Dados	db/models.py, db/session.py, migrations/001_initial.sql	✅
3	Pipeline RAG	rag/ingestor.py, rag/retriever.py, rag/memory.py, core/llm.py	✅
4	Agentes LangGraph	agents/graph.py, agents/recepcionista.py, agents/agendamento.py, agents/guardrails.py	✅
5	Integrações Externas	integrations/google_calendar.py, integrations/email_sender.py, integrations/whatsapp.py	⏳
6	App FastAPI	main.py (webhook WhatsApp + endpoints admin)	⏳
7	Dashboard Streamlit	dashboard/app.py, pages/agenda.py, pages/conversas.py, pages/metricas.py	⏳
8	Produção (Nginx)	nginx/nginx.conf, HTTPS via Certbot	⏳
Como adicionar cada módulo
bash
# Após criar os arquivos de cada módulo:

# 1. Rebuild da imagem se mudou requirements.txt
docker compose build app

# 2. Reinicia o container da app
docker compose up app -d --force-recreate

# 3. Verifica os logs
docker compose logs -f app
🔑 Variáveis de Ambiente
Copie o .env.example e preencha conforme necessário:

text
# ── OBRIGATÓRIO ──────────────────────────────────────────────
GEMINI_API_KEY=           # Google AI Studio → aistudio.google.com
POSTGRES_PASSWORD=        # senha forte para o banco

# ── RECOMENDADO ──────────────────────────────────────────────
LANGCHAIN_API_KEY=        # LangSmith → smith.langchain.com

# ── WHATSAPP DEV (Evolution API) ─────────────────────────────
WHATSAPP_PROVIDER=evolution
EVOLUTION_API_URL=        # URL da sua Evolution API local
EVOLUTION_API_KEY=        # chave da Evolution API
EVOLUTION_INSTANCE=       # nome da instância criada

# ── WHATSAPP PRODUÇÃO (Meta Cloud API) ───────────────────────
WHATSAPP_PROVIDER=meta
META_WHATSAPP_TOKEN=      # token Meta Business API
META_PHONE_NUMBER_ID=     # ID do número de telefone
META_VERIFY_TOKEN=        # token de verificação do webhook

# ── GOOGLE CALENDAR + GMAIL ───────────────────────────────────
GOOGLE_CREDENTIALS_JSON=./credentials/google_credentials.json
GOOGLE_TOKEN_JSON=./credentials/google_token.json

# ── EMAIL (SMTP) ──────────────────────────────────────────────
SMTP_USER=                # seu@gmail.com
SMTP_PASSWORD=            # senha de app gerada no Gmail

# ── APLICAÇÃO ─────────────────────────────────────────────────
APP_ENV=development       # trocar para production no deploy
📊 Dashboard
O dashboard Streamlit fica em http://localhost:8501 e oferece:

📅 Agenda — consultas do dia, semana e mês com status em tempo real

💬 Conversas — histórico completo de atendimentos por cliente

📈 Métricas — volume de atendimentos, tipos mais agendados, horários de pico e taxa de cancelamento

🔍 LangSmith — link direto para os traces de IA (debug e performance dos agentes)

☁️ Deploy em Produção
VPS Hetzner (recomendado)
bash
# 1. Contrate um servidor CX21 (~€4/mês) em hetzner.com
# 2. Acesse via SSH
ssh root@seu-ip

# 3. Instale o Docker
curl -fsSL https://get.docker.com | sh

# 4. Clone o repositório
git clone https://github.com/seu-usuario/vet-agent.git
cd vet-agent

# 5. Configure o .env para produção
cp .env.example .env
nano .env
# Altere: APP_ENV=production e WHATSAPP_PROVIDER=meta

# 6. Suba com perfil de produção (inclui Nginx)
docker compose --profile production up -d

# 7. Configure HTTPS (substitua pelo seu domínio)
docker exec vet_nginx certbot --nginx -d seu-dominio.com
Atualizando em produção
bash
git pull origin main
docker compose --profile production up -d --build
📂 Estrutura de Pastas
text
vet-agent/
├── docker-compose.yml
├── .env
├── .env.example
├── .gitignore
├── README.md
│
├── app/
│   ├── main.py
│   ├── Dockerfile
│   ├── requirements.txt
│   │
│   ├── agents/
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── recepcionista.py
│   │   ├── informacoes.py
│   │   ├── agendamento.py
│   │   └── guardrails.py
│   │
│   ├── integrations/
│   │   ├── whatsapp.py
│   │   ├── google_calendar.py
│   │   └── email_sender.py
│   │
│   ├── rag/
│   │   ├── ingestor.py
│   │   ├── retriever.py
│   │   └── memory.py
│   │
│   ├── db/
│   │   ├── models.py
│   │   ├── session.py
│   │   └── migrations/
│   │       └── 001_initial.sql
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── llm.py
│   │   └── langsmith.py
│   │
│   └── credentials/
│       └── google_credentials.json  ← não versionar!
│
├── dashboard/
│   ├── app.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── pages/
│       ├── agenda.py
│       ├── conversas.py
│       └── metricas.py
│
├── rag_files/         ← seus arquivos .txt e .docx aqui
│
└── nginx/
    ├── nginx.conf
    └── Dockerfile
🔒 .gitignore recomendado
text
# Ambiente
.env
*.env

# Credenciais Google
app/credentials/

# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/

# Docker
postgres_data/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db
🤝 Contribuindo
Faça um fork do projeto

Crie uma branch: git checkout -b feature/minha-feature

Commit suas mudanças: git commit -m 'feat: minha feature'

Push para a branch: git push origin feature/minha-feature

Abra um Pull Request

📄 Licença
MIT License — veja o arquivo LICENSE para detalhes.

👨‍💻 Suporte
Dúvidas ou problemas? Abra uma issue no repositório.

Desenvolvido com 🐾 para facilitar o atendimento de clínicas veterinárias.

