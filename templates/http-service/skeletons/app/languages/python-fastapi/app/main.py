from fastapi import FastAPI

from app.routers import root

app = FastAPI(title="${{ values.name }}")

app.include_router(root.router)
