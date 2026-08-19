import math
from typing import Optional
from sqlalchemy import func,select,and_,or_
from sqlalchemy.orm import Session,selectinload

from word_back.models import  WordBook, Word, BookWord,UserWordProgress
from word_back.schemas.word_schema import PageMeta, WordItem, WordPageResponse

# =====================
# 单词相关
# =====================

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
        status=status  
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
        # 作用：获取用户所有未背的单词、已掌握单词
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

    # ========== 分页 + 预加载关联数据 ====
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

def mark_word_as_mode(session: Session, user_id: int, word_id: int, mode: int) -> None:
    """
    根据 user_id 和 word_id 将该单词在用户名下标记为指定学习状态
    
    :param session: SQLAlchemy Session
    :param user_id: 用户 ID
    :param word_id: 单词 ID
    :param mode: 学习状态 (0-未学习 1-已认识 2-学习中 3-已掌握)
    """
    # 1. 检查单词是否存在
    word_exists = session.get(Word, word_id) is not None
    
    if not word_exists:
        raise ValueError(f"单词 {word_id} 不存在")

    # 2. 查找该用户对该单词的进度记录
    progress = session.execute(
        select(UserWordProgress).where(
            UserWordProgress.user_id == user_id,
            UserWordProgress.word_id == word_id
        )
    ).scalar_one_or_none()

    if progress is None:
        # 3a. 没有记录 → 新建（利用唯一约束保证安全）
        progress = UserWordProgress(
            user_id=user_id,
            word_id=word_id,
            status=mode
        )
        session.add(progress)
    else:
        # 3b. 有记录 → 更新状态
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