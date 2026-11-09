"""
routes/transaction.py
Endpoint transaksi + pemrosesan latar belakang (BackgroundTasks) + pengaman stok (asyncio.Lock).

Alur satu transaksi:
  POST /transactions
    1. validasi produk terdaftar            -> 404 bila tidak ada
    2. potong stok (critical section/lock)  -> 409 bila stok tidak cukup
    3. simpan transaksi berstatus 'pending'
    4. daftarkan background task, LANGSUNG balas 202 (tidak menunggu pemrosesan)
  Background task (fungsi Python internal, bukan endpoint):
    pending -> processing -> (sleep 3 detik) -> completed   (atau failed bila error)
"""
import asyncio
import os
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

import database as db
from models import StatusTransaksi, TransactionAccepted, TransactionCreate, TransactionOut

router = APIRouter(prefix="/transactions", tags=["Transactions"])

# asyncio.Lock = "gembok" untuk coroutine di dalam SATU event loop / SATU proses.
# Hanya satu coroutine boleh berada di dalam `async with stok_lock` pada satu waktu;
# coroutine lain di-suspend (await) sampai gembok dilepas -> event loop tidak terblokir.
stok_lock = asyncio.Lock()

# Saklar untuk demo B3 (tahap 1 vs tahap 2). Default: lock AKTIF.
#   USE_LOCK=0 uvicorn main:app --port 8000   -> versi TANPA lock (race condition)
USE_LOCK = os.getenv("USE_LOCK", "1") not in ("0", "false", "False")


async def potong_stok_tanpa_lock(item_id: int, qty: int) -> bool:
    """VERSI 1 (rentan race condition): read -> sleep -> write tanpa pengaman."""
    stok_terkini = await db.get_stok(item_id)
    # Jeda buatan: membuka jendela waktu sehingga request lain ikut membaca stok yang SAMA
    # sebelum stok sempat dikurangi (event loop berpindah ke coroutine lain saat await).
    await asyncio.sleep(0.01)
    if stok_terkini is None or stok_terkini < qty:
        return False
    await db.decrement_stok(item_id, qty)
    return True


async def potong_stok_dengan_lock(item_id: int, qty: int) -> bool:
    """VERSI 2 (aman): seluruh read-check-write dibungkus asyncio.Lock."""
    # Critical section: hanya satu coroutine pada satu waktu. Request kedua menunggu di sini,
    # lalu membaca stok yang SUDAH dikurangi sehingga ditolak dengan benar.
    async with stok_lock:
        stok_terkini = await db.get_stok(item_id)
        await asyncio.sleep(0.01)  # jeda yang sama, kini tidak berbahaya
        if stok_terkini is None or stok_terkini < qty:
            return False
        await db.decrement_stok(item_id, qty)
        return True


async def proses_transaksi_background(trx_id: int, item_id: int, qty: int) -> None:
    """Pekerja latar belakang internal (BUKAN endpoint HTTP). Berjalan setelah respons terkirim."""
    try:
        await db.update_trx_status(trx_id, "processing")
        # Simulasi pekerjaan I/O intensif (mis. verifikasi pembayaran). `await` melepas event
        # loop, sehingga request lain tetap dilayani selama 3 detik ini.
        await asyncio.sleep(3)
        await db.update_trx_status(trx_id, "completed")
    except Exception:
        # Kompensasi: kembalikan stok yang sudah dipotong, lalu tandai gagal.
        await db.increment_stok(item_id, qty)
        await db.update_trx_status(trx_id, "failed")


@router.post("", response_model=TransactionAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_transaction(data: TransactionCreate, bg: BackgroundTasks):
    product = await db.get_product(data.item_id)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Produk tidak terdaftar")

    potong = potong_stok_dengan_lock if USE_LOCK else potong_stok_tanpa_lock
    if not await potong(data.item_id, data.qty):
        raise HTTPException(status.HTTP_409_CONFLICT, "Stok habis atau tidak mencukupi")

    trx_id = await db.insert_transaction(
        data.item_id, data.qty, product["harga"] * data.qty, status="pending"
    )
    # Jadwalkan pemrosesan; respons di bawah langsung dikirim tanpa menunggu task selesai.
    bg.add_task(proses_transaksi_background, trx_id, data.item_id, data.qty)
    return {"id": trx_id, "status": "pending", "message": "Transaksi diproses"}


@router.get("", response_model=list[TransactionOut])
async def list_transactions(
    status_filter: Optional[StatusTransaksi] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
):
    return await db.list_transactions(status_filter, skip, limit)


@router.get("/{trx_id}", response_model=TransactionOut)
async def get_transaction(trx_id: int):
    trx = await db.get_transaction(trx_id)
    if trx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaksi tidak ditemukan")
    return trx
