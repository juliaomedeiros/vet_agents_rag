-- ─────────────────────────────────────────────────────────
-- Habilita extensão vetorial (pgvector)
-- ─────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─────────────────────────────────────────────────────────
-- 👨‍⚕️ Veterinários
-- Estrutura escalável: começa com 1, suporta N
-- ─────────────────────────────────────────────────────────
CREATE TABLE veterinarios (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nome            VARCHAR(150)    NOT NULL,
    especialidades  TEXT[]          NOT NULL DEFAULT '{}',
    email           VARCHAR(150)    NOT NULL UNIQUE,
    telefone        VARCHAR(20),
    google_calendar_id VARCHAR(200), -- ID da agenda Google do médico
    ativo           BOOLEAN         NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    atualizado_em   TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Seed: veterinário inicial da clínica
INSERT INTO veterinarios (nome, especialidades, email, google_calendar_id) VALUES
(
    'Dr. Daniel Travassos',
    ARRAY[
        'Clínica Geral',
        'Clínica Cirúrgica',
        'Ortopedia',
        'Neurologia Clínica',
        'Neurocirurgia Avançada',
        'Neuro-oncologia'
    ],
    'veterinario@clinica.com',
    'primary'  -- trocar pelo Calendar ID real depois
);

-- ─────────────────────────────────────────────────────────
-- 🐾 Clientes
-- Identificados pelo número WhatsApp
-- ─────────────────────────────────────────────────────────
CREATE TABLE clientes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    whatsapp        VARCHAR(30)     NOT NULL UNIQUE,  -- ex: 5583999999999
    nome            VARCHAR(150),
    email           VARCHAR(150),
    primeiro_contato TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    ultimo_contato  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    ativo           BOOLEAN         NOT NULL DEFAULT TRUE
);

-- ─────────────────────────────────────────────────────────
-- 🐶 Pets
-- Um cliente pode ter múltiplos pets
-- ─────────────────────────────────────────────────────────
CREATE TABLE pets (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cliente_id      UUID            NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    nome            VARCHAR(100)    NOT NULL,
    especie         VARCHAR(50),    -- cão, gato, etc.
    raca            VARCHAR(100),
    data_nascimento DATE,
    observacoes     TEXT,
    criado_em       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────
-- 📅 Consultas (Agendamentos)
-- ─────────────────────────────────────────────────────────
CREATE TYPE status_consulta AS ENUM (
    'agendada',
    'confirmada',
    'remarcada',
    'cancelada',
    'realizada'
);

CREATE TYPE tipo_consulta AS ENUM (
    'clinica_geral',
    'clinica_cirurgica',
    'ortopedia',
    'neurologia_clinica',
    'neurocirurgia',
    'neuro_oncologia'
);

CREATE TABLE consultas (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cliente_id          UUID            NOT NULL REFERENCES clientes(id),
    pet_id              UUID            REFERENCES pets(id),
    veterinario_id      UUID            NOT NULL REFERENCES veterinarios(id),
    tipo                tipo_consulta   NOT NULL,
    status              status_consulta NOT NULL DEFAULT 'agendada',
    data_hora           TIMESTAMPTZ     NOT NULL,
    duracao_minutos     INT             NOT NULL DEFAULT 30,
    motivo              TEXT,
    observacoes         TEXT,
    google_event_id     VARCHAR(200),   -- ID do evento no Google Calendar
    email_enviado       BOOLEAN         NOT NULL DEFAULT FALSE,
    agendado_via        VARCHAR(50)     NOT NULL DEFAULT 'whatsapp',
    criado_em           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    atualizado_em       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────
-- 💬 Sessões de Conversa
-- Cada sessão = uma conversa contínua via WhatsApp
-- ─────────────────────────────────────────────────────────
CREATE TABLE sessoes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cliente_id      UUID            NOT NULL REFERENCES clientes(id),
    iniciada_em     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    encerrada_em    TIMESTAMPTZ,
    ativa           BOOLEAN         NOT NULL DEFAULT TRUE,
    contexto_json   JSONB           NOT NULL DEFAULT '{}'  -- estado do LangGraph
);

-- ─────────────────────────────────────────────────────────
-- 📨 Mensagens
-- Cada mensagem dentro de uma sessão
-- ─────────────────────────────────────────────────────────
CREATE TYPE origem_mensagem AS ENUM ('cliente', 'agente');

CREATE TABLE mensagens (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sessao_id       UUID            NOT NULL REFERENCES sessoes(id) ON DELETE CASCADE,
    cliente_id      UUID            NOT NULL REFERENCES clientes(id),
    origem          origem_mensagem NOT NULL,
    conteudo        TEXT            NOT NULL,
    bloqueada       BOOLEAN         NOT NULL DEFAULT FALSE,  -- guardrail bloqueou?
    motivo_bloqueio VARCHAR(100),
    tokens_usados   INT,
    latencia_ms     INT,
    criado_em       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────
-- 🧠 Documentos RAG (base de conhecimento da clínica)
-- ─────────────────────────────────────────────────────────
CREATE TABLE rag_documentos (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    nome_arquivo    VARCHAR(200)    NOT NULL,
    chunk_index     INT             NOT NULL,
    conteudo        TEXT            NOT NULL,
    embedding       vector(768),    -- dimensão do text-embedding-004
    metadata_json   JSONB           NOT NULL DEFAULT '{}',
    criado_em       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Índice vetorial para busca semântica eficiente
CREATE INDEX idx_rag_embedding
    ON rag_documentos
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ─────────────────────────────────────────────────────────
-- 🧠 Memória Vetorial por Cliente (histórico de conversas)
-- ─────────────────────────────────────────────────────────
CREATE TABLE memoria_clientes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cliente_id      UUID            NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    sessao_id       UUID            REFERENCES sessoes(id),
    resumo          TEXT            NOT NULL,  -- resumo semântico da interação
    embedding       vector(768),
    criado_em       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_memoria_cliente_embedding
    ON memoria_clientes
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);

-- ─────────────────────────────────────────────────────────
-- 🔄 Trigger: atualiza atualizado_em automaticamente
-- ─────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_veterinarios_updated
    BEFORE UPDATE ON veterinarios
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trg_consultas_updated
    BEFORE UPDATE ON consultas
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ─────────────────────────────────────────────────────────
-- 📊 Índices de performance para o dashboard
-- ─────────────────────────────────────────────────────────
CREATE INDEX idx_consultas_data        ON consultas(data_hora);
CREATE INDEX idx_consultas_status      ON consultas(status);
CREATE INDEX idx_consultas_veterinario ON consultas(veterinario_id);
CREATE INDEX idx_mensagens_sessao      ON mensagens(sessao_id);
CREATE INDEX idx_mensagens_cliente     ON mensagens(cliente_id);
CREATE INDEX idx_sessoes_cliente       ON sessoes(cliente_id);
CREATE INDEX idx_clientes_whatsapp     ON clientes(whatsapp);
