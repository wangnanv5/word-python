from typing import Optional
from sqlalchemy import func,select,and_
from sqlalchemy.orm import Session,selectinload
from sqlalchemy.exc import SQLAlchemyError
from pwdlib import PasswordHash

from word_back.define import INIT_NICKNAME,CATEGORY_VOCABULARY,SYSTEM_DICTIONARY_ID,CATEGORY_DICTIONARY
from word_back.models import User, WordBook, Word, BookWord
from word_back.schemas import WordItem,WordPageResponse

# 密码加密工具
pwd_context = PasswordHash.recommended()

# =====================
# 通用
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
    db.flush()
    return word_book

# =====================
# 用户相关
# =====================

# 创建用户 并且创建一个生词本
def create_user(
    db: Session,
    username: str,
    phone: str | None = None,
    password: str = None,
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
    try:
        db.add(user)
        db.flush()  # 拿到 user.id，不提交事务

        create_word_book(db, user_id=user.id,name="生词本")

        # 5. 提交事务
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()      # 回滚，避免会话处于破损状态
        raise Exception("数据库创建用户失败")
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
    stmt = select(User).where(User.phone == phone)
    return db.scalars(stmt).first()

def get_user_by_username(db: Session, username: str) -> User | None:
    """
    根据用户名查询用户
    """
    stmt = select(User).where(User.username == username)
    return db.scalars(stmt).first()

def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    校验密码
    """
    return pwd_context.verify(plain_password, password_hash)

# =====================
# 单词本相关
# =====================


# 查询某个用户的所有单词本
def get_word_books_by_user(db: Session, user_id: int) -> list[WordBook]:
    """获取某用户的所有单词本，按创建时间倒序"""
    stmt = (
        select(WordBook)
        .where(WordBook.user_id == user_id,WordBook.category == CATEGORY_DICTIONARY)
        .order_by(WordBook.created_at.desc())
    )
    return db.scalars(stmt).all()

# 查询用户单词本 排除系统单词本
def get_system_book_except_user_book(db: Session, user_id: int,system_id = SYSTEM_DICTIONARY_ID) -> list[WordBook]:

    user_books = get_word_books_by_user(db, user_id)
    user_books_name = [b.name for b in user_books]

    system_books = get_word_books_by_user(db, system_id)
    system_books_name = [b.name for b in system_books]

    all_books_name = [x for x in system_books_name if x not in user_books_name]

    stmt = (
        select(WordBook)
        .where(WordBook.user_id == system_id)
        .filter(WordBook.name.in_(all_books_name))
    )

    return db.execute(stmt).scalars().all()

# 将一本已有的 WordBook 复制为指定用户的私人单词本
def clone_wordbook_to_user(db: Session, target_user_id: int, system_book_id: int) -> WordBook:
    source_book = get_word_book_by_id(db, system_book_id)

    # 1. 防止用户名下已存在同名单词本（触发 UniqueConstraint）
    existing = db.scalar(
        select(WordBook).where(
            WordBook.user_id == target_user_id,
            WordBook.name == source_book.name
        )
    )

    if existing:
        # 已存在则直接返回，或根据业务抛出提示
        raise Exception("单词本已存在")

    # 2. 创建属于该用户的新单词本
    new_book = WordBook(
        user_id=target_user_id,
        name=source_book.name,
        category=source_book.category,
        description=source_book.description,
    )
    db.add(new_book)
    db.flush()  # 刷新以获取 new_book.id

    # 3. 复制原书的单词关联到新本（BookWord 只是关联关系，可安全复用 word_id）
    for bw in source_book.book_words:
        db.add(BookWord(
            book_id=new_book.id,
            word_id=bw.word_id
        ))

    db.commit()
    db.refresh(new_book)

def get_word_book_by_id(db: Session, book_id: int) -> WordBook | None:
    """
    根据 ID 查询单词本
    """
    return db.get(WordBook, book_id)

def delete_word_book(
    db: Session,
    word_book_id: int,
    user_id: Optional[int] = None,
) -> bool:
    """带异常捕获与回滚的安全删除版本"""
    try:
        stmt  = select(WordBook).where(WordBook.id == word_book_id)
        if user_id is not None:
            stmt  = stmt .where(WordBook.user_id == user_id)

        word_book = db.scalar(stmt)
        if word_book is None:
            return False

        db.delete(word_book)
        db.commit()
        return True

    except SQLAlchemyError:
        db.rollback()
        raise  Exception("数据库删除单词本失败")

def word_to_view(word: Word) -> WordItem:
    return WordItem(
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
        ]
    )

# 获取一个单词本中的所有单词 支持分页
def get_wordbook_words(
    db :Session,
    user_id: int,
    book_id: int,
    page: int = 1,
    page_size: int = 20,
    sort : str = None
) -> WordPageResponse:
    """
    获取某个单词本中的单词列表（分页 + 搜索）
    book_id = -1 表示系统词典
    """
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

    base_stmt = (
        select(Word)
        .join(BookWord, BookWord.word_id == Word.id)
        .where(BookWord.book_id == book_id).where(Word.is_learned == False)
    )
    # 排序方式
    if sort == "spelling":
        sort_by = Word.spelling
    elif sort == "created_at":
        sort_by = Word.created_at.desc()
    else:
        raise ValueError("Invalid sort")

    # if keyword:
    #     base_stmt = base_stmt.where(Word.spelling.ilike(f"{keyword}%"))

    # if part_of_speech:
    #     base_stmt = base_stmt.join(
    #         WordTranslation, WordTranslation.word_id == Word.id
    #     ).where(WordTranslation.part_of_speech == part_of_speech).distinct()

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
    return WordPageResponse(items=items, total=total, page=page, page_size=page_size)

# =====================
# 单词相关
# =====================

def mark_word_as_learned(session:Session, word_id: int) -> bool:
    """
    根据 word id 将该单词标记为已学习

    :param session: SQLAlchemy Session
    :param word_id: 单词 ID
    :return: 是否成功（False 表示未找到该单词）
    """
    word = session.query(Word).filter(Word.id == word_id).first()
    if word is None:
        return False

    word.is_learned = True   # 注意字段名是 is_leared
    session.commit()

def search_words(
    db: Session,
    keyword: str,
    limit: int = 50
) -> list[Word]:
    stmt = (
        select(Word)
        .where(Word.spelling.ilike(f"%{keyword}%"))
        .order_by(Word.spelling)
        .limit(limit)          # 最多返回 50 条
    )
    return db.scalars(stmt).all()

# =====================
# 单词本和单词关系
# =====================
def add_word_to_book(
    db: Session,
    book_id: int,
    word_id: int
) -> BookWord:
    """
    把单词加入单词本（已存在则直接返回，幂等）
    """
    existing = db.scalar(
        select(BookWord).where(
            BookWord.book_id == book_id,
            BookWord.word_id == word_id
        )
    )
    if existing:
        return existing

    book_word = BookWord(book_id=book_id, word_id=word_id)
    db.add(book_word)
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
    book_word = db.scalar(
        select(BookWord).where(
            BookWord.book_id == book_id,
            BookWord.word_id == word_id
        )
    )
    if not book_word:
        return False

    db.delete(book_word)
    db.commit()
    return True