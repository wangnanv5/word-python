from word_back.database import Base, engine, SessionLocal

from word_back.crud import (
    create_user,
    create_word_book,
    create_word,
    add_word_to_book,
    get_words_in_book
)

from word_back.models import WordBook


# 创建所有表
Base.metadata.create_all(bind=engine)


# if __name__ == "__main__":
#     db = SessionLocal()

#     # 创建用户
#     user = create_user(
#         db=db,
#         phone="13800000000",
#         password="123456",
#         email="neo@example.com",
#         name="Neo",
#         nickname="尼奥"
#     )

#     print("创建用户成功：", user)

#     # 创建一个生词本
#     vocabulary_book = create_word_book(
#         db=db,
#         user_id=user.id,
#         name="我的生词本",
#         category=WordBook.CATEGORY_VOCABULARY,
#         description="平时遇到的生词"
#     )

#     # 创建一个词典单词本
#     dictionary_book = create_word_book(
#         db=db,
#         user_id=user.id,
#         name="四级词典",
#         category=WordBook.CATEGORY_DICTIONARY,
#         description="大学英语四级单词"
#     )

#     print("创建单词本成功：", vocabulary_book, dictionary_book)

#     # 创建单词
#     word_abandon = create_word(
#         db=db,
#         spelling="abandon",
#         meaning="放弃；抛弃",
#         phonetic="/əˈbændən/",
#         audio_url="/static/audio/abandon.mp3",
#         part_of_speech="v",
#         example_sentence="He abandoned his plan.",
#         example_translation="他放弃了他的计划。",
#         difficulty=2,
#         is_public=True,
#         owner_id=None
#     )

#     word_absorb = create_word(
#         db=db,
#         spelling="absorb",
#         meaning="吸收；吸引",
#         phonetic="/əbˈzɔːrb/",
#         audio_url="/static/audio/absorb.mp3",
#         part_of_speech="v",
#         example_sentence="Plants absorb water.",
#         example_translation="植物吸收水分。",
#         difficulty=2,
#         is_public=True,
#         owner_id=None
#     )

#     print("创建单词成功：", word_abandon, word_absorb)

#     # 把单词加入单词本
#     add_word_to_book(db, vocabulary_book.id, word_abandon.id)
#     add_word_to_book(db, vocabulary_book.id, word_absorb.id)
#     add_word_to_book(db, dictionary_book.id, word_abandon.id)

#     # 查询单词本里的单词
#     words = get_words_in_book(db, vocabulary_book.id)

#     print("生词本里的单词：")
#     for word in words:
#         print(word.spelling, word.meaning)

#     db.close()