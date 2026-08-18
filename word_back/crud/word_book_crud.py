from typing import Optional
from sqlalchemy import func,select,and_
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from word_back.define import CATEGORY_VOCABULARY,SYSTEM_DICTIONARY_ID,CATEGORY_DICTIONARY
from word_back.models import  WordBook, BookWord,UserWordProgress

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
    db.flush()
    return word_book

# 查询某个用户的所有单词本
def get_word_books_by_user(db: Session, user_id: int) -> list[tuple[WordBook, int]]:
    """获取用户的所有词典类单词本（倒序），并附带其中该用户未背的单词数。

    未背定义：本单词本中的单词，在 UserWordProgress 中不存在 (user_id, word_id) 记录，
    或 status 表示未背（这里假设 status=0 为未背，按需调整）。
    """
    # 关联子查询：统计某 book 下，用户 user_id 未背的单词数
    unlearned_subq = (
        select(func.count(func.distinct(BookWord.word_id)))
        .select_from(BookWord)
        .outerjoin(
            UserWordProgress,
            and_(
                UserWordProgress.word_id == BookWord.word_id,
                UserWordProgress.user_id == user_id,
                UserWordProgress.status != 0,   # 已背/学习中 的排除（按你的 status 含义调整）
            ),
        )
        .where(BookWord.book_id == WordBook.id)
        .where(UserWordProgress.id.is_(None))   # 没有进度记录 = 未背
    )

    stmt = (
        select(WordBook, unlearned_subq.label("unlearned_count"))
        .where(
            WordBook.user_id == user_id,
            WordBook.category == CATEGORY_DICTIONARY,
        )
        .order_by(WordBook.created_at.desc())
    )

    rows = db.execute(stmt).all()
    # rows: list of (WordBook, unlearned_count)
    result = []
    for book, cnt in rows:
        book.unlearned_count = cnt   # 挂临时属性
        result.append(book)
    return result

def _apply_sorting(stmt, sort_by: str = None, sort_order: str = None, unlearned_subq=None):
    """统一处理排序，返回带 order_by 的 stmt"""
    sort_mapping = {
        'name': WordBook.name,
        'created_at': WordBook.created_at,
        'id': WordBook.id,
        'unlearned_count': unlearned_subq,  # 子查询结果也能排序
    }

    if sort_by and sort_order and sort_by in sort_mapping:
        column = sort_mapping[sort_by]
        if sort_order.lower() == 'desc':
            return stmt.order_by(column.desc())
        else:
            return stmt.order_by(column.asc())
    
    # 默认排序
    return stmt.order_by(WordBook.created_at.desc())


# ===== 2. 构建基础查询 =====
def _build_book_base_query(db: Session, user_id: int):
    """构建基础查询（不含排序和分页），供复用"""
    unlearned_subq = (
        select(func.count(func.distinct(BookWord.word_id)))
        .select_from(BookWord)
        .outerjoin(
            UserWordProgress,
            and_(
                UserWordProgress.word_id == BookWord.word_id,
                UserWordProgress.user_id == user_id,
                UserWordProgress.status != 0,
            ),
        )
        .where(BookWord.book_id == WordBook.id)
        .where(UserWordProgress.id.is_(None))
    )

    stmt = (
        select(WordBook, unlearned_subq.label("unlearned_count"))
        .where(
            WordBook.user_id == user_id,
            WordBook.category == CATEGORY_DICTIONARY,
        )
    )
    return stmt, unlearned_subq


# ===== 3. 分页版 =====
def get_word_books_by_user_paged(
    db : Session, user_id, 
    page: int = 1, page_size: int = 10, 
    sort_by: str = None, sort_order: str = None
) -> tuple[list, int]:

    stmt, unlearned_subq = _build_book_base_query(db, user_id)

    # ✅ 用公共函数排序
    stmt = _apply_sorting(stmt, sort_by, sort_order, unlearned_subq)

    # 查总数
    count_stmt = (
        select(func.count())
        .select_from(WordBook)
        .where(
            WordBook.user_id == user_id,
            WordBook.category == CATEGORY_DICTIONARY,
        )
    )
    total = db.scalar(count_stmt) or 0

    # 分页
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    # 执行
    rows = db.execute(stmt).all()
    books = []
    for book, cnt in rows:
        book.unlearned_count = cnt
        books.append(book)

    return books, total


# ===== 4. 全量版 =====
def get_word_books_by_user_all(
    db : Session, user_id, 
    sort_by: str = None, sort_order: str = None
) -> list:

    stmt, unlearned_subq = _build_book_base_query(db, user_id)

    # ✅ 同样用公共函数排序，sort_by/sort_order 真正生效了
    stmt = _apply_sorting(stmt, sort_by, sort_order, unlearned_subq)

    # 执行（不分页）
    rows = db.execute(stmt).all()
    books = []
    for book, cnt in rows:
        book.unlearned_count = cnt
        books.append(book)

    return books

def get_system_book_except_user_book(db: Session, user_id: int,system_id = SYSTEM_DICTIONARY_ID) -> list[WordBook]:

    user_books = get_word_books_by_user_all(db, user_id)
    user_books_name = [b.name for b in user_books]

    system_books = get_word_books_by_user_all(db, system_id)
    system_books_name = [b.name for b in system_books]

    all_books_name = [x for x in system_books_name if x not in user_books_name]

    stmt = (
        select(WordBook)
        .where(WordBook.user_id == system_id)
        .filter(WordBook.name.in_(all_books_name))
    )

    return db.execute(stmt).scalars().all()

