from typing import List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_

from word_back.database import get_db

from word_back.models import User, WordBook

from word_back.crud import (
    create_user,
    get_user_by_phone,
    create_word_book,
    get_word_books_by_user,
    get_word_book_by_id,
    create_word,
    get_word_by_id,
    get_word_by_spelling,
    add_word_to_book,
    get_words_in_book,
    get_book_word
)

from word_back.schemas import (
    UserCreate,
    UserOut,
    HttpResponse,
    LoginRequest,
    Token,
    WordBookCreate,
    WordBookOut,
    WordCreate,
    WordOut,
    AddWordToBookRequest,
    BookWordOut
)

from word_back.auth import (
    create_access_token,
    verify_password,
    get_current_user
)


app = FastAPI(
    title="背单词 API",
    description="用户、单词本、单词接口",
    version="1.0.0"
)


# 允许跨域
# 生产环境不要随便用 *，要改成你的前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================
# 工具函数
# =====================

def get_user_book_or_404(db: Session,book_id: int,user_id: int) -> WordBook:
    """
    获取当前用户的单词本。
    如果不存在，或者不属于当前用户，返回 404。
    """
    book = get_word_book_by_id(db, book_id)

    if not book or book.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="单词本不存在"
        )

    return book


# =====================
# 认证接口
# =====================

@app.post(
    "/api/auth/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    tags=["认证"]
)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """
    用户注册
    """
    exists = (
        db.query(User)
        .filter(
            or_(
                User.username == payload.username
            )
        )
        .first()
    )

    if exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已注册"
        )

    user = create_user(
        db=db,
        password=payload.password,
        username=payload.username,
    )

    return user


@app.post(
    "/api/auth/login",
    response_model=Token,
    tags=["认证"]
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    用户登录

    返回 JWT token。
    前端之后请求需要携带：

    Authorization: Bearer <token>
    """
    user = get_user_by_phone(db, payload.phone)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="手机号或密码错误"
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="手机号或密码错误"
        )

    access_token = create_access_token(user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }


@app.get(
    "/api/users/me",
    response_model=UserOut,
    tags=["用户"]
)
def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    获取当前登录用户信息
    """
    return current_user


# =====================
# 单词本接口
# =====================

@app.post(
    "/api/word-books",
    response_model=WordBookOut,
    status_code=status.HTTP_201_CREATED,
    tags=["单词本"]
)
def create_book(
    payload: WordBookCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建单词本
    """
    book = create_word_book(
        db=db,
        user_id=current_user.id,
        name=payload.name,
        category=payload.category,
        description=payload.description
    )

    return book


@app.get(
    "/api/word-books",
    response_model=List[WordBookOut],
    tags=["单词本"]
)
def list_books(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取当前用户的所有单词本
    """
    return get_word_books_by_user(db, current_user.id)


@app.get(
    "/api/word-books/{book_id}/words",
    response_model=List[WordOut],
    tags=["单词本"]
)
def list_words_in_book(
    book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取某个单词本里的所有单词
    """
    get_user_book_or_404(db, book_id, current_user.id)

    return get_words_in_book(db, book_id)


# =====================
# 单词接口
# =====================

@app.post(
    "/api/words",
    response_model=WordOut,
    status_code=status.HTTP_201_CREATED,
    tags=["单词"]
)
def create_word_endpoint(
    payload: WordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建单词，但不加入某个单词本
    """
    existing_word = get_word_by_spelling(
        db,
        spelling=payload.spelling,
        part_of_speech=payload.part_of_speech
    )

    if existing_word:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="单词已存在"
        )

    word = create_word(
        db=db,
        spelling=payload.spelling,
        meaning=payload.meaning,
        phonetic=payload.phonetic,
        audio_url=payload.audio_url,
        part_of_speech=payload.part_of_speech,
        example_sentence=payload.example_sentence,
        example_translation=payload.example_translation,
        difficulty=payload.difficulty,
        is_public=payload.is_public,
        owner_id=current_user.id
    )

    return word


@app.post(
    "/api/word-books/{book_id}/words",
    response_model=BookWordOut,
    status_code=status.HTTP_201_CREATED,
    tags=["单词本"]
)
def add_existing_word_to_book(
    book_id: int,
    payload: AddWordToBookRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    把已有单词加入某个单词本
    """
    get_user_book_or_404(db, book_id, current_user.id)

    word = get_word_by_id(db, payload.word_id)

    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="单词不存在"
        )

    existing = get_book_word(db, book_id, payload.word_id)

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="单词已经在单词本里"
        )

    return add_word_to_book(db, book_id, payload.word_id)


@app.post(
    "/api/word-books/{book_id}/words/new",
    response_model=WordOut,
    status_code=status.HTTP_201_CREATED,
    tags=["单词本"]
)
def create_and_add_word_to_book(
    book_id: int,
    payload: WordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建新单词，并加入某个单词本。

    如果单词已经存在，则直接加入单词本。
    """
    get_user_book_or_404(db, book_id, current_user.id)

    word = get_word_by_spelling(
        db,
        spelling=payload.spelling,
        part_of_speech=payload.part_of_speech
    )

    if not word:
        word = create_word(
            db=db,
            spelling=payload.spelling,
            meaning=payload.meaning,
            phonetic=payload.phonetic,
            audio_url=payload.audio_url,
            part_of_speech=payload.part_of_speech,
            example_sentence=payload.example_sentence,
            example_translation=payload.example_translation,
            difficulty=payload.difficulty,
            is_public=payload.is_public,
            owner_id=current_user.id
        )

    add_word_to_book(db, book_id, word.id)

    return word

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5777, reload=True)
    # uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4