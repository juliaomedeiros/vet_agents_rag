import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Text, Boolean, Integer, DateTime,
    ForeignKey, Enum as SAEnum, ARRAY, JSON
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from db.session import Base
import enum


# ─────────────────────────────────────────────────────────────
# Enums Python (espelham os ENUMs do PostgreSQL)
# ─────────────────────────────────────────────────────────────
class StatusConsulta(str, enum.Enum):
    agendada    = "agendada"
    confirmada  = "confirmada"
    remarcada   = "remarcada"
    cancelada   = "cancelada"
    realizada   = "realizada"


class TipoConsulta(str, enum.Enum):
    clinica_geral       = "clinica_geral"
    clinica_cirurgica   = "clinica_cirurgica"
    ortopedia           = "ortopedia"
    neurologia_clinica  = "neurologia_clinica"
    neurocirurgia       = "neurocirurgia"
    neuro_oncologia     = "neuro_oncologia"


class OrigemMensagem(str, enum.Enum):
    cliente = "cliente"
    agente  = "agente"


# ─────────────────────────────────────────────────────────────
# 👨‍⚕️ Veterinario
# ─────────────────────────────────────────────────────────────
class Veterinario(Base):
    __tablename__ = "veterinarios"

    id                 : Mapped[uuid.UUID]        = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome               : Mapped[str]              = mapped_column(String(150), nullable=False)
    especialidades     : Mapped[list]             = mapped_column(ARRAY(String), default=[])
    email              : Mapped[str]              = mapped_column(String(150), unique=True, nullable=False)
    telefone           : Mapped[Optional[str]]    = mapped_column(String(20))
    google_calendar_id : Mapped[Optional[str]]    = mapped_column(String(200))
    ativo              : Mapped[bool]             = mapped_column(Boolean, default=True)
    criado_em          : Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    atualizado_em      : Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    consultas: Mapped[list["Consulta"]] = relationship("Consulta", back_populates="veterinario")


# ─────────────────────────────────────────────────────────────
# 🐾 Cliente
# ─────────────────────────────────────────────────────────────
class Cliente(Base):
    __tablename__ = "clientes"

    id              : Mapped[uuid.UUID]       = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    whatsapp        : Mapped[str]             = mapped_column(String(30), unique=True, nullable=False)
    nome            : Mapped[Optional[str]]   = mapped_column(String(150))
    email           : Mapped[Optional[str]]   = mapped_column(String(150))
    primeiro_contato: Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    ultimo_contato  : Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    ativo           : Mapped[bool]            = mapped_column(Boolean, default=True)

    pets      : Mapped[list["Pet"]]     = relationship("Pet", back_populates="cliente")
    sessoes   : Mapped[list["Sessao"]]  = relationship("Sessao", back_populates="cliente")
    consultas : Mapped[list["Consulta"]]= relationship("Consulta", back_populates="cliente")
    memorias  : Mapped[list["MemoriaCliente"]] = relationship("MemoriaCliente", back_populates="cliente")


# ─────────────────────────────────────────────────────────────
# 🐶 Pet
# ─────────────────────────────────────────────────────────────
class Pet(Base):
    __tablename__ = "pets"

    id              : Mapped[uuid.UUID]       = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id      : Mapped[uuid.UUID]       = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"))
    nome            : Mapped[str]             = mapped_column(String(100), nullable=False)
    especie         : Mapped[Optional[str]]   = mapped_column(String(50))
    raca            : Mapped[Optional[str]]   = mapped_column(String(100))
    data_nascimento : Mapped[Optional[datetime]] = mapped_column(DateTime)
    observacoes     : Mapped[Optional[str]]   = mapped_column(Text)
    criado_em       : Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    cliente  : Mapped["Cliente"]        = relationship("Cliente", back_populates="pets")
    consultas: Mapped[list["Consulta"]] = relationship("Consulta", back_populates="pet")


