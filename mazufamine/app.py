#!/usr/bin/env python3
"""MazufaMine 0.1: local, read-only RainbowMiner dashboard. Python 3.10+."""
import argparse
import concurrent.futures
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
ENDPOINTS = ('getdevices', 'runningminers', 'currentprofit', 'balances')

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect refused')

def fetch(base, endpoint):
    if endpoint not in ENDPOINTS:
        raise ValueError('Read endpoint not allowed')
    parsed = urlsplit(base)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('Use an HTTP(S) origin without credentials or path')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(base.rstrip('/') + '/' + endpoint, timeout=5) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('Response too large')
    data = json.loads(raw)
    if isinstance(data, dict) and data.get('Success') is False:
        raise ValueError('RainbowMiner reported failure')
    if endpoint == 'getdevices' and (not isinstance(data, dict) or not isinstance(data.get('Available'), list) or not isinstance(data.get('Active'), list)):
        raise ValueError('Unsupported getdevices response')
    return data

def amount(value):
    try:
        n = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('Invalid decimal amount') from None
    if not n.is_finite() or n < 0:
        raise ValueError('Amounts must be finite and non-negative')
    return n

class Ledger:
    """EUR-valued cash events; fees already inside net proceeds must not be imported."""
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL, kind TEXT NOT NULL, eur TEXT NOT NULL)')
    def connect(self):
        return sqlite3.connect(self.path, timeout=10)
    def import_csv(self, path):
        added = 0
        with open(path, newline='', encoding='utf-8') as handle, self.connect() as db:
            for row in csv.DictReader(handle):
                if row['kind'] not in ('sale_net', 'fee_extra', 'transfer', 'electricity'):
                    raise ValueError('Unknown ledger kind')
                date = datetime.fromisoformat(row['occurred_at'].replace('Z', '+00:00'))
                if date.tzinfo is None or not row['id'].strip():
                    raise ValueError('Require timezone and unique event id')
                event = (row['id'], date.astimezone(timezone.utc).isoformat(), row['kind'], str(amount(row['eur'])))
                previous = db.execute('SELECT id, occurred_at, kind, eur FROM events WHERE id=?', (event[0],)).fetchone()
                if previous and previous != event:
                    raise ValueError('Conflicting duplicate event: ' + event[0])
                if not previous:
                    db.execute('INSERT INTO events VALUES (?,?,?,?)', event)
                    added += 1
        return added
    def summary(self):
        totals = {k: Decimal(0) for k in ('sale_net', 'fee_extra', 'transfer', 'electricity')}
        with self.connect() as db:
            rows = db.execute('SELECT kind, eur FROM events').fetchall()
        for kind, eur in rows:
            totals[kind] += Decimal(eur)
        net = totals['sale_net'] - sum(totals[k] for k in ('fee_extra', 'transfer', 'electricity'))
        return {'events': len(rows), 'net_eur': str(net) if rows else None,
                'totals_eur': {k: str(v) for k, v in totals.items()},
                'scope': 'Imported events only; incomplete costs mean incomplete net result'}

class Monitor:
    def __init__(self, rigs, ledger, demo=False, interval=15):
        self.rigs, self.ledger, self.demo, self.interval = rigs, ledger, demo, interval
        self.cache, self.lock, self.stop = {}, threading.Lock(), threading.Event()
    def poll(self):
        def read(rig, endpoint):
            try:
                if self.demo:
                    samples = {'getdevices': {'Available': [{'Name':'GPU#00','Type':'Gpu','Model_Name':'RX 580 (esimerkki)'}], 'Active':['GPU#00']}, 'runningminers': [{'Name':'Esimerkkilouhija','Algorithm':['demo']}], 'currentprofit': {'note':'Demo: ei tuottoennustetta'}, 'balances': []}
                    data = samples[endpoint]
                else:
                    data = fetch(rig['url'], endpoint)
                return rig['name'], endpoint, data, None
            except Exception as error:
                # Do not expose response bodies, URLs or credentials in logs/UI.
                return rig['name'], endpoint, None, type(error).__name__
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            jobs = [pool.submit(read, r, e) for r in self.rigs for e in ENDPOINTS]
            for job in concurrent.futures.as_completed(jobs):
                name, endpoint, data, error = job.result()
                with self.lock:
                    item = self.cache.setdefault(name, {}).setdefault(endpoint, {})
                    item['error'] = error
                    item['attempt_at'] = time.time()
                    if error is None:
                        item.update(data=data, observed_at=time.time())
    def run(self):
        while not self.stop.is_set():
            self.poll()
            self.stop.wait(self.interval)
    def snapshot(self):
        with self.lock:
            rigs = json.loads(json.dumps(self.cache))
        for endpoints in rigs.values():
            for item in endpoints.values():
                item['age_seconds'] = round(time.time() - item['observed_at'], 1) if 'observed_at' in item else None
                item['stale'] = bool(item.get('error')) or item['age_seconds'] is None or item['age_seconds'] > self.interval * 3
        return {'mode':'DEMO' if self.demo else 'READ_ONLY', 'rigs':rigs, 'ledger':self.ledger.summary()}

def handler(monitor):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Localhost only, with Host validation against DNS rebinding.
            host = self.headers.get('Host', '').split(':')[0]
            if host not in ('localhost', '127.0.0.1'):
                self.send_error(403)
                return
            if self.path == '/api/status':
                body, mime = json.dumps(monitor.snapshot()).encode(), 'application/json'
            elif self.path == '/':
                body, mime = (ROOT / 'dashboard.html').read_bytes(), 'text/html; charset=utf-8'
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_):
            pass
    return Handler

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=str(ROOT / 'config.json'))
    parser.add_argument('--db', default=str(ROOT / 'ledger.sqlite3'))
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--import-ledger', metavar='CSV')
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args()
    os.umask(0o077)
    ledger = Ledger(args.db)
    if args.import_ledger:
        print('Imported:', ledger.import_csv(args.import_ledger))
        return
    config = {'rigs':[{'name':'Esimerkkirigi','url':'http://127.0.0.1:4000'}]} if args.demo else json.loads(Path(args.config).read_text())
    rigs = config['rigs']
    if not 1 <= len(rigs) <= 32 or len({r['name'] for r in rigs}) != len(rigs):
        raise ValueError('Require 1-32 rigs with unique names')
    monitor = Monitor(rigs, ledger, args.demo)
    worker = threading.Thread(target=monitor.run, daemon=True)
    worker.start()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(monitor))
    print(f'MazufaMine {"DEMO" if args.demo else "READ_ONLY"}: http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        monitor.stop.set()
        server.server_close()

if __name__ == '__main__':
    main()
