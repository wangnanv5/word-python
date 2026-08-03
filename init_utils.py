import json
import click
from pathlib import Path
from typing import Iterator
from sqlalchemy.orm import sessionmaker,Session
from word_back.models import Word, WordTranslation,WordPhrase,SystemDictionary
from sqlalchemy import create_engine, select, and_

from word_back.database import Base, engine

def load_words(json_path: str) -> Iterator[dict]:
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"JSON 顶层结构应为 list 或含 list 字段的 dict，实际为 {type(data)}")

    for item in data:
        yield item

def import_words(json_path: str,batch_size: int = 1000):

    # SQLite 性能优化参数
    @__import__("sqlalchemy.event").event.listens_for(engine, "connect")
    def _sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA cache_size=1000000")
        cursor.close()

    Session = sessionmaker(bind=engine)
    session = Session()

    # --- 统计计数器 ---
    stats = {
        "total": 0,        # JSON 中总单词数
        "inserted": 0,     # 新插入
        "skipped": 0,      # 已存在跳过
        "errors": 0,       # 解析/写入失败
    }

    batch_buffer = []   # 待提交的 Word 对象

    print(f"正在读取: {json_path}")
    print("-" * 60)

    def flush_batch():
        """将缓冲区中的单词一次性提交"""
        if not batch_buffer:
            return
        try:
            session.add_all(batch_buffer)
            session.commit()
        except Exception as e:
            # 如果批量提交失败（如唯一约束冲突），逐条插入以跳过坏数据
            session.rollback()
            print(f"  ⚠️  批量提交失败，切换为逐条模式: {e}")
            for w in batch_buffer:
                try:
                    session.add(w)
                    session.commit()
                except Exception as e2:
                    session.rollback()
                    stats["errors"] += 1
                    print(f"  ⚠️  跳过单词 [{w.spelling}]: {e2}")
        batch_buffer.clear()

    try:
        for word_data in load_words(json_path):
            stats["total"] += 1
            spelling = word_data.get("word", "").strip()

            if not spelling:
                stats["errors"] += 1
                print(f"  ⚠️  跳过无效记录（缺少 word 字段）: {word_data}")
                continue

            # --- 去重检查 ---
            existing = session.query(Word.id).filter_by(spelling=spelling).first()
            if existing:
                stats["skipped"] += 1
                continue

            # --- 构建 Word 对象 ---
            try:
                word = Word(
                    spelling=spelling,
                    us=word_data.get("us") or word_data.get("phonetic_us"),
                    uk=word_data.get("uk") or word_data.get("phonetic_uk"),
                )

                # 释义
                for t in word_data.get("translations", []):
                    trans = WordTranslation(
                        part_of_speech=t.get("type", ""),
                        translation=t.get("translation", ""),
                    )
                    word.translations.append(trans)

                # 短语
                for p in word_data.get("phrases", []):
                    phrase = WordPhrase(
                        phrase=p.get("phrase", ""),
                        translation=p.get("translation", ""),
                    )
                    word.phrases.append(phrase)

                batch_buffer.append(word)
                stats["inserted"] += 1

            except Exception as e:
                stats["errors"] += 1
                print(f"  ⚠️  解析失败 [{spelling}]: {e}")
                continue

            # --- 达到批量阈值，提交 ---
            if len(batch_buffer) >= batch_size:
                flush_batch()

        # --- 提交最后一批 ---
        flush_batch()

    except KeyboardInterrupt:
        print("\n⚠️  用户中断，正在回滚当前批次...")
        session.rollback()
        raise

    finally:
        session.close()

    # --- 打印统计报告 ---
    print()
    print("=" * 60)
    print("📊 导入完成统计")
    print("=" * 60)
    print(f"  总记录数:   {stats['total']}")
    print(f"  新插入:     {stats['inserted']}")
    print(f"  已跳过:     {stats['skipped']}  (数据库中已存在)")
    print(f"  失败:       {stats['errors']}")
    print("=" * 60)

def get_or_create_system_dictionary(session: Session) -> SystemDictionary:
    """获取唯一的系统词典，不存在则创建"""
    dictionary = session.execute(
        select(SystemDictionary).limit(1)
    ).scalar_one_or_none()

    if dictionary is None:
        dictionary = SystemDictionary(
            name="系统词典",
            description="平台默认提供的全局共享词典",
            version=1,
        )
        session.add(dictionary)
        session.flush()  # 获取 id
        print("✅ 创建系统词典 id=%s", dictionary.id)
    else:
        print("📖 已存在系统词典 id=%s version=%s",
                    dictionary.id, dictionary.version)
    return dictionary

@click.group()
@click.version_option("1.0.0", prog_name="filetool")
def cli():
    pass

# uv run .\init_utils.py create-db
# @cli.command(name="create_db")
@cli.command()
@click.option("--json_folder_path",default=r"D:\english-vocabulary-master\json_original\json-sentence")
def create_db(json_folder_path):
    # 创建空表，加载所有的单词到一个单词本中，作为词典。
    Base.metadata.create_all(bind=engine)

    json_file_list = [f for f in Path(json_folder_path).iterdir() if f.name.endswith(".json")]

    for json_file in json_file_list:
        print(f"正在处理文件: {json_file}")
        import_words(json_file)
    click.echo(click.style(f"数据库创建成功", fg="green", bold=True))



if __name__ == "__main__":
    cli()