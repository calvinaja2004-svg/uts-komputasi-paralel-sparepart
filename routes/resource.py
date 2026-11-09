"""
routes/resource.py
Endpoint CRUD resource utama: products (suku cadang).
Semua akses DB memakai aiosqlite (async) sehingga event loop tidak terblokir.
"""
from fastapi import APIRouter, HTTPException, Query, status

import database as db
from models import MessageOut, ProductCreate, ProductOut, ProductUpdate

router = APIRouter(prefix="/products", tags=["Products (resource utama)"])


@router.get("", response_model=list[ProductOut])
async def list_products(
    skip: int = Query(0, ge=0, description="Jumlah data yang dilewati"),
    limit: int = Query(10, ge=1, le=100, description="Jumlah data maksimal"),
):
    # I/O-bound: `await` melepas event loop selama menunggu SQLite.
    return await db.list_products(skip, limit)


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(product_id: int):
    product = await db.get_product(product_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Produk tidak ditemukan")
    return product


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(data: ProductCreate):
    new_id = await db.insert_product(**data.model_dump())
    return await db.get_product(new_id)


@router.put("/{product_id}", response_model=ProductOut)
async def update_product(product_id: int, data: ProductUpdate):
    if not await db.update_product(product_id, **data.model_dump()):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Produk tidak ditemukan")
    return await db.get_product(product_id)  # kembalikan data terbaru


@router.delete("/{product_id}", response_model=MessageOut)
async def delete_product(product_id: int):
    if await db.get_product(product_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Produk tidak ditemukan")
    # Produk yang sudah punya riwayat transaksi tidak boleh dihapus (menjaga integritas FK).
    if await db.has_transactions(product_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Produk punya riwayat transaksi dan tidak bisa dihapus"
        )
    await db.delete_product(product_id)  # hard delete
    return {"message": f"Produk {product_id} dihapus permanen"}
