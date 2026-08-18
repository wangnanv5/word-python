from pydantic import BaseModel, Field, ConfigDict
from typing import  Optional,  Optional

# =====================
# 单词相关
# =====================

class TranslationItem(BaseModel):
    pos: str = Field(description="词性")
    text: str = Field(description="中文释义")
    model_config = ConfigDict(from_attributes=True)

class PhraseItem(BaseModel):
    phrase: str = Field(description="短语")
    translation: Optional[str] = Field(description="短语翻译")
    model_config = ConfigDict(from_attributes=True)

class WordItem(BaseModel):
    """单个单词的完整信息"""
    id: int
    spelling: str = Field(description="单词拼写", example="apple")
    us: Optional[str] = Field(description="美式音标", example="/ˈæp.əl/")
    uk: Optional[str] = Field(description="英式音标", example="/ˈæp.əl/")
    audio_url: Optional[str] = Field(description="发音音频地址")
    translations: list[TranslationItem] = Field(default_factory=list, description="释义列表")
    phrases: list[PhraseItem] = Field(default_factory=list, description="短语列表")
    model_config = ConfigDict(from_attributes=True)
    status: int = 0  # 新增：学习状态，默认0（未学习）
    
class PageMeta(BaseModel):
    """分页元信息"""
    page: int = Field(description="当前页码（从 1 开始）")
    page_size: int = Field(description="每页数量")
    total: int = Field(description="总记录数")
    total_pages: int = Field(description="总页数")
    has_next: bool = Field(description="是否有下一页")
    has_prev: bool = Field(description="是否有上一页")

class WordPageResponse(BaseModel):
    """分页结果"""
    items: list[WordItem] = Field(default_factory=list)
    meta: PageMeta = Field(default_factory=PageMeta)