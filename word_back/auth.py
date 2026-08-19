import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from jose import jwt, JWTError
from pwdlib import PasswordHash

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from word_back.database import get_db
from word_back.models import User
from word_back.token_store import revoke_token


# 生产环境一定要改成环境变量（务必设置，缺失则启动失败）
SECRET_KEY = "SECRET_KEY"
# SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "环境变量 SECRET_KEY 未设置。请在启动前通过环境变量配置 JWT 签名密钥，"
        "例如：export SECRET_KEY='你的强随机密钥'"
    )

ALGORITHM = "HS256"

# Access Token：短期有效，用于普通接口鉴权
ACCESS_TOKEN_EXPIRE_MINUTES = 10
# Refresh Token：长期有效，仅用于换取新的 Access Token
REFRESH_TOKEN_EXPIRE_DAYS = 7


class TokenType(str, Enum):
    """JWT 中的 token 类型声明，避免 refresh token 被当成 access token 使用。"""
    ACCESS = "access"
    REFRESH = "refresh"


pwd_context = PasswordHash.recommended()

bearer_scheme = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    校验明文密码和哈希密码是否匹配
    """
    return pwd_context.verify(plain_password, password_hash)


def _create_token(
    user_id: int,
    token_type: TokenType,
    expires_delta: timedelta,
) -> str:
    """生成带 type 声明与唯一 jti 的 JWT（jti 用于服务端吊销）。"""
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(user_id),
        "type": token_type.value,
        "jti": str(uuid.uuid4()),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: int) -> str:
    """创建短期 Access Token。"""
    return _create_token(
        user_id,
        TokenType.ACCESS,
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int) -> str:
    """创建长期 Refresh Token。"""
    return _create_token(
        user_id,
        TokenType.REFRESH,
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


def _decode_token(
    token: str,
    expected_type: TokenType,
) -> dict:
    """
    解码并校验 JWT：
    - 签名/过期由 jose 校验
    - 额外校验 type 声明，防止 refresh token 被用作 access token
    - 校验是否被服务端吊销（登出黑名单）
    """
    from word_back.token_store import is_token_revoked

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    if payload.get("type") != expected_type.value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token 类型不匹配",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jti = payload.get("jti")
    if jti and is_token_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token 已被吊销",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    从 Authorization header 中解析 Access Token，
    并返回当前登录用户。已吊销的 token 会被拒绝。
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或 token 无效",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _decode_token(credentials.credentials, TokenType.ACCESS)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token 缺少用户标识",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, int(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_user_from_refresh_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    校验 Refresh Token 并返回对应用户，供刷新接口使用。
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = _decode_token(credentials.credentials, TokenType.REFRESH)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token 缺少用户标识",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, int(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def revoke_if_valid(raw_token: str) -> None:
    """尝试解码 token 并将 jti 加入黑名单，解码失败则忽略。"""
    try:
        payload = jwt.decode(
            raw_token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False}
        )
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            revoke_token(jti, datetime.fromtimestamp(exp, tz=timezone.utc))
    except JWTError:
        pass