"""Mule early-warning scoring service (runs on IBM LinuxONE).

Scores each incoming payment in milliseconds, decides who gets warned, and explains why.

Endpoints
  GET  /health              service is up + which model is loaded
  POST /score               score one payment (JSON: 24 features + payment details)
  GET  /alerts?limit=50     most recent alerts, newest first (for the dashboard)
  GET  /explain/<id>        LLM-written student warning + analyst note for one alert
  GET  /stats               running totals for the dashboard header
  POST /reset               clear alerts and totals (between demo runs)

Run:  python app.py   (or in Docker, see service/README.md)
Data: DATA_DIR env var, default /data, must contain models/ and thresholds.json
LLM:  optional. Set LLM_URL to an OpenAI-compatible chat endpoint (e.g. a local Granite
      server); otherwise explanations use templates built from the same reasons.
"""
import itertools
import json
import os
import platform
import threading
import time
import urllib.request
from collections import deque

import numpy as np
import xgboost as xgb
from flask import Flask, jsonify, request

DATA_DIR = os.environ.get('DATA_DIR', '/data')
LLM_URL = os.environ.get('LLM_URL', '')
LLM_MODEL = os.environ.get('LLM_MODEL', 'granite')

config = json.load(open(f'{DATA_DIR}/models/config.json'))
FEATURES = config['features']
thresholds = json.load(open(f'{DATA_DIR}/thresholds.json'))
ref = np.load(f'{DATA_DIR}/models/ref_xgb_val.npy')
booster = xgb.Booster()
booster.load_model(f'{DATA_DIR}/models/mule_xgb.json')

app = Flask(__name__)
lock = threading.Lock()
alerts = deque(maxlen=1000)
ids = itertools.count(1)
stats = {'scored': 0, 'analyst_alerts': 0, 'student_warnings': 0,
         'laundering_seen': 0, 'laundering_caught': 0, 'total_ms': 0.0}


# ---------- plain-English reasons ----------
def n(v):
    return int(round(float(v)))


def reason_text(feat, v, p):
    """One plain sentence per feature. Wording describes the fact, not a verdict."""
    fmt = p.get('payment_format_name', 'unknown method')
    texts = {
        'payment_format': (f'sent by bank transfer (ACH), the method behind most laundering in our data'
                           if fmt == 'ACH' else f'sent by {fmt}'),
        'new_pair': 'first ever payment from this sender to this account' if v else None,
        'pair_prior_cnt': ('first ever payment from this sender to this account' if n(v) == 0
                           else f'sender has paid this account {n(v)} times before'),
        'log_amount': f'payment of {float(np.expm1(v)):,.0f}',
        'cross_currency': 'payment was converted between currencies' if v else None,
        'cross_bank': 'sent from a different bank' if v else 'sent within the same bank',
        'payment_currency': 'paid in a currency linked to higher laundering rates',
        'hour': f'sent at {n(v):02d}:00',
        'r_age_h': f'receiving account first seen only {float(v):.0f} hours ago' if v < 48
                   else f'receiving account first seen {float(v) / 24:.0f} days ago',
        'r_in_cnt_all': ('first payment this account has ever received' if n(v) == 0
                         else f'account has received {n(v)} payments in total'),
        'r_in_cnt_24h': ('no other money arrived in the last 24 hours' if n(v) == 0
                         else f'{n(v)} other payments arrived in the last 24 hours'),
        'r_in_cnt_1h': ('account was otherwise quiet in the last hour' if n(v) == 0
                        else f'{n(v)} other payments arrived in the last hour'),
        'r_out_cnt_all': ('account has never sent money out' if n(v) == 0
                          else f'account has sent {n(v)} payments out in total'),
        'r_out_cnt_24h': f'account sent {n(v)} payments out in the last 24 hours',
        'r_distinct_senders': f'account has been paid by {n(v)} different senders',
        'r_new_senders_24h': f'account was paid by {n(v)} new senders in the last 24 hours',
        'amt_vs_r_avg': ('first incoming payment we have seen for this account' if v < 0
                         else f'{float(v):.1f}x this account\'s usual incoming amount'),
        'r_passthrough_24h': f'{float(v):.0%} of money received in the last 24 hours has already been sent on',
        's_age_h': f'sender first seen {float(v):.0f} hours ago',
        's_out_cnt_all': f'sender has made {n(v)} payments in total',
        's_out_cnt_24h': f'sender made {n(v)} payments in the last 24 hours',
        's_in_cnt_24h': f'sender itself received {n(v)} payments in the last 24 hours (money passing through)',
        's_distinct_receivers': f'sender has paid {n(v)} different accounts',
        's_new_receivers_24h': f'sender paid {n(v)} new accounts in the last 24 hours',
    }
    return texts.get(feat)


def top_reasons(x, payment, k=3):
    contrib = booster.predict(xgb.DMatrix(x, feature_names=FEATURES), pred_contribs=True)[0][:-1]
    out = []
    for j in np.argsort(-contrib):
        if contrib[j] <= 0 or len(out) == k:
            break
        text = reason_text(FEATURES[j], x[0, j], payment)
        if text and text not in out:
            out.append(text)
    return out


