import math
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Generic, Optional, TypeVar,Literal,List, Optional, Union

T = TypeVar("T")

class HttpResponse(BaseModel, Generic[T]):
    """
    统一响应结构，对应前端 interface HttpResponse<T>
    """
    code: int = 0          # 0 表示成功，其他表示失败
    data: Optional[T] = None
    message: str = ""

    model_config = ConfigDict(from_attributes=True)

# =====================
# 用户相关
# =====================

# 注册用户
class UserCreate(BaseModel):
    # phone: str = Field(
    #     ...,
    #     min_length=11,
    #     max_length=11,
    #     pattern=r"^1[3-9]\d{9}$",
    #     description="中国大陆手机号"
    # )

    # email: EmailStr

    username: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="用户名"
    )

    nickname: Optional[str] = Field(
        None,
        max_length=50,
        description="昵称"
    )

    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="密码，至少 6 位"
    )

# 用户登录
class LoginRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="用户名"
    )

    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="密码，至少 6 位"
    )

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
    access_token: str = Field(alias="accessToken")
    model_config = ConfigDict(validate_by_name=True,validate_by_alias=True)
    # token_type: str = "bearer"
    # user: UserOut


# =====================
# 单词相关
# =====================

class TranslationItem(BaseModel):
    pos: str = Field(description="词性")
    text: str = Field(description="中文释义")
    model_config = ConfigDict(from_attributes=True)

class PhraseItem(BaseModel):
    phrase: str = Field(description="短语")
    translation: Optional[str] = Field(description="短语翻译")
    model_config = ConfigDict(from_attributes=True)

class WordItem(BaseModel):
    """单个单词的完整信息"""
    id: int
    spelling: str = Field(description="单词拼写", example="apple")
    us: Optional[str] = Field(description="美式音标", example="/ˈæp.əl/")
    uk: Optional[str] = Field(description="英式音标", example="/ˈæp.əl/")
    audio_url: Optional[str] = Field(description="发音音频地址")
    translations: list[TranslationItem] = Field(default_factory=list, description="释义列表")
    phrases: list[PhraseItem] = Field(default_factory=list, description="短语列表")
    model_config = ConfigDict(from_attributes=True)

class PageMeta(BaseModel):
    """分页元信息"""
    page: int = Field(description="当前页码（从 1 开始）")
    page_size: int = Field(description="每页数量")
    total: int = Field(description="总记录数")
    total_pages: int = Field(description="总页数")
    has_next: bool = Field(description="是否有下一页")
    has_prev: bool = Field(description="是否有上一页")

class WordPageResponse(BaseModel):
    """分页结果"""
    items: list[WordItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20

    @property
    def total_pages(self) -> int:
        return math.ceil(self.total / self.page_size) if self.page_size > 0 else 0


# =====================
# 单词本-单词关系
# =====================

class AddWordToBookRequest(BaseModel):
    word_id: int


class BookWordOut(BaseModel):
    id: int
    book_id: int
    word_id: int
    mastery_level: int
    review_count: int
    last_review_at: Optional[datetime] = None
    next_review_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# =====================
# 单词本相关
# =====================

class WordBookBase(BaseModel):
    name: str = Field( ..., min_length=1, max_length=100, description="单词本名称")
    category: Literal["dictionary", "vocabulary"] = Field(
        default="vocabulary",
        description="dictionary: 词典, vocabulary: 生词本"
    )

    description: Optional[str] = Field(None,max_length=255,description="单词本描述")

class AddSystemBookToUser(BaseModel):
    system_book_id: int = Field(alias="systemBookId")
    model_config = ConfigDict(from_attributes=True,validate_by_name=True,validate_by_alias=True)

class MarkWordAsLearnedSchema(BaseModel):
    word_id: int = Field(alias="wordId")
    model_config = ConfigDict(from_attributes=True,validate_by_name=True,validate_by_alias=True)

class AddWordToVocabularySchema(BaseModel):
    word_id: int = Field(alias="wordId")
    mode: int = Field(alias="mode")
    model_config = ConfigDict(from_attributes=True,validate_by_name=True,validate_by_alias=True)

class WordBookOut(WordBookBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class WordBookListData(BaseModel):
    """系统单词本列表数据结构（支持分页/总数统计）"""
    items: List[WordBookOut]   # 原来的 data 数组内容
    total: int     