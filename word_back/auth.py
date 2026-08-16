import os
from datetime import datetime, timedelta,timezone

from typing import Optional

from jose import jwt, JWTError
from pwdlib import PasswordHash

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from word_back.database import get_db
from word_back.models import User


# 生产环境一定要改成环境变量
SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "jmjnwn0608!"
)

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 2400


pwd_context = PasswordHash.recommended()

bearer_scheme = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    校验明文密码和哈希密码是否匹配
    """
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(
    user_id: int,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    创建 JWT access token
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "exp": expire
    }

    token = jwt.encode(payload,SECRET_KEY,algorithm=ALGORITHM)

    return token


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    从 Authorization header 中解析 token，
    并返回当前登录用户。
    """
    auth_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未登录或 token 无效",
        headers={"WWW-Authenticate": "Bearer"}
    )

    if credentials is None:
        raise auth_exception

    if credentials.scheme.lower() != "bearer":
        raise auth_exception

    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("sub")

        if user_id is None:
            raise auth_exception

        user = db.get(User, int(user_id))

    except JWTError:
        raise auth_exception

    if user is None:
        raise auth_exception

    return user