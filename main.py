"""
main.py
Inisialisasi aplikasi FastAPI dan registrasi router.
Jalankan:  uvicorn main:app --port 8000        (tambah --workers 4 untuk multi-worker)
Swagger UI: http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

import database as db
from routes import resource, transaction


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()  # buat tabel bila belum ada (dijalankan tiap worker)
    yield


app = FastAPI(
    title="API Toko Suku Cadang Motor",
    description="UTS Komputasi Paralel dan Terdistribusi: FastAPI + aiosqlite + BackgroundTasks + asyncio.Lock",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(resource.router)
app.include_router(transaction.router)


@app.get("/", tags=["Root"])
async def root():
    return {"app": "API Toko Suku Cadang Motor", "docs": "/docs"}