# ─────────────────────────────────────────────────────────────
# 📅 Consulta
# ─────────────────────────────────────────────────────────────
class Consulta(Base):
    __tablename__ = "consultas"

    id               : Mapped[uuid.UUID]          = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id       : Mapped[uuid.UUID]          = mapped_column(ForeignKey("clientes.id"))
    pet_id           : Mapped[Optional[uuid.UUID]]= mapped_column(ForeignKey("pets.id"))
    veterinario_id   : Mapped[uuid.UUID]          = mapped_column(ForeignKey("veterinarios.id"))
    tipo             : Mapped[TipoConsulta]        = mapped_column(SAEnum(TipoConsulta), nullable=False)
    status           : Mapped[StatusConsulta]      = mapped_column(SAEnum(StatusConsulta), default=StatusConsulta.agendada)
    data_hora        : Mapped[datetime]            = mapped_column(DateTime(timezone=True), nullable=False)
    duracao_minutos  : Mapped[int]                 = mapped_column(Integer, default=30)
    motivo           : Mapped[Optional[str]]       = mapped_column(Text)
    observacoes      : Mapped[Optional[str]]       = mapped_column(Text)
    google_event_id  : Mapped[Optional[str]]       = mapped_column(String(200))
    email_enviado    : Mapped[bool]                = mapped_column(Boolean, default=False)
    agendado_via     : Mapped[str]                 = mapped_column(String(50), default="whatsapp")
    criado_em        : Mapped[datetime]            = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    atualizado_em    : Mapped[datetime]            = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    cliente     : Mapped["Cliente"]     = relationship("Cliente", back_populates="consultas")
    pet         : Mapped[Optional["Pet"]] = relationship("Pet", back_populates="consultas")
    veterinario : Mapped["Veterinario"] = relationship("Veterinario", back_populates="consultas")


# ─────────────────────────────────────────────────────────────
# 💬 Sessão de Conversa
# ─────────────────────────────────────────────────────────────
class Sessao(Base):
    __tablename__ = "sessoes"

    id           : Mapped[uuid.UUID]       = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id   : Mapped[uuid.UUID]       = mapped_column(ForeignKey("clientes.id"))
    iniciada_em  : Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    encerrada_em : Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ativa        : Mapped[bool]            = mapped_column(Boolean, default=True)
    contexto_json: Mapped[dict]            = mapped_column(JSONB, default={})

    cliente   : Mapped["Cliente"]          = relationship("Cliente", back_populates="sessoes")
    mensagens : Mapped[list["Mensagem"]]   = relationship("Mensagem", back_populates="sessao")
    memorias  : Mapped[list["MemoriaCliente"]] = relationship("MemoriaCliente", back_populates="sessao")


# ─────────────────────────────────────────────────────────────
# 📨 Mensagem
# ─────────────────────────────────────────────────────────────
class Mensagem(Base):
    __tablename__ = "mensagens"

    id              : Mapped[uuid.UUID]       = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sessao_id       : Mapped[uuid.UUID]       = mapped_column(ForeignKey("sessoes.id", ondelete="CASCADE"))
    cliente_id      : Mapped[uuid.UUID]       = mapped_column(ForeignKey("clientes.id"))
    origem          : Mapped[OrigemMensagem]  = mapped_column(SAEnum(OrigemMensagem, name="origem_mensagem"), nullable=False)
    conteudo        : Mapped[str]             = mapped_column(Text, nullable=False)
    bloqueada       : Mapped[bool]            = mapped_column(Boolean, default=False)
    motivo_bloqueio : Mapped[Optional[str]]   = mapped_column(String(100))
    tokens_usados   : Mapped[Optional[int]]   = mapped_column(Integer)
    latencia_ms     : Mapped[Optional[int]]   = mapped_column(Integer)
    criado_em       : Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    sessao: Mapped["Sessao"] = relationship("Sessao", back_populates="mensagens")


# ─────────────────────────────────────────────────────────────
# 🧠 Documento RAG
# ─────────────────────────────────────────────────────────────
class RagDocumento(Base):
    __tablename__ = "rag_documentos"

    id           : Mapped[uuid.UUID]       = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome_arquivo : Mapped[str]             = mapped_column(String(200), nullable=False)
    chunk_index  : Mapped[int]             = mapped_column(Integer, nullable=False)
    conteudo     : Mapped[str]             = mapped_column(Text, nullable=False)
    embedding    : Mapped[Optional[list]]  = mapped_column(Vector(3072))
    metadata_json: Mapped[dict]            = mapped_column(JSONB, default={})
    criado_em    : Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


# ─────────────────────────────────────────────────────────────
# 🧠 Memória Vetorial por Cliente
# ─────────────────────────────────────────────────────────────
class MemoriaCliente(Base):
    __tablename__ = "memoria_clientes"

    id         : Mapped[uuid.UUID]          = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id : Mapped[uuid.UUID]          = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"))
    sessao_id  : Mapped[Optional[uuid.UUID]]= mapped_column(ForeignKey("sessoes.id"))
    resumo     : Mapped[str]                = mapped_column(Text, nullable=False)
    embedding  : Mapped[Optional[list]]     = mapped_column(Vector(3072))
    criado_em  : Mapped[datetime]           = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="memorias")
    sessao : Mapped[Optional["Sessao"]] = relationship("Sessao", back_populates="memorias")
