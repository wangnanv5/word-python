"""
服务端 Token 吊销存储（黑名单）。

JWT 本身无状态，无法主动失效。这里用一个独立的 SQLite 表记录已吊销的
token jti，并在校验时查询。配合短效 Access Token + Refresh Token 机制，
可实现：登出即失效、被盗 token 窗口期短。

表独立存放于 token_blacklist.db，避免污染业务库；也可改为复用业务库。
"""
import threading
from datetime import datetime, timezone

from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

_engine = None
_SessionLocal = None
_lock = threading.Lock()


def _get_session():
    """懒初始化黑名单库的连接与会话（线程安全）。"""
    global _engine, _SessionLocal
    if _SessionLocal is None:
        with _lock:
            if _SessionLocal is None:
                _engine = create_engine(
                    "sqlite:///./token_blacklist.db",
                    connect_args={"check_same_thread": False},
                )
                Base.metadata.create_all(_engine)
                _SessionLocal = sessionmaker(bind=_engine, autoflush=False)
    return _SessionLocal()


class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    jti = Column(String(64), primary_key=True)
    # token 原本的过期时间，用于过期后自动清理行
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


def revoke_token(jti: str, expires_at: datetime) -> None:
    """将某个 jti 加入黑名单。"""
    if not jti:
        return
    session = _get_session()
    try:
        session.merge(RevokedToken(jti=jti, expires_at=expires_at))
        session.commit()
    finally:
        session.close()


def is_token_revoked(jti: str) -> bool:
    """判断 jti 是否已被吊销。"""
    if not jti:
        return False
    session = _get_session()
    try:
        exists = session.get(RevokedToken, jti) is not None
        return exists
    finally:
        session.close()


def cleanup_expired() -> None:
    """清理已过期的吊销记录，避免表无限增长。可定时调用。"""
    now = datetime.now(timezone.utc)
    session = _get_session()
    try:
        session.query(RevokedToken).filter(RevokedToken.expires_at < now).delete()
        session.commit()
    finally:
        session.close()