def get_system_book_except_user_book_paged(
    db: Session,
    user_id: int,
    page: int = 1,
    page_size: int = 10,
    sort_by: str = None,
    sort_order: str = None,
    system_id: int = SYSTEM_DICTIONARY_ID
) -> tuple[list[WordBook], int]:

    # ===== 1. 查出用户已有的 book name（用于排除）=====
    user_book_names = db.scalars(
        select(WordBook.name).where(WordBook.user_id == user_id)
    ).all()

    # ===== 2. 子查询：计算每个系统 book 下用户未背的单词数 =====
    unlearned_subq = (
        select(func.count(func.distinct(BookWord.word_id)))
        .select_from(BookWord)
        .outerjoin(
            UserWordProgress,
            and_(
                UserWordProgress.word_id == BookWord.word_id,
                UserWordProgress.user_id == user_id,
                UserWordProgress.status != 0,
            ),
        )
        .where(BookWord.book_id == WordBook.id)
        .where(UserWordProgress.id.is_(None))
    )

    # ===== 3. 基础查询（带 unlearned_count）=====
    stmt = (
        select(WordBook, unlearned_subq.label("unlearned_count"))
        .where(WordBook.user_id == system_id)
    )
    if user_book_names:
        stmt = stmt.where(WordBook.name.not_in(user_book_names))

    # ===== 4. 动态排序 =====
    sort_mapping = {
        'name': WordBook.name,
        'created_at': WordBook.created_at,
        'id': WordBook.id,
        'unlearned_count': unlearned_subq,
    }
    if sort_by and sort_order and sort_by in sort_mapping:
        column = sort_mapping[sort_by]
        stmt = stmt.order_by(
            column.desc() if sort_order.lower() == 'desc' else column.asc()
        )
    else:
        stmt = stmt.order_by(WordBook.created_at.desc())

    # ===== 5. 查总数 =====
    count_stmt = (
        select(func.count())
        .select_from(WordBook)
        .where(WordBook.user_id == system_id)
    )
    if user_book_names:
        count_stmt = count_stmt.where(WordBook.name.not_in(user_book_names))
    total = db.scalar(count_stmt) or 0

    # ===== 6. 分页 =====
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    # ===== 7. 执行查询，把 unlearned_count 挂到对象上 =====
    rows = db.execute(stmt).all()
    books = []
    for book, cnt in rows:
        book.unlearned_count = cnt   # ← 关键：挂上临时属性
        books.append(book)

    return books, total

def get_system_book_except_user_book_all(
    db: Session,
    user_id: int,
    sort_by: str = None,
    sort_order: str = None,
    system_id: int = SYSTEM_DICTIONARY_ID
) -> list[WordBook]:
    """不分页，获取所有系统 book（排除用户已有的）"""

    user_book_names = db.scalars(
        select(WordBook.name).where(WordBook.user_id == user_id)
    ).all()

    stmt = select(WordBook).where(WordBook.user_id == system_id)
    if user_book_names:
        stmt = stmt.where(WordBook.name.not_in(user_book_names))

    # 排序
    sort_mapping = {
        'name': WordBook.name,
        'created_at': WordBook.created_at,
        'id': WordBook.id,
    }
    if sort_by and sort_order and sort_by in sort_mapping:
        column = sort_mapping[sort_by]
        stmt = stmt.order_by(
            column.desc() if sort_order.lower() == 'desc' else column.asc()
        )
    else:
        stmt = stmt.order_by(WordBook.created_at.desc())

    return db.execute(stmt).scalars().all()

# 将一本已有的 WordBook 复制为指定用户的私人单词本
def clone_wordbook_to_user(db: Session, target_user_id: int, system_book_id: int) -> None:
    source_book = get_word_book_by_id(db, system_book_id)

    # 1. 防止用户名下已存在同名单词本
    existing = db.scalars(
        select(WordBook).where(
            WordBook.user_id == target_user_id,
            WordBook.name == source_book.name
        )
    ).first()

    if existing:
        raise ValueError("该用户名下已存在同名的单词本")

    # 2. 创建属于该用户的新单词本
    new_book = WordBook(
        user_id=target_user_id,
        name=source_book.name,
        category=source_book.category,
        description=source_book.description,
    )
    db.add(new_book)
    db.flush()  # 刷新以获取 new_book.id

    # 3. 收集原书的所有 word_id
    word_ids = [bw.word_id for bw in source_book.book_words]
    
    if not word_ids:
        # 原书是空的，直接提交返回
        db.commit()
        db.refresh(new_book)
        return 

    # 4. 批量复制单词关联到新本（用 bulk_save_objects 提升性能）
    new_book_words = [
        BookWord(book_id=new_book.id, word_id=word_id)
        for word_id in word_ids
    ]
    db.bulk_save_objects(new_book_words)

    # 5. 【核心修改】批量初始化用户对这些单词的学习进度（未学习）
    #    先查一下哪些单词已经有进度记录了（防止唯一约束冲突）
    existing_progress_word_ids = set(
        db.scalars(
            select(UserWordProgress.word_id).where(
                UserWordProgress.user_id == target_user_id,
                UserWordProgress.word_id.in_(word_ids)
            )
        ).all()
    )
    
    # 只给没有记录的单词初始化进度
    new_progresses = [
        UserWordProgress(
            user_id=target_user_id,
            word_id=word_id,
            status=0,           
        )
        for word_id in word_ids
        if word_id not in existing_progress_word_ids
    ]
    
    if new_progresses:
        db.bulk_save_objects(new_progresses)

    # 6. 提交并刷新
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