#!/usr/bin/env python3
"""Small bounded HTTP load tool. No third-party Python packages required."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import os
import signal
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

stop = threading.Event()
lock = threading.Lock()
counts = Counter()


def request(base, method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = Request(base + path, data=data, method=method,
                  headers={'Content-Type': 'application/json'})
    try:
        response = urlopen(req, timeout=3)
    except HTTPError as error:
        response = error
    with response:
        payload = response.read()
        return response.status, payload


def send(base, item_id, index):
    # Every 100 requests per replica: 3% missing id, 3% invalid body.
    position = index % 100
    if position < 3:
        method, path, body = 'GET', '/items/9223372036854775807', None
    elif position < 6:
        method, path, body = 'POST', '/items', {'name': ''}
    elif index % 3 == 0:
        method, path, body = 'POST', '/items', {'name': 'background-item'}
    elif index % 3 == 1:
        method, path, body = 'GET', '/items/' + str(item_id), None
    else:
        method, path, body = 'PUT', '/items/' + str(item_id), {'name': 'updated-item'}
    try:
        status, _ = request(base, method, path, body)
        key = str(status)
    except (URLError, OSError, TimeoutError):
        key = 'network_error'
    with lock:
        counts[key] += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=float, default=0,
                        help='Stop after this many seconds; 0 means run until stopped')
    args = parser.parse_args()
    bases = [url.strip().rstrip('/') for url in os.getenv(
        'APP_URLS', 'http://app-1:8080,http://app-2:8080').split(',') if url.strip()]
    target = float(os.getenv('TARGET_RPS', '30'))
    ramp = float(os.getenv('RAMP_SECONDS', '120'))
    if not bases or not 1 <= target <= 50 or ramp < 0:
        raise ValueError('Require URLs, TARGET_RPS in 1..50 and nonnegative RAMP_SECONDS')
    ids = []
    for base in bases:
        status, body = request(base, 'POST', '/items', {'name': 'seed-item'})
        if status != 201:
            raise RuntimeError('Cannot seed ' + base + ': HTTP ' + str(status))
        ids.append(json.loads(body)['id'])
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    started = time.monotonic()
    next_send = started
    report_at = started + 10
    last_total = 0
    pending = set()
    number = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        while not stop.is_set():
            now = time.monotonic()
            elapsed = now - started
            if args.duration > 0 and elapsed >= args.duration:
                break
            rps = target if ramp == 0 else min(target, 2 + (target - 2) * min(elapsed / ramp, 1))
            if now < next_send:
                stop.wait(min(next_send - now, .2))
                continue
            pending = {future for future in pending if not future.done()}
            if len(pending) < 32:
                replica = number % len(bases)
                # Separate sequence per replica guarantees equal error proportions.
                index = number // len(bases)
                pending.add(pool.submit(send, bases[replica], ids[replica], index))
                number += 1
            else:
                with lock:
                    counts['scheduler_skipped'] += 1
            next_send = max(next_send + 1 / rps, now)
            if now >= report_at:
                with lock:
                    snapshot = dict(counts)
                total = sum(v for k, v in snapshot.items() if k != 'scheduler_skipped')
                print(f'target={rps:.1f} actual={(total-last_total)/10:.1f} RPS; totals={snapshot}', flush=True)
                last_total = total
                report_at = now + 10
    print('Stopped; totals:', dict(counts), flush=True)


if __name__ == '__main__':
    main()
