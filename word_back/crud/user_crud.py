from sqlalchemy import select
from sqlalchemy.orm import Session

from word_back.define import INIT_NICKNAME
from word_back.models import User
from word_back.auth import pwd_context
from word_back.crud import create_word_book

# =====================
# 用户相关
# =====================

# 创建用户 并且创建一个默认生词本
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
        role = role
    )
    try:
        db.add(user)
        db.flush()  # 拿到 user.id，不提交事务
        if user.role == "super":
            # 创建系统单词本
            create_word_book(db, user_id=user.id,name="默认生词本")

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