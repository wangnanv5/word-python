from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, List, Optional

# =====================
# 用户相关
# =====================

class UserCreate(BaseModel):
    # phone: str = Field(...,min_length=11,max_length=11,pattern=r"^1[3-9]\d{9}$",description="中国大陆手机号")
    # email: EmailStr
    username: str = Field(...,min_length=1,max_length=50,description="用户名")
    nickname: Optional[str] = Field(None,max_length=50,description="昵称")
    password: str = Field(...,min_length=1,max_length=128,description="密码，至少 6 位")

# 用户登录
class LoginRequest(BaseModel):
    username: str = Field(...,min_length=1,max_length=50,description="用户名")
    password: str = Field(...,min_length=1,max_length=128,description="密码，至少 6 位")

# 用户信息
class UserInfo(BaseModel):
    # —— BasicUserInfo 基础字段 ——
    roles: List[str] = []
    real_name: str = Field(alias="realName")
    # 上面是必须要的字段，下面是可选字段
    # userId: Union[str, int]
    # userName: str
    # nickName: Optional[str] = None
    # avatar: Optional[str] = None
    # permissions: List[str] = []

    # —— 你扩展的字段 ——
    # desc: str            # 用户描述
    # homePath: str        # 首页地址
    # token: str           # accessToken
    model_config = ConfigDict(validate_by_name=True,validate_by_alias=True)


# 登录返回
class Token(BaseModel):
    """登录/刷新后返回的双 token。"""
    access_token: str = Field(alias="accessToken", description="短期访问令牌，30 分钟有效")
    refresh_token: str = Field(alias="refreshToken", description="长期刷新令牌，7 天有效")
    token_type: str = Field(default="bearer", description="令牌类型")
    model_config = ConfigDict(validate_by_name=True,validate_by_alias=True)
    # user: UserOut