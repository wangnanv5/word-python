from loguru import logger
from fastapi import APIRouter, Depends,  status, Query, Header
from sqlalchemy.orm import Session

from word_back.database import get_db
from word_back.models import User
from word_back.crud import (
    mark_word_as_mode,
    search_words,
    word_to_view
)
from word_back.schemas import AddWordToVocabularySchema, HttpResponse, WordItem
from word_back.auth import get_current_user

router = APIRouter()

# 把指定的单词标记为已学习状态,并且假如到生词本中
@router.post("/change",response_model=HttpResponse)
def change_word_status(payload: AddWordToVocabularySchema,db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    try:
        user_id = current_user.id
        mark_word_as_mode(db,user_id, payload.word_id,payload.mode)
        return HttpResponse(code=0,data=None,message="添加成功")
    except Exception as e:
        logger.error(e)
        return HttpResponse(code=status.HTTP_404_NOT_FOUND,data=None,message="添加失败")

# 模糊查找 Word 单词（按拼写部分匹配）
@router.get("/search", response_model=HttpResponse[list[WordItem]])
def search_words_route(
    q: str = Query(default="", description="查询关键词"),
    limit: int = Query(default=10, ge=1, le=100, description="返回数量"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # 1. 输入校验：去空格、判空
    keyword = (q or "").strip()
    if not keyword:
        return HttpResponse(code=0, data=[], message="查询成功（空关键词返回空列表）")

    try:
        # 2. 模糊匹配查询
        words = search_words(db=db, keyword=keyword, limit=limit)
    except Exception as e:
        logger.error(e)
        return HttpResponse(code=status.HTTP_404_NOT_FOUND, data=None, message="搜索单词失败")

    # 3. 转为 WordItem 列表（为空时返回空列表而非报错）
    if not words:
        return HttpResponse(code=0, data=[], message="未找到匹配的单词")

    items = [word_to_view(w) for w in words]
    return HttpResponse(code=0, data=items, message="搜索单词成功")