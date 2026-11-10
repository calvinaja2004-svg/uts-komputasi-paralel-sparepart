Video presentasi (YouTube, Unlisted): https://youtu.be/GANTI_DENGAN_LINK_VIDEO

# API Toko Suku Cadang Motor

UTS Komputasi Paralel dan Terdistribusi (Ganjil 2026/2027), Universitas Muhammadiyah Pontianak.
Nama: **CALVIN ANJAS PUTRA** | NIM: **231220101**

REST API suku cadang motor berbasis **FastAPI + aiosqlite (SQLite)**. Resource utama: `products`
(suku cadang, ada kolom `stok`). Resource transaksi: `transactions` (pembelian, diproses di
latar belakang dengan `BackgroundTasks`). Pengurangan stok diamankan dengan `asyncio.Lock`.

## Struktur proyek
```
main.py            inisialisasi FastAPI + registrasi router
database.py        koneksi aiosqlite, skema tabel, semua query
models.py          skema Pydantic (request/response)
routes/resource.py     CRUD products
routes/transaction.py  transaksi async + BackgroundTasks + asyncio.Lock
seed.py            12 data awal
test_race.py       uji race condition (B3)
locustfile.py      skenario uji beban Locust (C1)
benchmark.py       alat bantu: otomatis 1 vs 4 worker -> tabel Markdown
requirements.txt
docs/laporan_uts.pdf
```

## Instalasi (Windows, Python 3.10+)
Buka terminal di VS Code (**Terminal > New Terminal**, PowerShell) pada folder proyek:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python seed.py
```
- Jika `Activate.ps1` ditolak (execution policy), jalankan sekali:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, atau pakai CMD: `.venv\Scripts\activate.bat`.
- Jika perintah `python` tidak dikenal, ganti dengan `py`.
- `python seed.py` mengisi 12 produk awal (`python seed.py --reset` untuk mengulang dari nol).

## Menjalankan server
```powershell
uvicorn main:app --port 8000                 # 1 worker
uvicorn main:app --port 8000 --workers 4     # 4 worker
```
Swagger UI: http://127.0.0.1:8000/docs

## Endpoint
| Method | Path | Keterangan | Status |
|---|---|---|---|
| GET | /products?skip=0&limit=10 | Daftar produk | 200 |
| GET | /products/{id} | Detail produk | 200 / 404 |
| POST | /products | Tambah produk | 201 / 422 |
| PUT | /products/{id} | Perbarui produk | 200 / 404 / 422 |
| DELETE | /products/{id} | Hapus permanen (hard delete) | 200 / 404 / 409* |
| POST | /transactions | Buat transaksi, langsung `pending` | 202 / 404 / 409 / 422 |
| GET | /transactions?status=pending | Daftar transaksi (filter status) | 200 / 422 |
| GET | /transactions/{id} | Detail + status terkini | 200 / 404 |

\* 409 bila produk sudah punya riwayat transaksi (menjaga integritas foreign key).

Status transaksi: `pending -> processing -> completed` (atau `failed`; stok dikembalikan).

## Uji race condition (B3)
Server harus **1 worker**. Pakai dua terminal (terminal 1 = server, terminal 2 = test).

**Tahap 1: TANPA lock** (hasil: kedua request 202, stok akhir -1)
```powershell
# Terminal 1 (PowerShell)
$env:USE_LOCK="0"; uvicorn main:app --port 8000
# Terminal 1 (jika CMD):  set USE_LOCK=0 && uvicorn main:app --port 8000

# Terminal 2
python test_race.py
```
**Tahap 2: DENGAN lock** (hasil: satu 202 dan satu 409). Hentikan server (Ctrl+C), lalu:
```powershell
# Terminal 1 (PowerShell): hapus saklar dulu, atau buka terminal baru
Remove-Item Env:USE_LOCK
uvicorn main:app --port 8000

# Terminal 2
python test_race.py
```
`test_race.py` otomatis menyetel stok produk 1 menjadi 1 sebelum menguji.
Variabel `USE_LOCK` hanya berlaku di terminal tempat ia diset, jadi membuka terminal baru juga mereset ke mode lock.

## Uji beban (C1)
Otomatis (menjalankan server 1 lalu 4 worker, hasilnya tabel Markdown). Pastikan tidak ada server lain di port 8000:
```powershell
python benchmark.py
```
Manual (server sudah jalan dan data sudah di-seed), dari terminal lain:
```powershell
locust -f locustfile.py ReadUser  --headless -u 20 -r 20 --host http://127.0.0.1:8000   # 100 request
locust -f locustfile.py WriteUser --headless -u 10 -r 10 --host http://127.0.0.1:8000   #  50 request
```
Baris `BENCH_RESULT` di akhir output berisi total waktu, throughput, dan rata-rata latensi.
Windows Defender Firewall kadang meminta izin saat Locust/uvicorn pertama kali jalan: pilih **Allow**.

## Catatan desain
- Pemotongan stok terjadi saat `POST /transactions` (di bawah lock), sehingga penolakan 409 muncul
  langsung pada respons. Background task hanya mengubah status dan mensimulasikan pemrosesan 3 detik.
- Tabel `products` tidak memakai `CHECK (stok >= 0)` agar overselling pada tahap 1 B3 dapat diamati.
- `asyncio.Lock` hanya berlaku di dalam satu proses. Pada `--workers 4` lock tiap worker terpisah,
  sehingga race condition antar-worker masih mungkin (lihat analisis di laporan).
