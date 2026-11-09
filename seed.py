"""
seed.py
Mengisi data awal 12 produk suku cadang (syarat minimal 10 baris).
Pemakaian:
    python seed.py            # isi data bila tabel masih kosong
    python seed.py --reset    # hapus semua data (produk + transaksi) lalu isi ulang
"""
import asyncio
import sys

import database as db

PRODUCTS = [
    # (nama, kategori, merek, harga, stok)
    ("Kampas Rem Depan Beat", "Rem", "Honda Genuine Parts", 45000, 150),
    ("Kampas Rem Belakang Vario", "Rem", "Honda Genuine Parts", 38000, 120),
    ("Oli Mesin 0.8L", "Pelumas", "Yamalube", 52000, 200),
    ("Oli Gardan 120ml", "Pelumas", "Federal", 15000, 180),
    ("Busi Iridium", "Kelistrikan", "NGK", 85000, 100),
    ("Aki Kering 12V 5Ah", "Kelistrikan", "GS Astra", 210000, 100),
    ("Filter Udara Mio", "Mesin", "Yamaha Genuine Parts", 40000, 130),
    ("Rantai Keteng 428H", "Penggerak", "SSS", 120000, 100),
    ("Ban Tubeless 80/90-14", "Roda", "FDR", 175000, 110),
    ("V-Belt Nmax", "Penggerak", "Yamaha Genuine Parts", 185000, 100),
    ("Lampu Depan LED", "Kelistrikan", "Osram", 95000, 140),
    ("Kabel Gas Universal", "Kontrol", "Aspira", 25000, 160),
]


async def main() -> None:
    reset = "--reset" in sys.argv
    if reset:
        async with db.get_db() as conn:
            await conn.execute("DROP TABLE IF EXISTS transactions")
            await conn.execute("DROP TABLE IF EXISTS products")
            await conn.commit()
    await db.init_db()

    async with db.get_db() as conn:
        cur = await conn.execute("SELECT COUNT(*) AS n FROM products")
        if (await cur.fetchone())["n"] > 0:
            print("Tabel products sudah berisi data. Pakai --reset untuk mengisi ulang.")
            return
        await conn.executemany(
            "INSERT INTO products (nama, kategori, merek, harga, stok) VALUES (?,?,?,?,?)",
            PRODUCTS,
        )
        await conn.commit()
    print(f"Seed selesai: {len(PRODUCTS)} produk dimasukkan ke {db.DB_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
