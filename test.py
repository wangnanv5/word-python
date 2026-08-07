"""
main.py — FastAPI 应用入口
====================================
提供以下接口：

  GET  /api/words                    — 分页获取单词（默认从系统词典取）
  GET  /api/words/{word_id}          — 获取单个单词详情
  GET  /api/wordbooks                — 获取当前用户的所有单词本
  GET  /api/wordbooks/{book_id}/words — 分页获取指定单词本中的单词
  GET  /api/words/search             — 跨单词本搜索单词

认证说明：
  当前使用简化的 user_id 依赖注入（从 Header 读取 X-User-Id）
  生产环境请替换为真实的 JWT / Session 认证
"""

from __future__ import annotations

import math
from typing import Optional, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session, selectinload

from models import (
    Word,
    WordTranslation,
    WordPhrase,
    SystemDictionary,
    SystemDictionaryWord,
    WordBook,
    BookWord,
)
from wordbook_service import (
    WordBookService,
    SYSTEM_DICTIONARY_VIRTUAL_ID,
)

# ============================================================
# 数据库配置（生产环境请改为环境变量 / 配置文件）
# ============================================================
DATABASE_URL = "sqlite:///./word_back.db"
# 示例 PostgreSQL:
# DATABASE_URL = "postgresql+psycopg2://user:pass@localhost:5432/wordback"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    pool_pre_ping=True,
)

# ============================================================
# FastAPI 实例
# ============================================================
app = FastAPI(
    title="WordBack API",
    description="单词本系统后端接口",
    version="1.0.0",
)

# CORS（开发阶段允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境改为具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 依赖注入
# ============================================================
def get_db():
    """每次请求创建独立 Session，请求结束后自动关闭"""
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()


def get_current_user_id(
    x_user_id: Optional[int] = Header(default=None, description="当前用户 ID（Header: X-User-Id）"),
) -> int:
    """
    获取当前登录用户 ID

    ⚠️ 简化实现：直接从 Header 读取
    生产环境应改为 JWT 解码 / Session 校验
    """
    if x_user_id is None:
        # 开发阶段给个默认值，方便调试
        return 1
        # 生产环境请改为：
        # raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    return x_user_id


# ============================================================
# Pydantic 响应模型（接口文档 + 序列化控制）
# ============================================================
class TranslationItem(BaseModel):
    pos: str = Field(description="词性", example="n.")
    text: str = Field(description="中文释义", example="苹果；苹果公司")

    class Config:
        from_attributes = True


class PhraseItem(BaseModel):
    phrase: str = Field(description="短语", example="apple pie")
    translation: Optional[str] = Field(description="短语翻译", example="苹果派")

    class Config:
        from_attributes = True


class WordItem(BaseModel):
    """单个单词的完整信息"""
    id: int
    spelling: str = Field(description="单词拼写", example="apple")
    us: Optional[str] = Field(description="美式音标", example="/ˈæp.əl/")
    uk: Optional[str] = Field(description="英式音标", example="/ˈæp.əl/")
    audio_url: Optional[str] = Field(description="发音音频地址")
    translations: list[TranslationItem] = Field(default_factory=list, description="释义列表")
    phrases: list[PhraseItem] = Field(default_factory=list, description="短语列表")

    class Config:
        from_attributes = True


class PageMeta(BaseModel):
    """分页元信息"""
    page: int = Field(description="当前页码（从 1 开始）")
    page_size: int = Field(description="每页数量")
    total: int = Field(description="总记录数")
    total_pages: int = Field(description="总页数")
    has_next: bool = Field(description="是否有下一页")
    has_prev: bool = Field(description="是否有上一页")


class WordPageResponse(BaseModel):
    """分页获取单词的响应体"""
    items: list[WordItem] = Field(description="当前页的单词列表")
    meta: PageMeta = Field(description="分页信息")


class WordBookBrief(BaseModel):
    """单词本简要信息"""
    id: int
    name: str
    category: str
    description: Optional[str] = None
    is_system: bool
    word_count: int = 0

    class Config:
        from_attributes = True


