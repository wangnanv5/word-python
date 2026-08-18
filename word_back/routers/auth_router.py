from fastapi import APIRouter,  Depends
from typing import Optional
from fastapi import Depends,  status,  Header
from fastapi.security import  HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import or_

from word_back.database import get_db
from word_back.models import User
from word_back.crud import (
    create_user,
    get_user_by_username,
)
from word_back.schemas import *
from word_back.auth import (
    bearer_scheme,
    create_access_token,
    create_refresh_token,
    verify_password,
    get_user_from_refresh_token,
    revoke_if_valid
)

router = APIRouter()

# =====================
# 认证接口
# =====================

# 注册
@router.post("/register",response_model=HttpResponse)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    exists = (db.query(User).filter( or_(User.username == payload.username)).first())

    if exists:
        return HttpResponse(code=status.HTTP_409_CONFLICT,data=None, message="用户名已注册")

    create_user(db=db,password=payload.password,username=payload.username)
    return HttpResponse(code=0, data=None, message="注册成功")

# 登录
@router.post("/login",response_model=HttpResponse[Token])
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = get_user_by_username(db, payload.username)

    if not user:
        return HttpResponse(code=status.HTTP_401_UNAUTHORIZED,data=None,message="此用户名未注册")

    if not verify_password(payload.password, user.password_hash):
        return HttpResponse(code=status.HTTP_401_UNAUTHORIZED,data=None,message="用户名或密码错误")

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    result = Token(access_token=access_token, refresh_token=refresh_token)
    return HttpResponse(code=0,data=result,message="登录成功")

# 获取用户信息
@router.get("/info", response_model=HttpResponse)
def get_user_info():
    user_info = UserInfo(roles=["super"],realName = "小王")
    return HttpResponse(data=user_info.model_dump())

# 刷新 Access Token（使用 Refresh Token 换取新的 Access Token）
@router.post("/refresh", response_model=HttpResponse[Token])
def refresh_token(current_user: User = Depends(get_user_from_refresh_token)):
    new_access = create_access_token(current_user.id)
    new_refresh = create_refresh_token(current_user.id)

    result = Token(access_token=new_access, refresh_token=new_refresh)
    return HttpResponse(code=0,data=result,message="刷新成功")

# 退出登录：吊销当前 Access Token 与 Refresh Token
@router.post("/logout", response_model=HttpResponse)
def logout(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    refresh_token_raw: Optional[str] = Header(default=None, alias="X-Refresh-Token"),
):
    if credentials and credentials.scheme.lower() == "bearer":
        revoke_if_valid(credentials.credentials)
    if refresh_token_raw:
        revoke_if_valid(refresh_token_raw.strip())
    return HttpResponse(code=0, data=None, message="注销成功")