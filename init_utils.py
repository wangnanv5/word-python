import json
import click
from loguru import logger
from pathlib import Path
from typing import Iterator
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event

from word_back.crud import create_user
from word_back.define import CATEGORY_DICTIONARY,SYSTEM_DICTIONARY_ID
from word_back.database import Base, engine
from word_back.models import Word, WordTranslation,WordPhrase,WordBook,BookWord,User

def load_words(json_path: Path) -> Iterator[dict]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"JSON 顶层结构应为 list 或含 list 字段的 dict，实际为 {type(data)}")

    for item in data:
        yield item

# SQLite 性能优化参数
@event.listens_for(engine, "connect")
def _sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA cache_size=1000000")
    finally:
        cursor.close()

def import_words(json_path: Path,user_id=None):

    Session = sessionmaker(bind=engine)
    session = Session()

    book_name = json_path.stem
    word_book = session.query(WordBook).filter_by(user_id=user_id, name=book_name).first()
    if not word_book:
        word_book = WordBook(
            user_id=user_id,
            name=book_name,
            category=CATEGORY_DICTIONARY,  # 用户自建单词本通常归类为 vocabulary
            description=f"从文件 {book_name} 导入的单词本"
        )
        session.add(word_book)
        session.flush()  # 必须 flush 以获取数据库生成的 word_book.id

    # --- 统计计数器 ---
    stats = {
        "total": 0,        # JSON 中总单词数
        "inserted": 0,     # 新插入
        "skipped": 0,      # 已存在跳过
        "errors": 0,       # 解析/写入失败
    }

    logger.info(f"正在读取: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        words_data = json.load(f)

    spellings = [item.get('word') for item in words_data if item.get('word')]
    existing_words = session.query(Word).filter(Word.spelling.in_(spellings)).all()

    word_map = {w.spelling: w for w in existing_words}

    # 看目前的单词本已经有哪些单词了
    existing_book_word_ids = set(bw.word_id for bw in session.query(BookWord.word_id).filter_by(book_id=word_book.id).all())

    for item in words_data:
        stats["total"] += 1
        spelling = item.get('word')

        if not spelling:
            stats["errors"] += 1
            logger.warning(f"  ⚠️  跳过无效记录（缺少 word 字段）: {item}")
            continue

        if spelling not in word_map:
            try:
                new_word = Word(
                    spelling=spelling,
                    us=item.get('us'),
                    uk=item.get('uk'),
                    audio_url=item.get('audio_url')
                )
                session.add(new_word)
                session.flush()  # 获取 new_word.id

                # 添加释义 (请根据你实际的 JSON 结构调整字段名)
                for trans in item.get('translations', []):
                    session.add(WordTranslation(
                        word_id=new_word.id,
                        part_of_speech=trans.get('type', ''),
                        translation=trans.get('translation', '')
                    ))

                # 添加短语
                for phrase in item.get('phrases', []):
                    session.add(WordPhrase(
                        word_id=new_word.id,
                        phrase=phrase.get('phrase', ''),
                        translation=phrase.get('translation', '')
                    ))

                # 将新单词加入映射表
                word_map[spelling] = new_word
            except Exception as e:
                stats["errors"] += 1
                logger.error(f"  ⚠️  解析失败 [{spelling}]: {e}")
                continue
        else:
            stats["skipped"] += 1
            continue

        word = word_map[spelling]

        if word.id not in existing_book_word_ids:
            session.add(BookWord(book_id=word_book.id, word_id=word.id))
            existing_book_word_ids.add(word.id)  

    try:
        session.commit()
        # --- 打印统计报告 ---
        logger.info("📊 导入完成统计")
        logger.info(f"  总记录数:   {stats['total']}")
        logger.info(f"  新插入:     {stats['inserted']}")
        logger.info(f"  已跳过:     {stats['skipped']}  (数据库中已存在)")
        logger.info(f"  失败:       {stats['errors']}")
    except Exception as e:
        session.rollback()
        logger.error(f"导入失败，事务已回滚: {e}")

@click.group()
@click.version_option("1.0.0", prog_name="filetool")
def cli():
    pass

# uv run ./init_utils.py create-db
# @cli.command(name="create_db") 
@cli.command()
def create_db():
    # 初始化数据库,创建空表
    Base.metadata.create_all(bind=engine)

    # 系统词典借用 user_id=SYSTEM_DICTIONARY_ID(1) 存储，但外键要求 users 表中必须存在该记录。
    # 这里显式插入一条系统用户，避免 add_system_word 插入 word_books 时触发
    # FOREIGN KEY constraint failed。
    Session = sessionmaker(bind=engine)
    session = Session()
    if not session.get(User, SYSTEM_DICTIONARY_ID):
        from word_back.auth import pwd_context
        from word_back.define import INIT_PASSWORD
        system_user = User(
            id=SYSTEM_DICTIONARY_ID,
            username="__system__",
            password_hash=pwd_context.hash(INIT_PASSWORD),
            nickname="system",
            role="system",
            is_active=True,
        )
        session.add(system_user)
        session.commit()
        click.echo(click.style(f"已创建系统用户 id={SYSTEM_DICTIONARY_ID}", fg="green"))
    else:
        click.echo(f"系统用户 id={SYSTEM_DICTIONARY_ID} 已存在，跳过")
    session.close()

    click.echo(click.style(f"数据库创建成功", fg="green", bold=True))

# uv run ./init_utils.py add-system-word --json_folder_path="D:\english-vocabulary-master\json_original\json-sentence"
# @cli.command(name="create_db") 
@cli.command()
@click.option("--json_folder_path",default=r"/root/work/data/json-sentence/")
def add_system_word(json_folder_path):
    json_file_list = [f for f in Path(json_folder_path).iterdir() if f.name.endswith(".json")]

    for json_file in json_file_list:
        logger.info(f"正在处理文件: {json_file}")
        import_words(json_file,SYSTEM_DICTIONARY_ID)

    # click.echo(click.style(f"词典初始化成功", fg="green", bold=True))

if __name__ == "__main__":
    cli()