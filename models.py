"""
models.py
Skema Pydantic untuk validasi request body dan serialisasi response.
Pelanggaran validasi otomatis menghasilkan HTTP 422 Unprocessable Entity.
"""
from typing import Literal

from pydantic import BaseModel, Field

StatusTransaksi = Literal["pending", "processing", "completed", "failed"]


class ProductBase(BaseModel):
    nama: str = Field(..., min_length=1, max_length=100, examples=["Kampas Rem Depan"])
    kategori: str = Field(..., min_length=1, max_length=50, examples=["Rem"])
    merek: str = Field(..., min_length=1, max_length=50, examples=["Honda Genuine Parts"])
    harga: float = Field(..., gt=0, examples=[45000])
    stok: int = Field(..., ge=0, examples=[25])


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ProductBase):
    pass


class ProductOut(BaseModel):
    """Response: tanpa batas ge=0 pada stok agar stok negatif (overselling pada demo
    B3 tahap 1) tetap bisa ditampilkan apa adanya, bukan malah memicu error 500."""
    id: int
    nama: str
    kategori: str
    merek: str
    harga: float
    stok: int


class TransactionCreate(BaseModel):
    item_id: int = Field(..., ge=1, examples=[1])
    qty: int = Field(..., ge=1, examples=[1])


class TransactionOut(BaseModel):
    id: int
    item_id: int
    qty: int
    total_harga: float
    status: StatusTransaksi
    created_at: str
    updated_at: str


class TransactionAccepted(BaseModel):
    id: int
    status: StatusTransaksi
    message: str


class MessageOut(BaseModel):
    message: str
