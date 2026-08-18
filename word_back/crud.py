import math
from typing import Optional
from sqlalchemy import func,select,and_,or_
from sqlalchemy.orm import Session,selectinload
from sqlalchemy.exc import SQLAlchemyError

from word_back.define import INIT_NICKNAME,CATEGORY_VOCABULARY,SYSTEM_DICTIONARY_ID,CATEGORY_DICTIONARY
from word_back.models import User, WordBook, Word, BookWord,UserWordProgress
from word_back.schemas.word_book_schema import WordItem,WordPageResponse,PageMeta
from word_back.auth import pwd_context

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
        if user.role == "super":
            # 创建系统单词本
            create_word_book(db, user_id=user.id,name="生词本")

        # 5. 提交事务
        db.commit()
        db.refresh(user)
    except Exception:
        db.rollback()      # 回滚，避免会话处于破损状态
        raise Exception("数据库创建用户失败")
    return user

def get_user_by_username(db: Session, username: str) -> User | None:
    """
    根据用户名查询用户
    """
    stmt = select(User).where(User.username == username)
    return db.scalars(stmt).first()


# =====================
# 单词本相关
# =====================


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
        # 建议用更具体的异常，方便上层捕获处理
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

def word_to_view(word: Word, status: int = 0) -> WordItem:
    """
    将 Word ORM 对象转换为 WordItem 视图对象
    
    :param word: Word ORM 对象
    :param status: 当前用户对该单词的学习状态，默认0（未学习）
    """
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
        ],
        status=status  # 传入学习状态
    )
# 获取一个单词本中的所有单词 支持分页
# 0代表查询 is_learned为0 is_in_vocabulary:0 is_deleted:0 未学习的单词
# 1代表查询 is_learned为1 is_in_vocabulary:0 is_deleted:0 已认识,并删除
# 2代表查询 is_learned为1 is_in_vocabulary:1 is_deleted:0 已学习,并加入生词本
# 3代表查询 is_learned为1 is_in_vocabulary:1 is_deleted:1 未学习,并加入生词本,并已掌握删除
def get_wordbook_words(
    db: Session,
    user_id: int,
    book_id: Optional[int] = None,  # 改为可选，允许查全局
    page: int = 1,
    page_size: int = 20,
    sort: str = "spelling",
    mode: int = 0
) -> WordPageResponse:
    """
    获取单词列表（分页 + 排序 + 按用户学习状态过滤）
    
    :param user_id: 当前用户ID（必传）
    :param book_id: 单词本ID，None 表示查该用户所有单词
    :param mode: 学习状态 0-未学习 1-已认识 2-学习中 3-已掌握
    """
    
    # ========== 构建基础查询 ==========
    if book_id is None:
        # ---- 场景1：查该用户所有状态为 mode 的单词（不限单词本）----
        base_stmt = (
            select(Word)
            .outerjoin(  # 用 outerjoin 兼容"未学习且无进度记录"的情况
                UserWordProgress,
                and_(
                    UserWordProgress.word_id == Word.id,
                    UserWordProgress.user_id == user_id
                )
            )
        )
        # 根据 mode 过滤
        if mode == 0:
            # 未学习：没有进度记录，或者 status=0
            base_stmt = base_stmt.where(
                or_(
                    UserWordProgress.status == 0,
                    UserWordProgress.status.is_(None)
                )
            )
        else:
            base_stmt = base_stmt.where(UserWordProgress.status == mode)
            
    else:
        # ---- 场景2：查指定单词本内，该用户状态为 mode 的单词 ----
        
        # 校验权限
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
            .join(  # 这里用 join，因为单词本里的单词应该都有进度记录
                UserWordProgress,
                and_(
                    UserWordProgress.word_id == Word.id,
                    UserWordProgress.user_id == user_id
                )
            )
            .where(
                BookWord.book_id == book_id,
                UserWordProgress.status == mode
            )
        )

    # ========== 排序 ==========
    if sort == "created_at":
        sort_by = Word.created_at.desc()
    else:
        # 默认按拼写排序，避免传错参数直接抛异常
        sort_by = Word.spelling

    # ========== 总数统计 ==========
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = db.execute(count_stmt).scalar_one()

    # ========== 分页 + 预加载关联数据 ==========
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

    # ========== 批量获取这些单词的用户学习状态（避免 N+1 查询）==========
    word_ids = [w.id for w in words]
    progresses = {}
    if word_ids:
        progress_records = db.execute(
            select(UserWordProgress).where(
                UserWordProgress.user_id == user_id,
                UserWordProgress.word_id.in_(word_ids)
            )
        ).scalars().all()
        progresses = {p.word_id: p.status for p in progress_records}

    # ========== 转换为视图对象（带上 status）==========
    items = []
    for w in words:
        view = word_to_view(w)
        # 如果 word_to_view 返回的字典/对象可以附加字段，把 status 带上
        view.status = progresses.get(w.id, 0)  # 没有记录默认0（未学习）
        items.append(view)

    total_pages = math.ceil(total / page_size) if page_size > 0 else 0

    meta = PageMeta(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

    return WordPageResponse(items=items, meta=meta)

# =====================
# 单词相关
# =====================

def copy_word_to_book(
    session: Session,
    source_book_id: int,
    word_id: int,
    target_book_id: int,
) -> None:
    """
    将 source_book 中的某个 word 复制进 target_book。

    :raises ValueError:   源 book 与目标 book 相同
    :raises LookupError:  源 book 中不存在该 word，或目标 book 不存在
    """
    # 1. 基本参数校验
    if source_book_id == target_book_id:
        raise ValueError("源单词本和目标单词本不能相同")

    # 2. 确认源 book 中确实存在该 word
    src_link = session.scalar(
        select(BookWord).where(
            BookWord.book_id == source_book_id,
            BookWord.word_id == word_id,
        )
    )
    if src_link is None:
        raise LookupError(f"word {word_id} 不在源单词本 {source_book_id} 中")

    # 3. 确认目标 book 存在
    target_book = session.scalar(
        select(WordBook).where(WordBook.id == target_book_id)
    )
    if target_book is None:
        raise LookupError(f"目标单词本 {target_book_id} 不存在")

    # 4. 幂等：目标 book 已包含该 word 则直接返回
    existing = session.scalar(
        select(BookWord).where(
            BookWord.book_id == target_book_id,
            BookWord.word_id == word_id,
        )
    )
    if existing is not None:
        return existing

    # 5. 插入新关联
    new_link = BookWord(book_id=target_book_id, word_id=word_id)
    session.add(new_link)
    session.commit()
    session.refresh(new_link)

def mark_word_as_mode(session: Session, user_id: int, word_id: int, mode: int) -> None:
    """
    根据 user_id 和 word_id 将该单词在用户名下标记为指定学习状态
    
    :param session: SQLAlchemy Session
    :param user_id: 用户 ID（新增）
    :param word_id: 单词 ID
    :param mode: 学习状态 (0-未学习 1-已认识 2-学习中 3-已掌握)
    :return: 是否成功（False 表示未找到该单词）
    """
    # 1. 检查单词是否存在（保持原函数的语义）
    word_exists = session.query(Word.id).filter(Word.id == word_id).scalar() is not None
    if not word_exists:
        return 

    # 2. 查找该用户对该单词的进度记录
    progress = session.query(UserWordProgress).filter_by(
        user_id=user_id,
        word_id=word_id
    ).first()

    if progress is None:
        # 3a. 没有记录 → 新建（利用唯一约束保证安全）
        progress = UserWordProgress(
            user_id=user_id,
            word_id=word_id,
            status=mode
        )
        session.add(progress)
    else:
        progress.status = mode

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