import math
from datetime import datetime
from typing import Optional, Literal
from dataclasses import dataclass, field
from sqlalchemy import func,select,and_
from sqlalchemy.orm import Session,selectinload,joinedload
from pwdlib import PasswordHash

from word_back.define import SYSTEM_DICTIONARY_VIRTUAL_ID,INIT_PASSWORD,INIT_NICKNAME,CATEGORY_VOCABULARY
from word_back.models import User, WordBook, Word, BookWord,WordTranslation
from word_back.schemas import WordItem, TranslationItem,PhraseItem

# 密码加密工具
pwd_context = PasswordHash.recommended()

@dataclass
class WordView:
    """统一的单词视图，包含释义和短语"""
    id: int
    spelling: str
    us: Optional[str] = None
    uk: Optional[str] = None
    audio_url: Optional[str] = None
    translations: list[dict] = field(default_factory=list)
    phrases: list[dict] = field(default_factory=list)

@dataclass
class PageResult:
    """分页结果"""
    items: list = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20

    @property
    def total_pages(self) -> int:
        return math.ceil(self.total / self.page_size) if self.page_size > 0 else 0

# =====================
# 用户相关
# =====================
# 新用户会自动获得一个单词本，包含所有单词
def create_user(
    db: Session,
    username: str,
    phone: str | None = None,
    password: str = INIT_PASSWORD,
    email: str | None = None,
    nickname: str = INIT_NICKNAME,
    avatar_url: str | None = None,
    role: str = "user"
) -> User:
    """
    创建用户
    """
    if not password:
        raise ValueError("password is required")

    password_hash = pwd_context.hash(password)

    # 1. 创建用户
    user = User(
        phone=phone,
        password_hash=password_hash,
        email=email,
        username=username,
        nickname=nickname,
        avatar_url=avatar_url,
        role = role,
    )
    db.add(user)
    db.flush()  # 拿到 user.id，不提交事务

    # 2. 创建默认单词本（生词本 / 词典）
    # default_book = WordBook(
    #     user_id=user.id,
    #     name=f"{username or '默认'}的单词本",
    #     category=WordBook.CATEGORY_VOCABULARY,
    #     description="系统词典副本（物理复制）"
    # )
    # db.add(default_book)
    # db.flush()  # 拿到 book_id

    # system_dict = db.query(SystemDictionary).first()
    # if not system_dict:
    #     raise RuntimeError("系统词典不存在，请先初始化系统词典")

    # 4. 批量复制系统词典单词到用户单词本
    # sys_word_ids = (
    #     db.query(SystemDictionaryWord.word_id)
    #     .filter(SystemDictionaryWord.dictionary_id == system_dict.id)
    #     .all()
    # )

    # if sys_word_ids:
    #     db.bulk_insert_mappings(
    #         BookWord,
    #         [
    #             {
    #                 "book_id": default_book.id,
    #                 "word_id": word_id,
    #             }
    #             for (word_id,) in sys_word_ids
    #         ]
    #     )

    # default_book = WordBook(
    #     user_id=user.id,
    #     name=f"{username or '默认'}的2312单词本",
    #     category=WordBook.CATEGORY_VOCABULARY,
    #     description="系统词典副本（物理复制）"
    # )
    # db.add(default_book)
    # db.flush()  # 拿到 book_id

    # default_book = WordBook(
    #     user_id=user.id,
    #     name=f"{username or '默认'}的单412414词本",
    #     category=WordBook.CATEGORY_VOCABULARY,
    #     description="系统词典副本（物理复制）"
    # )
    # db.add(default_book)
    # db.flush()  # 拿到 book_id

    # 5. 提交事务
    db.commit()
    db.refresh(user)

    return user


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """
    根据 ID 查询用户
    """
    return db.get(User, user_id)


def get_user_by_phone(db: Session, phone: str) -> User | None:
    """
    根据电话号码查询用户
    """
    return (
        db.query(User)
        .filter(User.phone == phone)
        .first()
    )

def get_user_by_username(db: Session, username: str) -> User | None:
    """
    根据用户名查询用户
    """
    return (
        db.query(User)
        .filter(User.username == username)
        .first()
    )

