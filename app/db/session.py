from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from core.config import get_settings

settings = get_settings()

# ── Engine assíncrono ────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    echo=settings.app_env == "development",  # loga SQL apenas em dev
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # verifica conexão antes de usar
)

# ── Session factory ──────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# ── Base para todos os models ────────────────────────────────
class Base(DeclarativeBase):
    pass

# ── Dependency para FastAPI ──────────────────────────────────
async def get_db() -> AsyncSession:
    """
    Uso em rotas FastAPI:
    async def minha_rota(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