# ============================================================
# 内部查询函数（复用 wordbook_service 的逻辑）
# ============================================================
def _build_page_meta(page: int, page_size: int, total: int) -> PageMeta:
    """构造分页元信息"""
    total_pages = math.ceil(total / page_size) if page_size > 0 else 0
    return PageMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


def _word_to_item(word: Word) -> WordItem:
    """ORM Word → Pydantic WordItem"""
    return WordItem(
        id=word.id,
        spelling=word.spelling,
        us=word.us,
        uk=word.uk,
        audio_url=word.audio_url,
        translations=[
            TranslationItem(pos=t.part_of_speech, text=t.translation)
            for t in word.translations
        ],
        phrases=[
            PhraseItem(phrase=p.phrase, translation=p.translation)
            for p in word.phrases
        ],
    )


# ============================================================
# 接口 1：分页获取单词（核心接口）
# ============================================================
@app.get(
    "/api/words",
    response_model=WordPageResponse,
    summary="分页获取单词",
    description="""
前端每次请求一批单词（如 100 个），支持：
- 指定从哪个单词本取（book_id，默认系统词典）
- 按关键词过滤（前缀匹配）
- 按词性过滤
- 排序方式（字母序 / 时间倒序）
    """,
    tags=["单词"],
)
def list_words(
    # ---- 分页参数 ----
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=100, ge=1, le=500, description="每页数量，最大 500"),

    # ---- 过滤参数 ----
    keyword: Optional[str] = Query(default=None, description="关键词（前缀匹配单词拼写）", examples=["app"]),
    part_of_speech: Optional[str] = Query(
        default=None,
        description="词性过滤（如 n, v, adj, adv）",
        examples=["n"],
    ),

    # ---- 来源参数 ----
    book_id: Optional[int] = Query(
        default=None,
        description="单词本 ID。不传=系统词典；-1=系统词典；正数=用户单词本",
    ),

    # ---- 排序 ----
    sort: Literal["spelling", "created_at"] = Query(
        default="spelling",
        description="排序方式：spelling=字母序，created_at=最新添加",
    ),

    # ---- 依赖 ----
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    📖 核心接口：前端分页拉取单词

    典型调用：
      GET /api/words?page=1&page_size=100
      GET /api/words?page=2&page_size=100&keyword=app
      GET /api/words?book_id=5&page=1&page_size=50
    """
    # 确定目标单词本
    target_book_id = SYSTEM_DICTIONARY_VIRTUAL_ID if book_id is None else book_id

    # 使用 WordBookService 统一处理（自动识别系统词典 vs 用户单词本）
    service = WordBookService(db)

    try:
        result = service.get_wordbook_words(
            user_id=user_id,
            book_id=target_book_id,
            page=page,
            page_size=page_size,
            keyword=keyword,
            part_of_speech=part_of_speech,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    # 排序（Service 默认按 spelling 排，created_at 需要在接口层处理）
    items = result.items
    if sort == "created_at":
        # 对于 created_at 排序，需要直接查 BookWord 的 created_at
        if target_book_id == SYSTEM_DICTIONARY_VIRTUAL_ID:
            # 系统词典按 Word.created_at 倒序
            word_ids = [w.id for w in items]
            if word_ids:
                stmt = (
                    select(Word)
                    .where(Word.id.in_(word_ids))
                    .options(
                        selectinload(Word.translations),
                        selectinload(Word.phrases),
                    )
                    .order_by(Word.created_at.desc())
                )
                words = db.execute(stmt).scalars().all()
                items = [_word_to_item(w) for w in words]
        else:
            # 用户单词本按 BookWord.created_at 倒序
            stmt = (
                select(Word)
                .join(BookWord, BookWord.word_id == Word.id)
                .where(BookWord.book_id == target_book_id)
                .options(
                    selectinload(Word.translations),
                    selectinload(Word.phrases),
                )
                .order_by(BookWord.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            if keyword:
                stmt = stmt.where(Word.spelling.ilike(f"{keyword}%"))
            words = db.execute(stmt).scalars().all()
            items = [_word_to_item(w) for w in words]

    return WordPageResponse(
        items=items,
        meta=_build_page_meta(page, page_size, result.total),
    )


# ============================================================
# 接口 2：获取单个单词详情
# ============================================================
@app.get(
    "/api/words/{word_id}",
    response_model=WordItem,
    summary="获取单词详情",
    description="返回单词的完整信息（拼写、音标、全部释义、全部短语）",
    tags=["单词"],
)
def get_word_detail(
    word_id: int,
    db: Session = Depends(get_db),
):
    """
    📖 获取单个单词的完整详情

    典型调用：
      GET /api/words/42
    """
    stmt = (
        select(Word)
        .where(Word.id == word_id)
        .options(
            selectinload(Word.translations),
            selectinload(Word.phrases),
        )
    )
    word = db.execute(stmt).scalar_one_or_none()

    if word is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"单词 ID={word_id} 不存在",
        )

    return _word_to_item(word)


# ============================================================
# 接口 3：获取当前用户的所有单词本
# ============================================================
@app.get(
    "/api/wordbooks",
    response_model=list[WordBookBrief],
    summary="获取用户的所有单词本",
    description="返回系统词典 + 用户自建单词本列表",
    tags=["单词本"],
)
def list_wordbooks(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    📖 获取单词本列表

    典型调用：
      GET /api/wordbooks
    """
    service = WordBookService(db)
    books = service.list_user_wordbooks(user_id=user_id)

    return [
        WordBookBrief(
            id=b.id,
            name=b.name,
            category=b.category,
            description=b.description,
            is_system=b.is_system,
            word_count=b.word_count,
        )
        for b in books
    ]