def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    校验密码
    """
    return pwd_context.verify(plain_password, password_hash)


# =====================
# 单词本相关
# =====================

def create_word_book(
    db: Session,
    user_id: int,
    name: str,
    category: str = CATEGORY_VOCABULARY,
    description: str | None = None
) -> WordBook:
    """
    创建单词本
    """
    word_book = WordBook(
        user_id=user_id,
        name=name,
        category=category,
        description=description
    )

    db.add(word_book)
    db.commit()
    db.refresh(word_book)
    return word_book


# 查询某个用户的所有单词本
def get_word_books_by_user(db: Session, user_id: int) -> list[WordBook]:
    return (
        db.query(WordBook)
        .filter(WordBook.user_id == user_id)
        .order_by(WordBook.created_at.desc())
        .all()
    )


def get_word_book_by_id(db: Session, book_id: int) -> WordBook | None:
    """
    根据 ID 查询单词本
    """
    return db.get(WordBook, book_id)


def word_to_item(word: Word) -> WordItem:
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

def word_to_view(word: Word) -> WordView:
    """将 Word ORM 对象转为 WordView DTO"""
    return WordView(
        id=word.id,
        spelling=word.spelling,
        us=word.us,
        uk=word.uk,
        audio_url=word.audio_url,
        translations=[
            {"pos": t.part_of_speech, "text": t.translation}
            for t in word.translations
        ],
        phrases=[
            {"phrase": p.phrase, "translation": p.translation}
            for p in word.phrases
        ],
    )

# def get_system_dictionary(db :Session) -> Optional[SystemDictionary]:
#         return db.execute(select(SystemDictionary).limit(1)).scalar_one_or_none()

# def get_system_dictionary_words(
#         db :Session,
#         page: int,
#         page_size: int,
#         sort: str = "spelling"
#     ) -> PageResult:
#         """查询系统词典中的单词（分页 + 搜索）"""
#         sys_dict = get_system_dictionary(db)
#         if sys_dict is None:
#             return PageResult(page=page, page_size=page_size)

#         # 子查询：系统词典中的 word_id
#         dict_word_ids = select(SystemDictionaryWord.word_id).where(
#             SystemDictionaryWord.dictionary_id == sys_dict.id
#         )

#         base_stmt = select(Word).where(Word.id.in_(dict_word_ids))

#         # 总数
#         count_stmt = select(func.count()).select_from(base_stmt.subquery())
#         total = db.execute(count_stmt).scalar_one()

#         # 排序方式
#         if sort == "spelling":
#             sort_by = Word.spelling
#         elif sort == "created_at":
#             sort_by = Word.created_at.desc()
#         else:
#             raise ValueError("Invalid sort")

#         # 分页 + 预加载
#         stmt = (
#             base_stmt
#             .options(
#                 selectinload(Word.translations),
#                 selectinload(Word.phrases),
#             )
#             .order_by(sort_by)
#             .offset((page - 1) * page_size)
#             .limit(page_size)
#         )
#         words = db.execute(stmt).scalars().all()

#         items = [word_to_view(w) for w in words]
#         return PageResult(items=items, total=total, page=page, page_size=page_size)

def get_user_wordbook_words(
    db :Session,
    book_id: int,
    page: int,
    page_size: int,
    keyword: Optional[str] = None,
    part_of_speech: Optional[str] = None,
    sort: str = "spelling"

) -> PageResult:
    """查询用户单词本中的单词"""
    base_stmt = (
        select(Word)
        .join(BookWord, BookWord.word_id == Word.id)
        .where(BookWord.book_id == book_id)
    )
    # 排序方式
    if sort == "spelling":
        sort_by = Word.spelling
    elif sort == "created_at":
        sort_by = Word.created_at.desc()
    else:
        raise ValueError("Invalid sort")

    if keyword:
        base_stmt = base_stmt.where(Word.spelling.ilike(f"{keyword}%"))

    if part_of_speech:
        base_stmt = base_stmt.join(
            WordTranslation, WordTranslation.word_id == Word.id
        ).where(WordTranslation.part_of_speech == part_of_speech).distinct()

    # 总数
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = db.execute(count_stmt).scalar_one()

    # 分页 + 预加载
    stmt = (
        base_stmt
        .options(
            selectinload(Word.translations),
            selectinload(Word.phrases),
        )
        .order_by(sort_by)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    words = db.execute(stmt).scalars().all()

    items = [word_to_view(w) for w in words]
    return PageResult(items=items, total=total, page=page, page_size=page_size)

def get_wordbook_words(
    db :Session,
    user_id: int,
    book_id: int,
    page: int = 1,
    page_size: int = 20,
    sort : str = None
) -> PageResult:
    """
    获取某个单词本中的单词列表（分页 + 搜索）
    book_id = -1 表示系统词典
    """
    if book_id == SYSTEM_DICTIONARY_VIRTUAL_ID:
        page_result = get_system_dictionary_words(db=db,page=page, page_size=page_size,sort=sort)
    else:
        # ---- 用户私有单词本 ----
        # 校验权限：只能看自己的
        book = db.execute(
            select(WordBook).where(
                and_(
                    WordBook.id == book_id,
                    WordBook.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

        if book is None:
            raise PermissionError(f"单词本 {book_id} 不存在或不属于当前用户")

        page_result = get_user_wordbook_words(
            db=db,
            book_id=book_id,
            page=page, page_size=page_size,sort=sort
        )

    return page_result

# =====================
# 单词相关
# =====================



def search_words(db: Session, keyword: str) -> list[Word]:
    """
    简单搜索单词
    """
    return (
        db.query(Word)
        .filter(Word.spelling.ilike(f"%{keyword}%"))
        .order_by(Word.spelling)
        .all()
    )


# =====================
# 单词本和单词关系
# =====================

def add_word_to_book(
    db: Session,
    book_id: int,
    word_id: int
) -> BookWord:
    """
    把单词加入单词本
    """
    existing = (
        db.query(BookWord)
        .filter(
            BookWord.book_id == book_id,
            BookWord.word_id == word_id
        )
        .first()
    )

    if existing:
        return existing

    book_word = BookWord(
        book_id=book_id,
        word_id=word_id
    )

    db.add(book_word)
    db.flush()


    db.commit()
    db.refresh(book_word)
    return book_word


def remove_word_from_book(
    db: Session,
    book_id: int,
    word_id: int
) -> bool:
    """
    从单词本移除单词
    """
    book_word = (
        db.query(BookWord)
        .filter(
            BookWord.book_id == book_id,
            BookWord.word_id == word_id
        )
        .first()
    )

    if not book_word:
        return False

    db.delete(book_word)
    db.flush()

    db.commit()
    return True
