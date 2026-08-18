from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal,List, Optional

# =====================
# 单词本相关
# =====================

class AddWordToBookRequest(BaseModel):
    word_id: int

class BookWordOut(BaseModel):
    id: int
    book_id: int
    word_id: int
    mastery_level: int
    review_count: int
    last_review_at: Optional[datetime] = None
    next_review_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class AddSystemBookToUser(BaseModel):
    system_book_id: int = Field(alias="systemBookId")
    model_config = ConfigDict(from_attributes=True,validate_by_name=True,validate_by_alias=True)

class MarkWordAsLearnedSchema(BaseModel):
    word_id: int = Field(alias="wordId")
    model_config = ConfigDict(from_attributes=True,validate_by_name=True,validate_by_alias=True)

class AddWordToVocabularySchema(BaseModel):
    word_id: int = Field(alias="wordId")
    mode: int = Field(alias="mode")
    model_config = ConfigDict(from_attributes=True,validate_by_name=True,validate_by_alias=True)

class WordBookOut(BaseModel):
    id: int
    name: str = Field( ..., min_length=1, max_length=100, description="单词本名称")
    unlearned_count : int 
    category: Literal["dictionary", "vocabulary"] = Field(
        default="vocabulary",
        description="dictionary: 词典, vocabulary: 生词本"
    )

    description: Optional[str] = Field(None,max_length=255,description="单词本描述")    
    model_config = ConfigDict(from_attributes=True)

class WordBookListData(BaseModel):
    """系统单词本列表数据结构（支持分页/总数统计）"""
    items: List[WordBookOut]
    total: int