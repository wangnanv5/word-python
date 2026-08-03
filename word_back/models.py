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

    phone = Column(String(20), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(120), unique=True, nullable=True, index=True)
    username = Column(String(50), nullable=False)
    nickname = Column(String(50), nullable=True)
    avatar_url = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    # 用户私有单词本（不含系统词典）
    word_books = relationship(
        "WordBook",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<User id={self.id} username={self.username}>"


# ============================================================
# 用户私有单词本表
# ============================================================
class WordBook(Base):
    """
    用户私有单词本表
    只存放用户自己创建的单词本（dictionary / vocabulary 类别均在此）
    系统全局词典不在此表中，见 SystemDictionary
    """
    __tablename__ = "word_books"

    CATEGORY_DICTIONARY = "dictionary"
    CATEGORY_VOCABULARY = "vocabulary"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 注意：字段名原本叫 username，实际存的是单词本名称，改名为 name 更语义化
    name = Column(String(100), nullable=False)

    category = Column(String(20), nullable=False, default=CATEGORY_DICTIONARY)

    description = Column(Text, nullable=True)

    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    user = relationship("User", back_populates="word_books")
    book_words = relationship(
        "BookWord",
        back_populates="book",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "category IN ('dictionary', 'vocabulary')",
            name="ck_word_books_category",
        ),
        # (user_id, name) 已能唯一标识一个用户的单词本，category 去掉以减少索引宽度
        UniqueConstraint("user_id", "name", name="uq_word_books_user_name"),
        Index("ix_word_books_user_category", "user_id", "category"),
    )

    def __repr__(self):
        return f"<WordBook id={self.id} name={self.name} category={self.category}>"


# ============================================================
# 系统全局词典（新增）
# ============================================================
class SystemDictionary(Base):
    """
    系统默认词典（全局唯一 / 全局共享）
    不属于任何用户，所有用户登录后都能看到
    """
    __tablename__ = "system_dictionary"

    id = Column(Integer, primary_key=True, autoincrement=True)

    name = Column(String(100), nullable=False, default="系统词典")
    description = Column(Text, nullable=True)

    # 版本号：方便后续做词典热更新 / 增量同步
    version = Column(Integer, default=1, nullable=False)

    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    # 反向关系
    entries = relationship(
        "SystemDictionaryWord",
        back_populates="dictionary",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<SystemDictionary id={self.id} name={self.name} version={self.version}>"


class SystemDictionaryWord(Base):
    """
    系统词典中的单词关联表
    一条记录 = 系统词典包含一个单词
    """
    __tablename__ = "system_dictionary_words"

    id = Column(Integer, primary_key=True, autoincrement=True)

    dictionary_id = Column(
        Integer,
        ForeignKey("system_dictionary.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    word_id = Column(
        Integer,
        ForeignKey("words.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = Column(DateTime, default=_utcnow, nullable=False)

    dictionary = relationship("SystemDictionary", back_populates="entries")
    word = relationship("Word")

    __table_args__ = (
        UniqueConstraint(
            "dictionary_id", "word_id",
            name="uq_sys_dict_dictionary_word",
        ),
        # 覆盖索引：按单词查所属词典
        Index("ix_sys_dict_word_dictionary", "word_id", "dictionary_id"),
    )

    def __repr__(self):
        return f"<SystemDictionaryWord dict_id={self.dictionary_id} word_id={self.word_id}>"


# ============================================================
# 单词主表
# ============================================================
class Word(Base):
    """
    单词表
    """
    __tablename__ = "words"

    id = Column(Integer, primary_key=True, autoincrement=True)

    spelling = Column(String(100), nullable=False, index=True)
    us = Column(String(100), nullable=True)   # 美式音标
    uk = Column(String(100), nullable=True)   # 英式音标
    audio_url = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    translations = relationship(
        "WordTranslation",
        back_populates="word",
        cascade="all, delete-orphan",
    )
    phrases = relationship(
        "WordPhrase",
        back_populates="word",
        cascade="all, delete-orphan",
    )
    book_words = relationship(
        "BookWord",
        back_populates="word",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        # 唯一约束：拼写全局唯一，避免重复单词
        UniqueConstraint("spelling", name="uq_words_spelling"),
        # 复合索引：按拼写前缀模糊搜索时加速（B-Tree 对 LIKE 'abc%' 有效）
        Index("ix_words_spelling_created", "spelling", "created_at"),
    )

    def __repr__(self):
        return f"<Word id={self.id} spelling={self.spelling!r}>"


# ============================================================
# 单词释义表
# ============================================================
class WordTranslation(Base):
    """
    单词释义表
    一个单词可以有多个词性 + 对应中文释义
    """
    __tablename__ = "word_translations"

    id = Column(Integer, primary_key=True, autoincrement=True)

    word_id = Column(
        Integer,
        ForeignKey("words.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    part_of_speech = Column(String(20), nullable=False, default="")
    translation = Column(Text, nullable=False)

    word = relationship("Word", back_populates="translations")

    __table_args__ = (
        UniqueConstraint(
            "word_id", "part_of_speech", "translation",
            name="uq_translation_word_pos_text",
        ),
        # 新增：按词性查询时加速（如"只查名词释义"）
        Index("ix_translations_word_pos", "word_id", "part_of_speech"),
    )

    def __repr__(self):
        return (
            f"<WordTranslation word_id={self.word_id} "
            f"pos={self.part_of_speech!r} text={self.translation[:20]!r}>"
        )


# ============================================================
# 短语搭配表
# ============================================================
class WordPhrase(Base):
    """
    短语搭配表
    """
    __tablename__ = "word_phrases"

    id = Column(Integer, primary_key=True, autoincrement=True)

    word_id = Column(
        Integer,
        ForeignKey("words.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    phrase = Column(String(255), nullable=False)
    translation = Column(Text, nullable=True)

    word = relationship("Word", back_populates="phrases")

    __table_args__ = (
        UniqueConstraint("word_id", "phrase", name="uq_phrase_word_text"),
        # 新增：按短语内容搜索时加速
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
    可在此扩展复习算法字段（如 sm-2 间隔重复）
    """
    __tablename__ = "book_words"

    id = Column(Integer, primary_key=True, autoincrement=True)

    book_id = Column(
        Integer,
        ForeignKey("word_books.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    word_id = Column(
        Integer,
        ForeignKey("words.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = Column(DateTime, default=_utcnow, nullable=False)

    # ---- 复习算法预留字段 ----
    next_review_at = Column(DateTime, nullable=True, index=True)
    review_count = Column(Integer, default=0, nullable=False)
    ease_factor = Column(Integer, default=250, nullable=False)  # *100 存储，避免浮点

    book = relationship("WordBook", back_populates="book_words")
    word = relationship("Word", back_populates="book_words")

    __table_args__ = (
        UniqueConstraint("book_id", "word_id", name="uq_book_words_book_word"),
        # 复习队列查询：(book_id, next_review_at) 覆盖索引
        Index(
            "ix_book_words_review_queue",
            "book_id", "next_review_at", "word_id",
        ),
    )

    def __repr__(self):
        return f"<BookWord book_id={self.book_id} word_id={self.word_id}>"
