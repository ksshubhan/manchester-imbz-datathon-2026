"""Stream the test-day payments into the scoring service in time order, like live traffic.

    python backend/replay.py --url http://148.100.108.113:5000 --rate 50

--rate      payments per second (default 50). Lower it for a slower, more watchable demo.
--limit     stop after N payments (default: all)
--file      replay CSV made by export_for_service.py
--reset     clear the service's alerts and totals first (default on)
"""
import argparse
import csv
import json
import os
import time
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument('--url', default='http://localhost:5000')
ap.add_argument('--rate', type=float, default=50)
ap.add_argument('--limit', type=int, default=0)
default_file = ('/home/jovyan/shared/service_data/replay_sample.csv'
                if os.path.isdir('/home/jovyan/shared') else os.path.expanduser('~/shared/service_data/replay_sample.csv'))
ap.add_argument('--file', default=default_file)
ap.add_argument('--no-reset', action='store_true')
args = ap.parse_args()


def post(path, payload=None):
    req = urllib.request.Request(args.url + path, data=json.dumps(payload or {}).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


if not args.no_reset:
    post('/reset')

gap = 1.0 / args.rate if args.rate > 0 else 0
sent = alerts = students = 0
start = time.time()
with open(args.file) as fh:
    for row in csv.DictReader(fh):
        result = post('/score', row)
        sent += 1
        if result['level'] != 'none':
            alerts += 1
            students += result['level'] == 'student'
            tag = 'STUDENT+ANALYST' if result['level'] == 'student' else 'ANALYST'
            truth = 'laundering' if row.get('y') == '1' else 'normal'
            print(f"{row['timestamp']}  {tag:15s} risk={result['risk_score']:.4f}  ({truth})  "
                  f"{row['receiver']}  | {'; '.join(result.get('reasons', []))}")
        if sent % 1000 == 0:
            print(f'... {sent:,} payments sent, {alerts:,} alerts, {students:,} student warnings')
        if args.limit and sent >= args.limit:
            break
        if gap:
            time.sleep(gap)

print(f'\nDone: {sent:,} payments in {time.time() - start:.0f}s | {alerts:,} alerts | {students:,} student warnings')
print('Service totals:', json.load(urllib.request.urlopen(args.url + '/stats', timeout=10)))
