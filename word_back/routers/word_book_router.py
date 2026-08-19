from loguru import logger
from typing import Optional, Literal
from fastapi import  Depends,  status, Query,APIRouter
from sqlalchemy.orm import Session

from word_back.database import get_db
from word_back.models import User
from word_back.crud import (
    delete_word_book,
    get_word_books_by_user_paged,
    clone_wordbook_to_user,
    get_wordbook_words,
    get_system_book_except_user_book_paged
)
from word_back.auth import get_current_user
from word_back.schemas import *

router = APIRouter()

# =====================
# 单词本接口
# =====================
    
# 获取当前用户的所有单词本 for vxe
@router.get("/all-vxe",response_model=HttpResponse[WordBookListData])
def get_word_books_by_user_paged_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1, description="当前页码，从1开始"),
    page_size: int = Query(10, ge=1, le=200,alias="pageSize", description="每页条数"),
    sort_by: str = Query(None, description="排序列名，如 name、created_at"),
    sort_order: str = Query(None, description="排序方向：asc 或 desc"),
):
    books, total = get_word_books_by_user_paged(
        db=db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    result = WordBookListData(items=books, total=total)
    return HttpResponse(code=0,data=result,message="获取所有单词本成功")

# 获取所有的系统单词本,排除已有的单词本 for vxe
@router.get("/system-vxe",response_model=HttpResponse[WordBookListData])
def get_system_book_except_user_book_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1, description="当前页码，从1开始"),
    page_size: int = Query(10, ge=1, le=200,alias="pageSize", description="每页条数"),
    sort_by: str = Query(None, description="排序列名，如 name、created_at"),
    sort_order: str = Query(None, description="排序方向：asc 或 desc"),
):
    books, total = get_system_book_except_user_book_paged(
        db, current_user.id, page, page_size, sort_by, sort_order
    )
    result = WordBookListData(items=books, total=total)
    return HttpResponse(code=0,data=result,message="获取系统单词本成功")

# 用户添加指定的系统单词本 
@router.post("/add",response_model=HttpResponse)
def add_system_book_to_user(payload: AddSystemBookToUser,db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    try:
        clone_wordbook_to_user(db, current_user.id,payload.system_book_id)
        return HttpResponse(code=0,data=None,message="添加系统单词本成功")
    except Exception as e:
        logger.error(e)
        return HttpResponse(code=status.HTTP_500_INTERNAL_SERVER_ERROR,data=None,message="添加系统单词本失败")

# 用户删除指定的单词本
@router.post("/delete",response_model=HttpResponse)
def delete_user_book(payload: AddSystemBookToUser,db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    try:
        delete_word_book(db, payload.system_book_id,current_user.id)
        return HttpResponse(code=0,data=None,message="删除单词本成功")
    except Exception as e:
        logger.error(e)
        return HttpResponse(code=status.HTTP_500_INTERNAL_SERVER_ERROR,data=None,message="删除单词本失败")

# 获取用户某个单词本里的所有单词
@router.get("/words",response_model=HttpResponse[WordPageResponse])
def list_words(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    book_id: Optional[int] = Query(default=None),
    sort: Literal["spelling", "created_at"] = Query(default="spelling"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),mode : int = Query(default=0)
):
    try:
        user_id = user.id
        result = get_wordbook_words(
            db = db,
            user_id=user_id,
            book_id=book_id,
            page=page,
            page_size=page_size,
            sort = sort,mode=mode
        )
    except PermissionError as e:
        logger.error(e)
        return HttpResponse(code=status.HTTP_500_INTERNAL_SERVER_ERROR,data=None,message="获取所有单词失败")
    return HttpResponse(code=0, data=result, message="获取单词成功")