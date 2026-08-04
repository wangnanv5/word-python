from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session
from pwdlib import PasswordHash
from word_back.models import User, WordBook, Word, BookWord,SystemDictionary,SystemDictionaryWord


# 密码加密工具
pwd_context = PasswordHash.recommended()


# =====================
# 用户相关
# =====================
# 新用户会自动获得一个单词本，包含所有单词
def create_user(
    db: Session,
    phone: str | None = None,
    password: str | None = None,
    email: str | None = None,
    username: str | None = None,
    nickname: str | None = None,
    avatar_url: str | None = None
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
        avatar_url=avatar_url
    )
    db.add(user)
    db.flush()  # 拿到 user.id，不提交事务

    # 2. 创建默认单词本（生词本 / 词典）
    default_book = WordBook(
        user_id=user.id,
        name=f"{username or '默认'}的单词本",
        category=WordBook.CATEGORY_VOCABULARY,
        description="系统词典副本（物理复制）"
    )
    db.add(default_book)
    db.flush()  # 拿到 book_id

    system_dict = db.query(SystemDictionary).first()
    if not system_dict:
        raise RuntimeError("系统词典不存在，请先初始化系统词典")

    # 4. 批量复制系统词典单词到用户单词本
    sys_word_ids = (
        db.query(SystemDictionaryWord.word_id)
        .filter(SystemDictionaryWord.dictionary_id == system_dict.id)
        .all()
    )

    if sys_word_ids:
        db.bulk_insert_mappings(
            BookWord,
            [
                {
                    "book_id": default_book.id,
                    "word_id": word_id,
                }
                for (word_id,) in sys_word_ids
            ]
        )

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
    category: str = WordBook.CATEGORY_VOCABULARY,
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


def get_word_books_by_user(db: Session, user_id: int) -> list[WordBook]:
    """
    查询某个用户的所有单词本
    """
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


def update_word_book_count(db: Session, book_id: int) -> None:
    """
    更新单词本的单词数量
    """
    book = db.get(WordBook, book_id)
    if not book:
        return

    count = (
        db.query(func.count(BookWord.id))
        .filter(BookWord.book_id == book_id)
        .scalar()
    )

    book.word_count = count or 0
    db.commit()


# =====================
# 单词相关
# =====================

def create_word(
    db: Session,
    spelling: str,
    meaning: str,
    phonetic: str | None = None,
    audio_url: str | None = None,
    part_of_speech: str = "",
    example_sentence: str | None = None,
    example_translation: str | None = None,
    difficulty: int = 1
) -> Word:
    """
    创建单词
    """
    word = Word(
        spelling=spelling,
        meaning=meaning,
        phonetic=phonetic,
        audio_url=audio_url,
        part_of_speech=part_of_speech or "",
        example_sentence=example_sentence,
        example_translation=example_translation,
        difficulty=difficulty,
    )

    db.add(word)
    db.commit()
    db.refresh(word)
    return word


def get_word_by_id(db: Session, word_id: int) -> Word | None:
    """
    根据 ID 查询单词
    """
    return db.get(Word, word_id)


def get_word_by_spelling(
    db: Session,
    spelling: str,
    part_of_speech: str = ""
) -> Word | None:
    """
    根据拼写和词性查询单词
    """
    return (
        db.query(Word)
        .filter(
            Word.spelling == spelling,
            Word.part_of_speech == (part_of_speech or "")
        )
        .first()
    )


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

    update_word_book_count(db, book_id)

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

    update_word_book_count(db, book_id)

    db.commit()
    return True


def get_words_in_book(db: Session, book_id: int) -> list[Word]:
    """
    查询某个单词本里的所有单词
    """
    return (
        db.query(Word)
        .join(BookWord, BookWord.word_id == Word.id)
        .filter(BookWord.book_id == book_id)
        .order_by(Word.spelling)
        .all()
    )


def get_book_word(
    db: Session,
    book_id: int,
    word_id: int
) -> BookWord | None:
    """
    查询某个单词在某本单词本里的学习记录
    """
    return (
        db.query(BookWord)
        .filter(
            BookWord.book_id == book_id,
            BookWord.word_id == word_id
        )
        .first()
    )


def review_word(
    db: Session,
    book_id: int,
    word_id: int,
    mastery_level: int | None = None,
    next_review_at: datetime | None = None
) -> BookWord | None:
    """
    复习单词，更新学习状态
    """
    book_word = get_book_word(db, book_id, word_id)

    if not book_word:
        return None

    book_word.review_count += 1
    book_word.last_review_at = datetime.now(timezone.utc)

    if mastery_level is not None:
        book_word.mastery_level = mastery_level

    if next_review_at is not None:
        book_word.next_review_at = next_review_at

    db.commit()
    db.refresh(book_word)
    return book_word


def get_due_review_words(
    db: Session,
    book_id: int,
    now: datetime | None = None
) -> list[Word]:
    """
    查询某个单词本中到期需要复习的单词
    """
    if now is None:
        now = datetime.now(timezone.utc)

    return (
        db.query(Word)
        .join(BookWord, BookWord.word_id == Word.id)
        .filter(
            BookWord.book_id == book_id,
            BookWord.next_review_at <= now
        )
        .order_by(BookWord.next_review_at)
        .all()
    )