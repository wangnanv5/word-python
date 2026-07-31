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
    CheckConstraint
)
from sqlalchemy.orm import relationship

from word_back.database import Base


class User(Base):
    """
    用户表
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 电话号码，唯一
    phone = Column(String(20), unique=True, nullable=True, index=True)

    # 不要存明文密码，要存密码哈希
    password_hash = Column(String(255), nullable=False)

    # 邮箱，唯一
    email = Column(String(120), unique=True, nullable=True, index=True)

    # 姓名
    username = Column(String(50), nullable=False)

    # 昵称，可选
    nickname = Column(String(50), nullable=True)

    # 头像地址，可选
    avatar_url = Column(String(255), nullable=True)

    # 是否激活
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
        nullable=False
    )

    # 一个用户有多个单词本
    word_books = relationship(
        "WordBook",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    # 一个用户可以创建多个单词
    words = relationship(
        "Word",
        back_populates="owner",
        foreign_keys="Word.owner_id"
    )

    def __repr__(self):
        return f"<User id={self.id} username={self.username}>"


class WordBook(Base):
    """
    单词本表
    """
    __tablename__ = "word_books"

    # 单词本类别常量
    CATEGORY_DICTIONARY = "dictionary"      # 词典
    CATEGORY_VOCABULARY = "vocabulary"      # 生词本

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 外键：关联用户
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # 单词本名称
    username = Column(String(100), nullable=False)

    # 类别：dictionary / vocabulary
    category = Column(
        String(20),
        nullable=False,
        default=CATEGORY_VOCABULARY
    )

    # 描述
    description = Column(Text, nullable=True)

    # 单词数量
    # 注意：这是冗余字段，方便查询，但需要程序维护
    word_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
        nullable=False
    )

    # 一个单词本属于一个用户
    user = relationship(
        "User",
        back_populates="word_books"
    )

    # 一个单词本包含多个 book_words 记录
    book_words = relationship(
        "BookWord",
        back_populates="book",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "category IN ('dictionary', 'vocabulary')",
            name="ck_word_books_category"
        ),
        UniqueConstraint(
            "user_id",
            "username",
            "category",
            name="uq_word_books_user_name_category"
        ),
        Index(
            "ix_word_books_user_category",
            "user_id",
            "category"
        )
    )

    def __repr__(self):
        return f"<WordBook id={self.id} username={self.username} category={self.category}>"


class Word(Base):
    """
    单词表
    """
    __tablename__ = "words"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 英语拼写
    spelling = Column(String(100), nullable=False, index=True)

    # 中文意思
    meaning = Column(Text, nullable=False)

    # 音标
    phonetic = Column(String(100), nullable=True)

    # 读音存储位置
    # 建议存文件路径、URL 或对象存储地址，不要直接存音频二进制
    audio_url = Column(String(255), nullable=True)

    # 词性，例如 n. v. adj. adv.
    part_of_speech = Column(String(20), nullable=False, default="")

    # 英文例句
    example_sentence = Column(Text, nullable=True)

    # 例句翻译
    example_translation = Column(Text, nullable=True)

    # 难度，1 到 5
    difficulty = Column(Integer, default=1, nullable=False)

    # 是否公共单词
    # True：系统词典单词
    # False：用户私有单词
    is_public = Column(Boolean, default=False, nullable=False)

    # 创建者
    # 如果为空，表示系统公共单词
    owner_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
        nullable=False
    )

    # 单词创建者
    owner = relationship(
        "User",
        back_populates="words",
        foreign_keys=[owner_id]
    )

    # 一个单词可以出现在多个单词本中
    book_words = relationship(
        "BookWord",
        back_populates="word",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "difficulty BETWEEN 1 AND 5",
            name="ck_words_difficulty"
        ),
        UniqueConstraint(
            "spelling",
            "part_of_speech",
            name="uq_words_spelling_part_of_speech"
        ),
        Index(
            "ix_words_spelling_public",
            "spelling",
            "is_public"
        )
    )

    def __repr__(self):
        return f"<Word id={self.id} spelling={self.spelling}>"


class BookWord(Base):
    """
    单词本-单词关联表

    作用：
    1. 表示某个单词属于某个单词本
    2. 记录该单词在这个单词本里的学习状态
    """
    __tablename__ = "book_words"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 外键：关联单词本
    book_id = Column(
        Integer,
        ForeignKey("word_books.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # 外键：关联单词
    word_id = Column(
        Integer,
        ForeignKey("words.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # 掌握程度
    # 0：未学习
    # 1：学习中
    # 2：熟悉
    # 3：掌握
    # 你也可以扩展成 0 到 5
    mastery_level = Column(Integer, default=0, nullable=False)

    # 复习次数
    review_count = Column(Integer, default=0, nullable=False)

    # 上次复习时间
    last_review_at = Column(DateTime, nullable=True)

    # 下次复习时间
    next_review_at = Column(DateTime, nullable=True)

    # 加入单词本时间
    created_at = Column(DateTime, default=datetime.now(timezone.utc), nullable=False)

    # 关系
    book = relationship(
        "WordBook",
        back_populates="book_words"
    )

    word = relationship(
        "Word",
        back_populates="book_words"
    )

    __table_args__ = (
        CheckConstraint(
            "mastery_level BETWEEN 0 AND 5",
            name="ck_book_words_mastery_level"
        ),
        UniqueConstraint(
            "book_id",
            "word_id",
            name="uq_book_words_book_word"
        ),
        Index(
            "ix_book_words_book_next_review",
            "book_id",
            "next_review_at"
        )
    )

    def __repr__(self):
        return f"<BookWord book_id={self.book_id} word_id={self.word_id}>"