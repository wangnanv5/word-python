from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from word_back.routers import auth_router, word_book_router, word_router

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

app.include_router(
    word_book_router.router,
    prefix=f"{API_PREFIX}/word-book",
    tags=["Word Book"]
)

app.include_router(
    word_router.router,
    prefix=f"{API_PREFIX}/word",
    tags=["Word"]
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
    # uvicorn.run("main:app", host="127.0.0.1", port=8080, reload=False)
    # uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4