# ============================================================
# 接口 4：分页获取指定单词本中的单词
# ============================================================
@app.get(
    "/api/wordbooks/{book_id}/words",
    response_model=WordPageResponse,
    summary="分页获取指定单词本中的单词",
    description="从某个单词本（系统词典或用户单词本）中分页取单词",
    tags=["单词本"],
)
def list_wordbook_words(
    book_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    keyword: Optional[str] = Query(default=None, description="关键词前缀搜索"),
    part_of_speech: Optional[str] = Query(default=None, description="词性过滤"),
    sort: Literal["spelling", "created_at"] = Query(default="spelling"),

    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    📖 从指定单词本分页取单词

    典型调用：
      GET /api/wordbooks/-1/words?page=1&page_size=100   ← 系统词典
      GET /api/wordbooks/5/words?page=2&page_size=50     ← 用户单词本
    """
    service = WordBookService(db)

    try:
        result = service.get_wordbook_words(
            user_id=user_id,
            book_id=book_id,
            page=page,
            page_size=page_size,
            keyword=keyword,
            part_of_speech=part_of_speech,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    items = result.items
    # created_at 排序
    if sort == "created_at" and book_id != SYSTEM_DICTIONARY_VIRTUAL_ID:
        stmt = (
            select(Word)
            .join(BookWord, BookWord.word_id == Word.id)
            .where(BookWord.book_id == book_id)
            .options(
                selectinload(Word.translations),
                selectinload(Word.phrases),
            )
            .order_by(BookWord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        if keyword:
            stmt = stmt.where(Word.spelling.ilike(f"{keyword}%"))
        words = db.execute(stmt).scalars().all()
        items = [_word_to_item(w) for w in words]

    return WordPageResponse(
        items=items,
        meta=_build_page_meta(page, page_size, result.total),
    )


# ============================================================
# 接口 5：跨单词本搜索
# ============================================================
@app.get(
    "/api/search/words",
    response_model=WordPageResponse,
    summary="搜索单词",
    description="跨所有单词本（系统词典 + 用户单词本）搜索单词",
    tags=["单词"],
)
def search_words(
    keyword: str = Query(..., min_length=1, description="搜索关键词", examples=["apple"]),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    scope: Literal["all", "system", "user"] = Query(
        default="all",
        description="搜索范围：all=全部，system=仅系统词典，user=仅用户单词本",
    ),

    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """
    📖 搜索单词

    典型调用：
      GET /api/words/search?keyword=apple
      GET /api/words/search?keyword=app&scope=system&page=1&page_size=20
    """
    service = WordBookService(db)
    result = service.search_words(
        user_id=user_id,
        keyword=keyword,
        page=page,
        page_size=page_size,
        scope=scope,
    )

    # search_words 返回的 items 是 WordView dataclass，需转为 WordItem
    items = [
        WordItem(
            id=w.id,
            spelling=w.spelling,
            us=w.us,
            uk=w.uk,
            audio_url=w.audio_url,
            translations=[TranslationItem(pos=t["pos"], text=t["text"]) for t in w.translations],
            phrases=[PhraseItem(phrase=p["phrase"], translation=p["translation"]) for p in w.phrases],
        )
        for w in result.items
    ]
    return WordPageResponse(
        items=items,
        meta=_build_page_meta(page, page_size, result.total),
    )


# ============================================================
# 启动入口
# ============================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 开发模式热重载
    )


import os
import json
from sqlalchemy.orm import Session
# 请确保导入了你的模型和常量
# from models import Word, WordBook, BookWord, WordTranslation, WordPhrase
# from constants import CATEGORY_VOCABULARY 

def import_words_and_build_book(file_path: str, user_id: int, session: Session):
    # 1. 从文件路径中提取文件名（不含后缀）作为单词本名称
    base_name = os.path.basename(file_path)
    book_name = os.path.splitext(base_name)[0]

    # 2. 查找或创建单词本 (利用 user_id + name 的唯一约束)
    word_book = session.query(WordBook).filter_by(user_id=user_id, name=book_name).first()
    if not word_book:
        word_book = WordBook(
            user_id=user_id,
            name=book_name,
            category=CATEGORY_VOCABULARY,  # 用户自建单词本通常归类为 vocabulary
            description=f"从文件 {base_name} 导入的单词本"
        )
        session.add(word_book)
        session.flush()  # 必须 flush 以获取数据库生成的 word_book.id

    # 3. 读取 JSON 数据
    with open(file_path, 'r', encoding='utf-8') as f:
        words_data = json.load(f)

    # ================= 性能优化区 =================
    # 提取所有需要处理的 spelling
    spellings = [item.get('spelling') for item in words_data if item.get('spelling')]
    
    # 批量查询数据库中已存在的 Word，构建字典映射，避免循环内逐条查询 (解决 N+1 问题)
    existing_words = session.query(Word).filter(Word.spelling.in_(spellings)).all()
    word_map = {w.spelling: w for w in existing_words}

    # 批量查询该单词本已经关联的 word_id，存入集合，避免重复插入触发唯一约束报错
    existing_book_word_ids = set(
        bw.word_id for bw in session.query(BookWord.word_id).filter_by(book_id=word_book.id).all()
    )
    # ==============================================

    # 4. 遍历处理单词及关联关系
    for item in words_data:
        spelling = item.get('spelling')
        if not spelling:
            continue

        # 4.1 处理 Word 主表及子表 (释义、短语)
        if spelling not in word_map:
            new_word = Word(
                spelling=spelling,
                us=item.get('us'),
                uk=item.get('uk'),
                audio_url=item.get('audio_url')
            )
            session.add(new_word)
            session.flush()  # 获取 new_word.id

            # 添加释义 (请根据你实际的 JSON 结构调整字段名)
            for trans in item.get('translations', []):
                session.add(WordTranslation(
                    word_id=new_word.id,
                    part_of_speech=trans.get('part_of_speech', ''),
                    translation=trans.get('translation', '')
                ))

            # 添加短语
            for phrase in item.get('phrases', []):
                session.add(WordPhrase(
                    word_id=new_word.id,
                    phrase=phrase.get('phrase', ''),
                    translation=phrase.get('translation', '')
                ))

            # 将新单词加入映射表
            word_map[spelling] = new_word

        word = word_map[spelling]

        # 4.2 处理 BookWord 关联关系
        # 如果该单词还没加入当前单词本，则创建关联
        if word.id not in existing_book_word_ids:
            session.add(BookWord(book_id=word_book.id, word_id=word.id))
            # 加入集合，防止 JSON 文件内部有重复单词导致唯一约束冲突
            existing_book_word_ids.add(word.id)  

    # 5. 提交事务
    try:
        session.commit()
        return {"status": "success", "book_id": word_book.id, "book_name": book_name}
    except Exception as e:
        session.rollback()
        print(f"导入失败，事务已回滚: {e}")
        raise e