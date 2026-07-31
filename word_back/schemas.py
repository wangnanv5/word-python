from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Generic, Optional, TypeVar,Literal

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

class UserBase(BaseModel):
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
        description="姓名"
    )

    nickname: Optional[str] = Field(
        None,
        max_length=50,
        description="昵称"
    )


class UserCreate(UserBase):
    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="密码，至少 6 位"
    )


class UserOut(UserBase):
    id: int
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    phoneNumber: str = Field(
        ...,
        min_length=11,
        max_length=11,
        pattern=r"^1[3-9]\d{9}$"
    )

    password: str = Field(
        ...,
        min_length=6,
        max_length=128
    )


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# =====================
# 单词本相关
# =====================

class WordBookBase(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="单词本名称"
    )

    category: Literal["dictionary", "vocabulary"] = Field(
        default="vocabulary",
        description="dictionary: 词典, vocabulary: 生词本"
    )

    description: Optional[str] = Field(
        None,
        max_length=255,
        description="单词本描述"
    )


class WordBookCreate(WordBookBase):
    pass


class WordBookOut(WordBookBase):
    id: int
    user_id: int
    word_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =====================
# 单词相关
# =====================

class WordBase(BaseModel):
    spelling: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="英语拼写"
    )

    meaning: str = Field(
        ...,
        min_length=1,
        description="中文意思"
    )

    phonetic: Optional[str] = Field(
        None,
        max_length=100,
        description="音标"
    )

    audio_url: Optional[str] = Field(
        None,
        max_length=255,
        description="读音存储位置"
    )

    part_of_speech: str = Field(
        default="",
        max_length=20,
        description="词性，例如 n. v. adj."
    )

    example_sentence: Optional[str] = Field(
        None,
        description="英文例句"
    )

    example_translation: Optional[str] = Field(
        None,
        description="例句翻译"
    )

    difficulty: int = Field(
        default=1,
        ge=1,
        le=5,
        description="难度，1 到 5"
    )

    is_public: bool = Field(
        default=False,
        description="是否公共单词"
    )


class WordCreate(WordBase):
    pass


class WordOut(WordBase):
    id: int
    owner_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


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