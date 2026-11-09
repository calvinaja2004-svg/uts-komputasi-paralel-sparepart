"""
database.py
Koneksi aiosqlite + inisialisasi tabel + seluruh query (semuanya async / non-blocking).

Keputusan desain:
- Satu koneksi BARU per operasi (open -> query -> commit -> close). Sederhana dan aman
  ketika Uvicorn dijalankan multi-worker (tiap proses punya koneksi sendiri).
- Mode WAL + timeout 30 detik supaya beberapa worker bisa menulis ke satu file SQLite
  tanpa langsung gagal "database is locked".
"""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import aiosqlite

DB_PATH = str(Path(__file__).parent / "sparepart.db")

# CATATAN: tabel products SENGAJA tidak memakai CHECK (stok >= 0).
# Skenario B3 mengharuskan stok akhir BISA negatif pada versi tanpa lock (overselling).
# Dengan CHECK, DB akan menolak decrement kedua (IntegrityError -> HTTP 500) sehingga
# race condition tidak terlihat. Validasi stok tetap dilakukan di level aplikasi.
CREATE_PRODUCTS_TABLE = """
CREATE TABLE IF NOT EXISTS products (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    nama     TEXT    NOT NULL,
    kategori TEXT    NOT NULL,
    merek    TEXT    NOT NULL,
    harga    REAL    NOT NULL,
    stok     INTEGER NOT NULL          -- kolom kuantitas wajib
);
"""

CREATE_TRANSACTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL REFERENCES products(id),
    qty         INTEGER NOT NULL,
    total_harga REAL    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


@asynccontextmanager
async def get_db():
    """Buka koneksi aiosqlite baru; tutup otomatis saat blok selesai."""
    async with aiosqlite.connect(DB_PATH, timeout=30) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn


async def init_db() -> None:
    """Buat tabel (idempotent). Dipanggil saat startup tiap worker."""
    async with get_db() as conn:
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute(CREATE_PRODUCTS_TABLE)
        await conn.execute(CREATE_TRANSACTIONS_TABLE)
        await conn.commit()


# ───────────────────────── Products ─────────────────────────
async def list_products(skip: int, limit: int) -> list[dict]:
    async with get_db() as conn:
        cur = await conn.execute(
            "SELECT * FROM products ORDER BY id LIMIT ? OFFSET ?", (limit, skip)
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_product(product_id: int) -> Optional[dict]:
    async with get_db() as conn:
        cur = await conn.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def insert_product(nama: str, kategori: str, merek: str, harga: float, stok: int) -> int:
    async with get_db() as conn:
        cur = await conn.execute(
            "INSERT INTO products (nama, kategori, merek, harga, stok) VALUES (?,?,?,?,?)",
            (nama, kategori, merek, harga, stok),
        )
        await conn.commit()
        return cur.lastrowid


async def update_product(product_id: int, nama: str, kategori: str, merek: str,
                         harga: float, stok: int) -> bool:
    async with get_db() as conn:
        cur = await conn.execute(
            "UPDATE products SET nama=?, kategori=?, merek=?, harga=?, stok=? WHERE id=?",
            (nama, kategori, merek, harga, stok, product_id),
        )
        await conn.commit()
        return cur.rowcount > 0


async def delete_product(product_id: int) -> bool:
    """Hard delete: baris benar-benar dihapus dari tabel."""
    async with get_db() as conn:
        cur = await conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
        await conn.commit()
        return cur.rowcount > 0


async def has_transactions(product_id: int) -> bool:
    async with get_db() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM transactions WHERE item_id = ? LIMIT 1", (product_id,)
        )
        return await cur.fetchone() is not None


# ───────────────────────── Stok ─────────────────────────
async def get_stok(item_id: int) -> Optional[int]:
    async with get_db() as conn:
        cur = await conn.execute("SELECT stok FROM products WHERE id = ?", (item_id,))
        row = await cur.fetchone()
        return row["stok"] if row else None


async def decrement_stok(item_id: int, qty: int) -> None:
    # UPDATE tanpa kondisi: sengaja, agar celah race condition (B3 tahap 1) terlihat.
    async with get_db() as conn:
        await conn.execute("UPDATE products SET stok = stok - ? WHERE id = ?", (qty, item_id))
        await conn.commit()


async def increment_stok(item_id: int, qty: int) -> None:
    """Kompensasi stok bila transaksi gagal. Atomic di level SQL."""
    async with get_db() as conn:
        await conn.execute("UPDATE products SET stok = stok + ? WHERE id = ?", (qty, item_id))
        await conn.commit()


# ───────────────────────── Transactions ─────────────────────────
async def insert_transaction(item_id: int, qty: int, total_harga: float, status: str) -> int:
    async with get_db() as conn:
        cur = await conn.execute(
            "INSERT INTO transactions (item_id, qty, total_harga, status) VALUES (?,?,?,?)",
            (item_id, qty, total_harga, status),
        )
        await conn.commit()
        return cur.lastrowid


async def update_trx_status(trx_id: int, status: str) -> None:
    async with get_db() as conn:
        await conn.execute(
            "UPDATE transactions SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
            (status, trx_id),
        )
        await conn.commit()


async def get_transaction(trx_id: int) -> Optional[dict]:
    async with get_db() as conn:
        cur = await conn.execute("SELECT * FROM transactions WHERE id = ?", (trx_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def list_transactions(status: Optional[str], skip: int, limit: int) -> list[dict]:
    async with get_db() as conn:
        if status:
            cur = await conn.execute(
                "SELECT * FROM transactions WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (status, limit, skip),
            )
        else:
            cur = await conn.execute(
                "SELECT * FROM transactions ORDER BY id DESC LIMIT ? OFFSET ?", (limit, skip)
            )
        return [dict(r) for r in await cur.fetchall()]
