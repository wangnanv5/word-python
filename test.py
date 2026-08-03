
import argparse
import json
import csv
import logging
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, select, and_
from sqlalchemy.orm import Session

# ---------- 日志配置 ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------- 数据库连接 ----------
# 实际项目中建议从配置/环境变量读取
DATABASE_URL = "sqlite:///./word_back.db"  # 替换为你的真实连接串
engine = create_engine(DATABASE_URL, echo=False, future=True)

# 延迟导入模型，确保 Base.metadata 已注册
from models import (  # noqa: E402
    SystemDictionary,
    SystemDictionaryWord,
    Word,
)


# ============================================================
# 核心函数
# ============================================================
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
        logger.info("✅ 创建系统词典 id=%s", dictionary.id)
    else:
        logger.info("📖 已存在系统词典 id=%s version=%s",
                    dictionary.id, dictionary.version)
    return dictionary


def add_words_to_dictionary(
    session: Session,
    dictionary: SystemDictionary,
    word_ids: Iterable[int],
) -> int:
    """
    将一批 word_id 加入系统词典（自动去重）
    返回：本次新增的记录数
    """
    word_ids = list(set(word_ids))  # 去重
    if not word_ids:
        return 0

    # 查询已存在的记录，避免唯一约束冲突
    existing = session.execute(
        select(SystemDictionaryWord.word_id).where(
            and_(
                SystemDictionaryWord.dictionary_id == dictionary.id,
                SystemDictionaryWord.word_id.in_(word_ids),
            )
        )
    ).scalars().all()

    existing_set = set(existing)
    new_word_ids = [wid for wid in word_ids if wid not in existing_set]

    for wid in new_word_ids:
        session.add(SystemDictionaryWord(
            dictionary_id=dictionary.id,
            word_id=wid,
        ))

    session.flush()
    logger.info("➕ 新增 %d 个单词到系统词典（已有 %d 个）",
                len(new_word_ids), len(existing_set))
    return len(new_word_ids)


def init_from_existing_words(session: Session) -> int:
    """将 words 表中所有已有单词加入系统词典"""
    dictionary = get_or_create_system_dictionary(session)

    # 分批查询，避免大表一次性加载
    BATCH_SIZE = 5000
    total_new = 0
    offset = 0

    while True:
        word_ids = session.execute(
            select(Word.id).order_by(Word.id).offset(offset).limit(BATCH_SIZE)
        ).scalars().all()

        if not word_ids:
            break

        total_new += add_words_to_dictionary(session, dictionary, word_ids)
        offset += BATCH_SIZE
        logger.info("📦 已处理 %d 个单词...", offset)

    return total_new


def load_words_from_json(filepath: str) -> list[dict]:
    """
    从 JSON 文件加载单词数据
    期望格式：
    [
      {
        "spelling": "apple",
        "us": "/ˈæpəl/",
        "uk": "/ˈæpl/",
        "audio_url": "https://...",
        "translations": [{"pos": "n", "text": "苹果"}],
        "phrases": [{"phrase": "apple pie", "translation": "苹果派"}]
      }
    ]
    """
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_words_from_csv(filepath: str) -> list[dict]:
    """
    从 CSV 文件加载单词数据
    期望列：spelling,us,uk,audio_url,translation(可选)
    """
    words = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            words.append(dict(row))
    return words


def import_words(session: Session, word_data: list[dict]) -> int:
    """
    导入单词并加入系统词典
    返回新增单词数
    """
    from models import Word, WordTranslation, WordPhrase  # noqa: E402

    dictionary = get_or_create_system_dictionary(session)
    new_count = 0

    for data in word_data:
        spelling = data["spelling"].strip().lower()
        if not spelling:
            continue

        # 查找或创建单词
        word = session.execute(
            select(Word).where(Word.spelling == spelling)
        ).scalar_one_or_none()

        if word is None:
            word = Word(
                spelling=spelling,
                us=data.get("us"),
                uk=data.get("uk"),
                audio_url=data.get("audio_url"),
            )
            session.add(word)
            session.flush()
            new_count += 1

        # 添加释义
        for trans in data.get("translations", []):
            pos = trans.get("pos", "")
            text = trans.get("text", "")
            if not text:
                continue
            existing = session.execute(
                select(WordTranslation).where(
                    and_(
                        WordTranslation.word_id == word.id,
                        WordTranslation.part_of_speech == pos,
                        WordTranslation.translation == text,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(WordTranslation(
                    word_id=word.id,
                    part_of_speech=pos,
                    translation=text,
                ))

        # 添加短语
        for phrase_data in data.get("phrases", []):
            phrase_text = phrase_data.get("phrase", "").strip()
            if not phrase_text:
                continue
            existing = session.execute(
                select(WordPhrase).where(
                    and_(
                        WordPhrase.word_id == word.id,
                        WordPhrase.phrase == phrase_text,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(WordPhrase(
                    word_id=word.id,
                    phrase=phrase_text,
                    translation=phrase_data.get("translation"),
                ))

    session.flush()

    # 将所有新单词加入系统词典
    all_word_ids = [w.id for w in session.execute(select(Word)).scalars().all()]
    add_words_to_dictionary(session, dictionary, all_word_ids)

    return new_count


# ============================================================
# 主入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="系统词典初始化工具")
    parser.add_argument(
        "--file", "-f",
        help="单词数据文件路径（JSON 或 CSV）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览操作，不写入数据库",
    )
    args = parser.parse_args()

    if args.dry_run:
        logger.info("🔍 DRY RUN 模式 — 不会写入数据库")
        # 仅打印统计信息
        with Session(engine, future=True) as session:
            word_count = session.execute(select(Word.id)).scalars().count()
            dict_exists = session.execute(
                select(SystemDictionary).limit(1)
            ).scalar_one_or_none()
            logger.info("  当前单词总数: %d", word_count)
            logger.info("  系统词典状态: %s", "已存在" if dict_exists else "未创建")
        return

    # 实际执行
    with Session(engine, future=True) as session:
        if args.file:
            filepath = args.file
            logger.info("📂 从文件导入: %s", filepath)
            if filepath.endswith(".json"):
                word_data = load_words_from_json(filepath)
            elif filepath.endswith(".csv"):
                word_data = load_words_from_csv(filepath)
            else:
                logger.error("❌ 不支持的文件格式，请使用 .json 或 .csv")
                return

            new_count = import_words(session, word_data)
            logger.info("✅ 导入完成，新增单词 %d 个", new_count)
        else:
            logger.info("🚀 开始初始化系统词典（全量模式）...")
            total_new = init_from_existing_words(session)

            # 递增版本号
            dictionary = session.execute(
                select(SystemDictionary).limit(1)
            ).scalar_one_or_none()
            if dictionary:
                dictionary.version += 1
                logger.info("📌 系统词典版本升至 %d", dictionary.version)

            logger.info("🎉 初始化完成，本次新增 %d 条记录", total_new)

        session.commit()
        logger.info("💾 已提交事务")


if __name__ == "__main__":
    main()
