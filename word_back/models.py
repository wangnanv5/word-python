from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    CheckConstraint,
)
from sqlalchemy.orm import relationship

from word_back.database import Base
from word_back.define import CATEGORY_DICTIONARY, CATEGORY_VOCABULARY


# ============================================================
# 工具函数
# ============================================================
def _utcnow():
    """统一返回带时区的 UTC 当前时间，避免 default 值不一致"""
    return datetime.now(timezone.utc)


# ============================================================
# 用户表
# ============================================================
class User(Base):
    """
    用户表
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    role = Column(String(20), nullable=False, default="user")

    phone = Column(String(20), unique=True, nullable=True, index=True)
    email = Column(String(120), unique=True, nullable=True, index=True)
    avatar_url = Column(String(255), nullable=True)
    nickname = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    # 用户私有单词本
    word_books = relationship("WordBook", back_populates="user", cascade="all, delete-orphan")
    
    # 【新增】用户的学习进度记录
    word_progresses = relationship("UserWordProgress", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User id={self.id} username={self.username}>"


# ============================================================
# 单词本表
# ============================================================
class WordBook(Base):
    """
    只存放用户自己创建的单词本
    """
    __tablename__ = "word_books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(20), nullable=False, default=CATEGORY_VOCABULARY)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    user = relationship("User", back_populates="word_books")
    book_words = relationship("BookWord", back_populates="book", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(f"category IN ('{CATEGORY_DICTIONARY}', '{CATEGORY_VOCABULARY}')", name="ck_word_books_category"),
        UniqueConstraint("user_id", "name", name="uq_word_books_user_name"),
        Index("ix_word_books_user_category", "user_id", "category")
    )

    def __repr__(self):
        return f"<WordBook id={self.id} name={self.name} category={self.category}>"


# ============================================================
# 单词主表
# ============================================================
class Word(Base):
    """
    单词表（全局共享，不含任何用户学习状态）
    """
    __tablename__ = "words"

    id = Column(Integer, primary_key=True, autoincrement=True)

    spelling = Column(String(100), nullable=False, index=True)
    us = Column(String(100), nullable=True)   # 美式音标
    uk = Column(String(100), nullable=True)   # 英式音标
    audio_url = Column(String(255), nullable=True)
    
    translations = relationship("WordTranslation", back_populates="word", cascade="all, delete-orphan")
    phrases = relationship("WordPhrase", back_populates="word", cascade="all, delete-orphan")
    book_words = relationship("BookWord", back_populates="word", cascade="all, delete-orphan")
    
    # 【新增】用户学习进度关联（多对多，通过进度表）
    user_progresses = relationship("UserWordProgress", back_populates="word", cascade="all, delete-orphan")

    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    # 【已删除】mode 字段，用户状态已移至 UserWordProgress 表

    __table_args__ = (
        UniqueConstraint("spelling", name="uq_words_spelling"),
        Index("ix_words_spelling_created", "spelling", "created_at"),
    )

    def __repr__(self):
        return f"<Word id={self.id} spelling={self.spelling!r}>"


# ============================================================
# 【新增】用户单词学习进度表
# ============================================================
class UserWordProgress(Base):
    """
    用户单词学习记录表
    替代原来 Word 表中的 mode 字段，实现多用户数据隔离
    
    状态说明（对应你原来的 mode 逻辑）：
    0 - 未学习（默认）
    1 - 已认识（跳过，相当于原来的 mode=1）
    2 - 已学习/加入生词本（可结合 BookWord 表，或单独用此状态）
    3 - 已掌握（相当于原来的 mode=3）
    """
    __tablename__ = "user_word_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    word_id = Column(Integer, ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True)

    # 学习状态
    status = Column(Integer, nullable=False, default=0, comment="0-未学习 1-已认识 2-学习中 3-已掌握")
    
    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    # 关联关系
    user = relationship("User", back_populates="word_progresses")
    word = relationship("Word", back_populates="user_progresses")

    __table_args__ = (
        # 核心：确保一个用户对一个单词只有一条进度记录
        UniqueConstraint("user_id", "word_id", name="uq_user_word_progress"),
        # 优化：按用户+状态查询（比如查某用户所有未学习的单词）
        Index("ix_progress_user_status", "user_id", "status"),
        # 约束状态值范围
        CheckConstraint("status >= 0 AND status <= 3", name="ck_progress_status_range"),
    )

    def __repr__(self):
        return f"<UserWordProgress user_id={self.user_id} word_id={self.word_id} status={self.status}>"


# ============================================================
# 单词释义表
# ============================================================
class WordTranslation(Base):
    """
    单词释义表
    """
    __tablename__ = "word_translations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word_id = Column(Integer, ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True)

    part_of_speech = Column(String(20), nullable=False, default="")
    translation = Column(Text, nullable=False)

    word = relationship("Word", back_populates="translations")

    __table_args__ = (
        UniqueConstraint("word_id", "part_of_speech", "translation", name="uq_translation_word_pos_text"),
        Index("ix_translations_word_pos", "word_id", "part_of_speech"),
    )

    def __repr__(self):
        return f"<WordTranslation word_id={self.word_id} pos={self.part_of_speech!r} text={self.translation[:20]!r}>"


# ============================================================
# 短语搭配表
# ============================================================
class WordPhrase(Base):
    """
    短语搭配表
    """
    __tablename__ = "word_phrases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word_id = Column(Integer, ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True)

    phrase = Column(String(255), nullable=False)
    translation = Column(Text, nullable=True)

    word = relationship("Word", back_populates="phrases")

    __table_args__ = (
        UniqueConstraint("word_id", "phrase", name="uq_phrase_word_text"),
        Index("ix_phrases_phrase", "phrase"),
    )

    def __repr__(self):
        return f"<WordPhrase word_id={self.word_id} phrase={self.phrase!r}>"


# ============================================================
# 单词本-单词关联表
# ============================================================
class BookWord(Base):
    """
    用户单词本中的单词记录
    """
    __tablename__ = "book_words"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("word_books.id", ondelete="CASCADE"), nullable=False, index=True)
    word_id = Column(Integer, ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True)

    created_at = Column(DateTime, default=_utcnow, nullable=False)

    book = relationship("WordBook", back_populates="book_words")
    word = relationship("Word", back_populates="book_words")

    __table_args__ = (
        UniqueConstraint("book_id", "word_id", name="uq_book_words_book_word"),
    )

    def __repr__(self):
        return f"<BookWord book_id={self.book_id} word_id={self.word_id}>"