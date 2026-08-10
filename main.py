import math
from loguru import logger
from typing import List,Optional, Literal
from fastapi import FastAPI, Depends,  status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import or_

from word_back.define import SYSTEM_DICTIONARY_VIRTUAL_ID
from word_back.database import get_db
from word_back.models import User
from word_back.crud import (
    create_user,
    get_user_by_username,
    delete_word_book,
    get_word_books_by_user,
    clone_wordbook_to_user,
    get_wordbook_words,
    get_system_book_except_user_book,
    mark_word_as_learned
)
from word_back.schemas import (
    UserCreate,
    HttpResponse,
    LoginRequest,
    Token,
    UserInfo,
    WordBookOut,
    AddSystemBookToUser,
    WordPageResponse,
    PageMeta,
    WordBookListData,
    MarkWordAsLearnedSchema
)
from word_back.auth import (
    create_access_token,
    verify_password,
    get_current_user
)

app = FastAPI(
    title="背单词 API",
    description="用户、单词本、单词接口",
    version="1.0.0"
)

# 允许跨域
# 生产环境不要随便用 *，要改成你的前端域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5779"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =====================
# 认证接口
# =====================

# 注册
@app.post("/api/auth/register",response_model=HttpResponse,status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    exists = (db.query(User).filter( or_(User.username == payload.username)).first())

    if exists:
        return HttpResponse(code=status.HTTP_400_BAD_REQUEST,data=None, message="用户名已注册")

    create_user(db=db,password=payload.password,username=payload.username)

    return HttpResponse(code=0, data=None, message="注册成功")


# 登录
@app.post("/api/auth/login",response_model=HttpResponse[Token])
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = get_user_by_username(db, payload.username)

    if not user:
        return HttpResponse(code=-1,data=None,message="此用户名未注册")

    if not verify_password(payload.password, user.password_hash):
        return HttpResponse(code=-1,data=None,message="密码错误")

    access_token = create_access_token(user.id)

    return HttpResponse(code=0, data={"accessToken":access_token}, message="登录成功")


# 退出登录
@app.post("/api/auth/logout")
def logout():
    return HttpResponse(code=0, data=None, message="登录成功")


# 获取用户信息
@app.get("/api/user/info", response_model=HttpResponse)
def get_user_info():
    user_info = UserInfo(roles=["super"],realName = "小王")
    return HttpResponse(data=user_info.model_dump())


# =====================
# 单词本接口
# =====================
    
# 获取当前用户的所有单词本
@app.get("/api/word-books",response_model=HttpResponse[List[WordBookOut]])
def list_books(db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    all_books = get_word_books_by_user(db, current_user.id)
    return HttpResponse(code=0,data=all_books,message="获取所有单词本成功")

# 获取当前用户的所有单词本 for vxe
@app.get("/api/word-books-vxe",response_model=HttpResponse[WordBookListData])
def list_books_vxe(db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    all_books = get_word_books_by_user(db, current_user.id)
    data = WordBookListData(
            items=[WordBookOut.model_validate(b) for b in all_books],
            total=len(all_books)
        )
    return HttpResponse(code=0,data=data,message="获取所有单词本成功")

# 获取所有的系统单词本 for vxe
@app.get("/api/system-word-books-vxe",response_model=HttpResponse[WordBookListData])
def list_books_vxe(db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    all_books = get_system_book_except_user_book(db,current_user.id)
    data = WordBookListData(
            items=[WordBookOut.model_validate(b) for b in all_books],
            total=len(all_books)
        )
    return HttpResponse(code=0,data=data,message="获取系统单词本成功")

# 用户添加指定的系统单词本 
@app.post("/api/add-system-word-books-to-user",response_model=HttpResponse)
def add_system_book_to_user(payload: AddSystemBookToUser,db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    try:
        clone_wordbook_to_user(db, current_user.id,payload.system_book_id)
        return HttpResponse(code=0,data=None,message="添加系统单词本成功")
    except Exception as e:
        logger.error(e)
        return HttpResponse(code=-1,data=None,message="添加系统单词本失败")

# 用户删除指定的单词本
@app.post("/api/delete-user-book",response_model=HttpResponse)
def add_system_book_to_user(payload: AddSystemBookToUser,db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    try:
        delete_word_book(db, payload.system_book_id,current_user.id)
        return HttpResponse(code=0,data=None,message="删除单词本成功")
    except Exception as e:
        logger.error(e)
        return HttpResponse(code=-1,data=None,message="删除单词本失败")

# 获取某个单词本里的所有单词
@app.get("/api/words",response_model=HttpResponse[WordPageResponse])
def list_words(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    book_id: Optional[int] = Query(default=None),
    sort: Literal["spelling", "created_at"] = Query(default="spelling"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_book_id = SYSTEM_DICTIONARY_VIRTUAL_ID if book_id is None else book_id
    try:
        user_id = user.id
        result = get_wordbook_words(
            db = db,
            user_id=user_id,
            book_id=target_book_id,
            page=page,
            page_size=page_size,
            sort = sort
        )
    except PermissionError as e:
        logger.error(e)
        return HttpResponse(code=status.HTTP_403_FORBIDDEN,data=None,message="获取所有单词失败")

    items = result.items
    
    total_pages = math.ceil(result.total / page_size) if page_size > 0 else 0
    meta = PageMeta(
        page=page,
        page_size=page_size,
        total=result.total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

    word_page_response = WordPageResponse(
        items=items,
        meta=meta,
    )

    return HttpResponse(code=0, data=word_page_response, message="获取单词成功")

# 把指定的单词标记为已学习状态
@app.post("/api/mark-word-as-learned",response_model=HttpResponse)
def mark_word_as_learned_api(payload: MarkWordAsLearnedSchema,db: Session = Depends(get_db)):
    try:
        mark_word_as_learned(db, payload.word_id)
        return HttpResponse(code=0,data=None,message="删除单词本成功")
    except Exception as e:
        logger.error(e)
        return HttpResponse(code=-1,data=None,message="删除单词本失败")

# 把指定的单词标记为已学习状态,并且假如到生词本中
@app.post("/api/mark-word-as-learned",response_model=HttpResponse)
def mark_word_as_learned_api(payload: MarkWordAsLearnedSchema,db: Session = Depends(get_db)):
    try:
        mark_word_as_learned(db, payload.word_id)
        return HttpResponse(code=0,data=None,message="删除单词本成功")
    except Exception as e:
        logger.error(e)
        return HttpResponse(code=-1,data=None,message="删除单词本失败")

# # 删除单词本中的某个单词
# @app.delete(
#     "/api/word-books/{book_id}/words/{word_id}",
#     response_model=HttpResponse
# )
# def delete_word_from_book(
#     book_id: int,
#     word_id: int,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):
#     book = get_user_book_or_404(db, book_id, current_user.id)

#     if not remove_word_from_book(db, book_id, word_id):
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="单词不存在"
#         )

#     return HttpResponse(code=0, data=None, message="删除单词成功")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    # uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4