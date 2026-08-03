from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

# SQLite 数据库文件
SQLALCHEMY_DATABASE_URL = "sqlite:///./word_app.db"

# 创建数据库引擎
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

# SQLite 配置
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection,connection_record):
    cursor = dbapi_connection.cursor()

    # 开启外键约束
    cursor.execute("PRAGMA foreign_keys=ON")

    # 提高 SQLite 并发能力
    cursor.execute("PRAGMA journal_mode=WAL")

    # 设置 busy timeout，减少 database is locked 问题
    cursor.execute("PRAGMA busy_timeout=5000")

    cursor.close()


# Session 工厂
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# ORM 模型基类
Base = declarative_base()


# FastAPI 依赖注入可用
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()