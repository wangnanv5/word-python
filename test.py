# main.py
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt, JWTError

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, ConfigDict, Field
from passlib.context import CryptContext

# ========== 配置 ==========
SECRET_KEY = "your-secret-key-change-me"   # ⚠️ 生产环境务必用环境变量
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
app = FastAPI()


# ========== 数据模型（对齐前端字段名） ==========
class LoginParams(BaseModel):
    username: str
    password: str


class LoginResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    access_token: str = Field(alias="accessToken")   # 序列化后变成 accessToken


class RefreshTokenResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    data: str
    status: int


# 模拟数据库用户
fake_users_db = {
    "test": {
        "id": 1,
        "username": "test",
        "hashed_password": pwd_context.hash("123456"),
    }
}


# ========== Token 工具 ==========
def create_token(user_id: int, expires_delta: timedelta) -> str:
    """生成 JWT"""
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """解析并校验 JWT（过期/签名错误会抛异常）"""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# ========== 依赖：解析当前登录用户 ==========
def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="无效凭证")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效 Token")
    return user_id


# ========== 接口 ==========
@app.post("/login", response_model=LoginResult)
def login(params: LoginParams, response: Response):
    # 1. 校验账号密码
    user = fake_users_db.get(params.username)
    if not user or not pwd_context.verify(params.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user_id = user["id"]

    # 2. 生成 access token（短期）
    access_token = create_token(
        user_id=user_id,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    # 3. 生成 refresh token（长期），写入 httpOnly Cookie
    refresh_token = create_token(
        user_id=user_id,
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,    # JS 读不到，防 XSS
        secure=True,      # 生产 HTTPS 下开启
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
    )

    # 4. 返回 { accessToken: "..." }
    return LoginResult(accessToken=access_token)


@app.post("/refresh", response_model=RefreshTokenResult)
def refresh(request: Request):
    # 从 Cookie 读取 refresh token
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        return RefreshTokenResult(data="", status=401)

    try:
        payload = decode_token(refresh_token)
        user_id = payload.get("sub")
    except jwt.InvalidTokenError:
        return RefreshTokenResult(data="", status=401)

    # 签发新的 access token
    new_access_token = create_token(
        user_id=int(user_id),
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return RefreshTokenResult(data=new_access_token, status=200)


@app.get("/me")
def read_me(user_id: str = Depends(get_current_user)):
    """受保护接口示例：前端需在 Header 带 Authorization: Bearer <accessToken>"""
    return {"user_id": user_id}