"""
test_race.py
Uji race condition B3: dua request POST /transactions dikirim SERENTAK untuk produk id=1
yang stoknya hanya 1. Skrip ini menyetel stok produk 1 menjadi 1 sebelum menguji, lalu
menampilkan stok akhir.

Tahap 1 (tanpa lock): server dijalankan dengan   USE_LOCK=0
    -> kedua request sukses (202) dan stok akhir -1 (overselling)
Tahap 2 (dengan lock): server dijalankan biasa   (USE_LOCK default 1)
    -> satu request 202, satu request 409 Conflict, stok akhir 0

Pemakaian:  python test_race.py            (server harus 1 worker pada port 8000)
"""
import asyncio
import sys

import httpx

BASE = "http://127.0.0.1:8000"
ITEM_ID = 1


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as client:
        # 1) Setel stok produk menjadi 1 (PUT butuh body lengkap, jadi baca dulu data produknya).
        r = await client.get(f"/products/{ITEM_ID}")
        if r.status_code != 200:
            sys.exit(f"Produk {ITEM_ID} tidak ada. Jalankan dulu: python seed.py")
        p = r.json()
        body = {k: p[k] for k in ("nama", "kategori", "merek", "harga")} | {"stok": 1}
        await client.put(f"/products/{ITEM_ID}", json=body)
        print(f"Stok produk {ITEM_ID} disetel ke 1")

        # 2) Dua request serentak.
        payload = {"item_id": ITEM_ID, "qty": 1}
        req1 = client.post("/transactions", json=payload)
        req2 = client.post("/transactions", json=payload)
        res1, res2 = await asyncio.gather(req1, req2)
        print("Respon Request 1:", res1.status_code, res1.json())
        print("Respon Request 2:", res2.status_code, res2.json())

        # 3) Stok akhir.
        stok = (await client.get(f"/products/{ITEM_ID}")).json()["stok"]
        print(f"Stok akhir produk {ITEM_ID}: {stok}")
        if stok < 0:
            print(">> RACE CONDITION: overselling terjadi (stok negatif)")
        elif sorted([res1.status_code, res2.status_code]) == [202, 409]:
            print(">> AMAN: satu transaksi sukses, satu ditolak 409 Conflict")


if __name__ == "__main__":
    asyncio.run(main())
