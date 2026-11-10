"""
locustfile.py
Skenario uji beban C1. Ada dua kelas user; pilih lewat nama kelas:
    ReadUser   : GET /products          -> 100 request, 20 user konkuren
    WriteUser  : POST /transactions     ->  50 request, 10 user konkuren

Contoh (headless):
    locust -f locustfile.py ReadUser  --headless -u 20 -r 20 --host http://127.0.0.1:8000
    locust -f locustfile.py WriteUser --headless -u 10 -r 10 --host http://127.0.0.1:8000

Locust tidak punya batas "jumlah request" bawaan, jadi di sini dibuat penghitung:
  - tiap user "mengklaim" 1 slot sebelum mengirim request (tidak akan melebihi batas),
  - setelah semua request selesai, runner dihentikan dan ringkasan dicetak
    sebagai satu baris  BENCH_RESULT {...}  (dibaca oleh benchmark.py).
"""
import json
import random
import time

import gevent
from locust import HttpUser, constant, events, task
from locust.exception import StopUser


class _Quota:
    """Penghitung batas request (aman karena gevent bersifat kooperatif)."""
    limit = 0
    claimed = 0
    done = 0
    t_start = None
    t_end = None


def _claim() -> bool:
    if _Quota.claimed >= _Quota.limit:
        return False
    _Quota.claimed += 1
    if _Quota.t_start is None:
        _Quota.t_start = time.perf_counter()
    return True


@events.request.add_listener
def _on_request(**kwargs):
    _Quota.done += 1
    _Quota.t_end = time.perf_counter()
    env = _on_request.env
    if _Quota.limit and _Quota.done >= _Quota.limit:
        # quit() dijalankan di greenlet terpisah: bila dipanggil langsung dari greenlet user,
        # greenlet itu ikut terbunuh sebelum request terakhir sempat tercatat.
        gevent.spawn(env.runner.quit)


@events.init.add_listener
def _on_init(environment, **kwargs):
    _on_request.env = environment


@events.quitting.add_listener
def _on_quit(environment, **kwargs):
    total = environment.stats.total
    elapsed = (_Quota.t_end - _Quota.t_start) if _Quota.t_start else 0.0
    print("BENCH_RESULT " + json.dumps({
        "requests": total.num_requests,
        "failures": total.num_failures,
        "total_time_s": round(elapsed, 3),
        "throughput_rps": round(total.num_requests / elapsed, 2) if elapsed else 0,
        "avg_latency_ms": round(total.avg_response_time, 2),
    }))


class ReadUser(HttpUser):
    """Skenario Read: GET /products, 100 request, konkurensi 20."""
    wait_time = constant(0)

    def on_start(self):
        _Quota.limit = 100

    @task
    def list_products(self):
        if not _claim():
            raise StopUser()
        self.client.get("/products?skip=0&limit=10", name="GET /products")


class WriteUser(HttpUser):
    """Skenario Write: POST /transactions, 50 request, konkurensi 10."""
    wait_time = constant(0)

    def on_start(self):
        _Quota.limit = 50

    @task
    def create_transaction(self):
        if not _claim():
            raise StopUser()
        # qty=1 pada produk acak id 1..10 (stok seed >= 100, jadi tidak akan habis).
        self.client.post(
            "/transactions",
            json={"item_id": random.randint(1, 10), "qty": 1},
            name="POST /transactions",
        )