# ---------- messages ----------
def template_messages(a):
    student = (
        'Check before you send this money on. '
        f'You have just received a payment of {a["amount"]:,.2f}. It matches patterns we see in money-mule scams, '
        'where people are paid to let money pass through their account. '
        'If someone asked you to receive money and send it on, even as a "job", stop: moving it on can be a crime '
        'even if you did not know. Not sure? Do not move the money and call your bank using the number on your card.'
    )
    analyst = (
        f'Risk in the top {max(100 * (1 - a["risk_score"]), 0.01):.2f}% of payments. '
        f'Flagged because: {"; ".join(a["reasons"]) or "combined pattern"}. '
        f'Suggested action: hold outbound transfers from {a["receiver"]} pending review; '
        f'check sender {a["sender"]} for payments to other new accounts.'
    )
    return student, analyst


def llm_messages(a):
    prompt = (
        'You help a bank protect students from becoming money mules. Using ONLY the facts below, write two short texts.\n'
        f'Facts: amount {a["amount"]:,.2f}; reasons the model flagged it: {"; ".join(a["reasons"])}.\n'
        '1) STUDENT: a calm, non-accusatory warning to the account holder (max 60 words). Say it matches mule-scam '
        'patterns, do not send the money on, contact their bank via the number on their card.\n'
        '2) ANALYST: a one-paragraph factual summary for a fraud analyst (max 60 words) with a suggested action.\n'
        'Reply as JSON: {"student": "...", "analyst": "..."}'
    )
    body = json.dumps({'model': LLM_MODEL, 'temperature': 0.2,
                       'messages': [{'role': 'user', 'content': prompt}]}).encode()
    req = urllib.request.Request(LLM_URL, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = json.load(r)['choices'][0]['message']['content']
    parsed = json.loads(text[text.find('{'): text.rfind('}') + 1])
    return parsed['student'], parsed['analyst']


# ---------- routes ----------
@app.after_request
def cors(resp):
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return resp


@app.get('/health')
def health():
    return jsonify(status='ok', machine=platform.machine(), features=len(FEATURES),
                   thresholds={k: thresholds[k] for k in ('analyst_alert', 'student_warning')},
                   llm='on' if LLM_URL else 'templates')


@app.route('/score', methods=['POST', 'OPTIONS'])
def score():
    if request.method == 'OPTIONS':
        return ('', 204)
    p = request.get_json(force=True)
    t0 = time.perf_counter()
    x = np.array([[float(p[f]) for f in FEATURES]], dtype='float32')
    prob = float(booster.predict(xgb.DMatrix(x, feature_names=FEATURES))[0])
    risk = float(np.searchsorted(ref, prob, side='right') / len(ref))   # 0-1: share of validation payments below this one
    level = ('student' if prob >= thresholds['student_warning']
             else 'analyst' if prob >= thresholds['analyst_alert'] else 'none')
    result = {'probability': round(prob, 6), 'risk_score': round(risk, 5), 'level': level}
    if level != 'none':
        result['reasons'] = top_reasons(x, p)
    ms = (time.perf_counter() - t0) * 1000
    result['latency_ms'] = round(ms, 2)

    truth = p.get('y')
    with lock:
        stats['scored'] += 1
        stats['total_ms'] += ms
        if truth is not None and int(truth) == 1:
            stats['laundering_seen'] += 1
            if level != 'none':
                stats['laundering_caught'] += 1
        if level != 'none':
            stats['analyst_alerts'] += 1
            stats['student_warnings'] += level == 'student'
            alert = {'id': next(ids), 'timestamp': p.get('timestamp'), 'sender': p.get('sender'),
                     'receiver': p.get('receiver'), 'amount': float(p.get('amount_paid', 0)),
                     'payment_format': p.get('payment_format_name'), **result}
            if truth is not None:
                alert['is_laundering'] = int(truth)   # demo only: the dataset's ground truth, never shown to the student
            alert['student_message'], alert['analyst_message'] = template_messages(alert)
            alerts.appendleft(alert)
            result['alert_id'] = alert['id']
    return jsonify(result)


@app.get('/alerts')
def get_alerts():
    limit = int(request.args.get('limit', 50))
    with lock:
        return jsonify(list(itertools.islice(alerts, limit)))


@app.get('/explain/<int:alert_id>')
def explain(alert_id):
    with lock:
        alert = next((a for a in alerts if a['id'] == alert_id), None)
    if alert is None:
        return jsonify(error='alert not found'), 404
    source = 'template'
    student, analyst = alert['student_message'], alert['analyst_message']
    if LLM_URL:
        try:
            student, analyst = llm_messages(alert)
            source = f'llm:{LLM_MODEL}'
        except Exception as e:  # LLM down or slow: never break the demo
            source = f'template (llm failed: {type(e).__name__})'
    return jsonify(id=alert_id, student_message=student, analyst_message=analyst, source=source,
                   reasons=alert.get('reasons', []))


@app.get('/stats')
def get_stats():
    with lock:
        s = dict(stats)
    s['avg_latency_ms'] = round(s.pop('total_ms') / max(s['scored'], 1), 2)
    s['catch_rate'] = round(s['laundering_caught'] / max(s['laundering_seen'], 1), 4)
    return jsonify(s)


@app.post('/reset')
def reset():
    with lock:
        alerts.clear()
        for k in stats:
            stats[k] = 0.0 if k == 'total_ms' else 0
    return jsonify(status='reset')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), threaded=True)
