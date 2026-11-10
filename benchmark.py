"""
benchmark.py (alat bantu, bukan syarat UTS)
Menjalankan otomatis C1: server 1 worker lalu 4 worker, tiap kali diuji dengan Locust
(skenario Read & Write di locustfile.py), lalu mencetak tabel hasil dalam format Markdown.

Pemakaian:  python benchmark.py
Target: Windows (juga jalan di Linux/macOS). Jangan jalankan server lain di port 8000.
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request

PORT = 8000
HOST = f"http://127.0.0.1:{PORT}"
ROOT = os.path.dirname(os.path.abspath(__file__))
SCENARIOS = [  # (label, kelas locust, jumlah user)
    ("GET /products", "ReadUser", 20),
    ("POST /transactions", "WriteUser", 10),
]


def start_server(workers: int) -> subprocess.Popen:
    kw = {"start_new_session": True} if os.name != "nt" else {}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--port", str(PORT),
         "--workers", str(workers), "--log-level", "warning"],
        cwd=ROOT, **kw)
    for _ in range(60):  # tunggu sampai server siap
        try:
            urllib.request.urlopen(HOST + "/", timeout=1)
            return proc
        except Exception:
            time.sleep(0.5)
    stop_server(proc)
    sys.exit("Server tidak kunjung siap")


def stop_server(proc: subprocess.Popen) -> None:
    if os.name == "nt":  # matikan seluruh pohon proses (parent + worker)
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    proc.wait()
    time.sleep(2)  # beri waktu Windows melepas port 8000 sebelum server berikutnya


def run_locust(cls: str, users: int) -> dict:
    out = subprocess.run(
        [sys.executable, "-m", "locust", "-f", "locustfile.py", cls, "--headless",
         "-u", str(users), "-r", str(users), "--host", HOST, "--only-summary"],
        cwd=ROOT, capture_output=True, text=True)
    for line in (out.stdout + out.stderr).splitlines():
        if "BENCH_RESULT" in line:
            return json.loads(line.split("BENCH_RESULT", 1)[1])
    sys.exit("Hasil Locust tidak ditemukan:\n" + out.stdout[-800:] + out.stderr[-800:])


def main() -> None:
    rows = []
    for workers in (1, 4):
        for label, cls, users in SCENARIOS:
            subprocess.run([sys.executable, "seed.py", "--reset"], cwd=ROOT, capture_output=True)
            proc = start_server(workers)
            try:
                r = run_locust(cls, users)
            finally:
                stop_server(proc)
            rows.append((label, workers, r))
            print(f"[selesai] {label} | {workers} worker | {r}", flush=True)

    print("\n| Skenario | Worker | Total Waktu (s) | Throughput (req/s) | Rata-rata Latensi (ms) | Gagal |")
    print("|---|---|---|---|---|---|")
    for label, w, r in rows:
        print(f"| {label} | {w} | {r['total_time_s']} | {r['throughput_rps']} | "
              f"{r['avg_latency_ms']} | {r['failures']}/{r['requests']} |")


if __name__ == "__main__":
    main()
