from loguru import logger
from typing import Optional, Literal
from fastapi import FastAPI, Depends,  status, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import or_

from word_back.database import get_db
from word_back.models import User
from word_back.crud import (
    create_user,
    get_user_by_username,
    delete_word_book,
    get_word_books_by_user_paged,
    clone_wordbook_to_user,
    get_wordbook_words,
    get_system_book_except_user_book_paged,
    mark_word_as_mode,
    search_words,
    word_to_view
)
from word_back.schemas.word_book_schema import (
    UserCreate,
    WordItem,
    HttpResponse,
    LoginRequest,
    Token,
    UserInfo,
    AddSystemBookToUser,
    WordPageResponse,
    WordBookListData,
    AddWordToVocabularySchema
)
from word_back.auth import get_current_user

from word_back.routers import *

app = FastAPI(
    title="背单词 API",
    description="用户、单词本、单词接口",
    version="1.0.0"
)

API_PREFIX = "/api"

app.include_router(
    auth_router.router,
    prefix=f"{API_PREFIX}/auth",
    tags=["Authentication"]
)

# 允许跨域
# 生产环境不要随便用 *，要改成你的前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5777"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 获取用户信息
@app.get("/api/user/info", response_model=HttpResponse)
def get_user_info():
    user_info = UserInfo(roles=["super"],realName = "小王")
    return HttpResponse(data=user_info.model_dump())



# 把指定的单词标记为已学习状态,并且假如到生词本中
@app.post("/api/change-word-status",response_model=HttpResponse)
def change_word_status(payload: AddWordToVocabularySchema,db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    try:
        user_id = current_user.id
        mark_word_as_mode(db,user_id, payload.word_id,payload.mode)
        return HttpResponse(code=0,data=None,message="添加成功")
    except Exception as e:
        logger.error(e)
        return HttpResponse(code=-1,data=None,message="添加失败")

# 模糊查找 Word 单词（按拼写部分匹配）
@app.get("/api/words/search", response_model=HttpResponse[list[WordItem]])
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
        return HttpResponse(code=-1, data=None, message="搜索单词失败")

    # 3. 转为 WordItem 列表（为空时返回空列表而非报错）
    if not words:
        return HttpResponse(code=0, data=[], message="未找到匹配的单词")

    items = [word_to_view(w) for w in words]
    return HttpResponse(code=0, data=items, message="搜索单词成功")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
    # uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=False)
    # uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4