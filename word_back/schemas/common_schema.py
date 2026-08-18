from pydantic import BaseModel,  ConfigDict
from typing import Generic, Optional, TypeVar,Optional

T = TypeVar("T")

class HttpResponse(BaseModel, Generic[T]):
    """
    统一响应结构，对应前端 interface HttpResponse<T>
    """
    code: int = 0          # 0 表示成功，其他表示失败
    data: Optional[T] = None
    message: str = ""

    model_config = ConfigDict(from_attributes=True)