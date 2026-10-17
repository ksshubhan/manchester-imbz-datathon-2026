"""
StudentShield frontend server (Flask), wired to the real model.

The demo plays a REAL account from the IBM AML test days (an account that received several
laundering payments and then sent money on). Every payment is sent to the scoring service
(mule-service, our XGBoost model on LinuxONE) as it "arrives", and the panels show what the
model actually returned: score, alert level, reasons and the explanation.

Only the persona is illustrative: we label the account holder "Student" to tell the story.
The payments, the scores and the reasons are real.

Pages
  /        landing page
  /demo    three-panel story view (one real case, payment by payment)
  /live    full replay of the test days with live stats (served by mule-service, proxied here)

Env
  MODEL_URL  scoring service, default http://mule-service:5000 (same Docker network)
"""

import json
import os
import platform
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from urllib.error import HTTPError

from flask import Flask, Response, jsonify, render_template, request

MODEL_URL = os.environ.get("MODEL_URL", "http://mule-service:5000").rstrip("/")
STEP_SECONDS = 1.6        # one case payment every 1.6 real seconds
BG_SECONDS = 1.1          # one background payment every 1.1 real seconds
MAX_INBOUND = 8           # keep the money-flow picture readable

app = Flask(__name__)
lock = threading.Lock()


# ---------------------------------------------------------------------------
# Talking to the scoring service
# ---------------------------------------------------------------------------
def model(path, payload=None, timeout=10):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(MODEL_URL + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="GET" if payload is None else "POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def short_time(ts):
    return ts[11:19] if len(ts) >= 19 else ts


def day_label(ts):
    """'2022-09-09 14:03:00' -> 'Fri 9 Sep' (the case spans several days, so times need a date)."""
    try:
        d = datetime.strptime(ts[:10], "%Y-%m-%d")
        return f"{d:%a} {d.day} {d:%b}"
    except (ValueError, TypeError):
        return ""


def stamp(ts):
    """'Fri 9 Sep 14:03' for timelines."""
    return f"{day_label(ts)} {ts[11:16]}".strip() if ts else ""


def parse_ts(ts):
    return datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")


def span_text(minutes):
    """Human lead time: '19 h 12 min', '45 min', '2 days 3 h'."""
    minutes = int(minutes)
    d, rem = divmod(minutes, 1440)
    h, m = divmod(rem, 60)
    if d:
        return f"{d} day{'s' if d > 1 else ''} {h} h" if h else f"{d} day{'s' if d > 1 else ''}"
    if h:
        return f"{h} h {m} min" if m else f"{h} h"
    return f"{m} min"


def rarity_text(risk_score):
    """How unusual this score is, against all validation payments. Replaces 'top 0.01%' (a floor, not a fact)."""
    share = 1 - float(risk_score)
    if share <= 0:
        return "No payment in the validation days scored this high"
    n = 1 / share
    n = int(float(f"{n:.2g}")) if n >= 100 else round(n)
    return f"Only about 1 in {n:,} payments scores this high"


# ---------------------------------------------------------------------------
# Story state
# ---------------------------------------------------------------------------
def fresh_state():
    return {
        "t0": time.time(),
        "last_bg": 0.0,
        "bg_rows": [],
        "bg_i": 0,
        "feed": [],
        "tiles": {},                 # receiving account -> latest model probability (background)
        "case": None,                # summary from /cases
        "events": [],                # rows into / out of the case account, time order
        "ev_i": 0,
        "scenario_start": None,
        "inbound": [],               # (row, model result)
        "outbound": None,            # (row, held?)
        "best": None,                # highest-scoring inbound result (drives risk + explanation)
        "explanation": None,
        "explain_source": None,
        "student_response": None,
        "clock": None,
        "error": None,
    }


S = fresh_state()


def add_feed(row, flag=False, kind="transfer"):
    S["feed"].insert(0, {"time": row["timestamp"][11:16], "date": day_label(row["timestamp"]),
                         "from": row["sender"],
                         "to": row["receiver"], "amount": round(float(row["amount_paid"]), 2),
                         "flag": flag, "kind": kind})
    del S["feed"][40:]
    S["clock"] = row["timestamp"]


def load_case():
    """Pick the strongest real fan-in case and its payments."""
    cases = model("/cases?limit=1")
    if not cases:
        raise RuntimeError("no suitable case found in the replay file")
    case = cases[0]
    rows = model("/case/" + case["account"])
    acct = case["account"]
    inbound = [r for r in rows if r["receiver"] == acct][:MAX_INBOUND]
    last_in = inbound[-1]["timestamp"] if inbound else ""
    first_out = next((r for r in rows if r["sender"] == acct and r["timestamp"] >= inbound[0]["timestamp"]), None)
    events = inbound + ([first_out] if first_out else [])
    events.sort(key=lambda r: r["timestamp"])
    S["case"], S["events"] = case, events


def advance():
    real = time.time() - S["t0"]

    # Pick the real case first, so the background traffic can come from the same hours
    if S["case"] is None:
        try:
            load_case()
        except Exception as e:
            S["error"] = f"scoring service unreachable or no case ({type(e).__name__})"
            return
    # Background: real normal payments from around the same time, scored by the model as they arrive
    if not S["bg_rows"]:
        first = S["events"][0]["timestamp"]
        start = first[:11] + f"{max(int(first[11:13]) - 3, 0):02d}" + first[13:]
        try:
            S["bg_rows"] = model(f"/sample?n=300&start={urllib.parse.quote(start)}&end={urllib.parse.quote(S['events'][-1]['timestamp'])}")
        except Exception as e:
            S["error"] = f"scoring service unreachable ({type(e).__name__})"
            return
    while S["last_bg"] + BG_SECONDS < real and S["bg_i"] < len(S["bg_rows"]):
        S["last_bg"] += BG_SECONDS
        row = S["bg_rows"][S["bg_i"]]
        S["bg_i"] += 1
        try:
            res = model("/score", row)
        except Exception:
            continue
        S["tiles"][row["receiver"]] = (res["probability"], res["level"])
        if len(S["tiles"]) > 7:
            S["tiles"].pop(next(iter(S["tiles"])))
        add_feed(row, flag=res["level"] != "none")

    # The real case, one payment at a time
    if S["scenario_start"] is None:
        return
    since = time.time() - S["scenario_start"]
    acct = S["case"]["account"]
    while S["ev_i"] < len(S["events"]) and since >= S["ev_i"] * STEP_SECONDS:
        # catch background traffic up to this payment's time, so the stream stays in time order
        nxt = S["events"][S["ev_i"]]["timestamp"]
        while S["bg_i"] < len(S["bg_rows"]) and S["bg_rows"][S["bg_i"]]["timestamp"] <= nxt:
            S["bg_i"] += 1
        row = S["events"][S["ev_i"]]
        S["ev_i"] += 1
        if row["receiver"] == acct:
            res = model("/score", row)
            S["inbound"].append((row, res))
            add_feed(row, flag=res["level"] != "none", kind="inbound")
            if S["best"] is None or res["probability"] > S["best"]["probability"]:
                S["best"] = res
                S["explanation"] = None          # refresh explanation for the new top alert
        else:
            held = S["best"] is not None and S["best"]["level"] != "none"
            S["outbound"] = (row, held)
            add_feed(row, flag=held, kind="held" if held else "transfer")


def explanation():
    best = S["best"]
    if best is None:
        return None, None
    if S["explanation"] is None:
        text, source = None, "model reasons"
        if best.get("alert_id"):
            try:
                ex = model(f"/explain/{best['alert_id']}", timeout=40)
                text, source = ex["analyst_message"], ex["source"]
            except Exception:
                pass
        if text is None:
            text = ("Flagged because: " + "; ".join(best.get("reasons") or ["combined pattern"]) + "."
                    if best["level"] != "none" else "Below the alert threshold so far. Still watching this account.")
        S["explanation"], S["explain_source"] = text, source
    return S["explanation"], S["explain_source"]


def status_of(level):
    return {"student": "red", "analyst": "amber"}.get(level, "green")


def case_features():
    ins = [r for r, _ in S["inbound"]]
    total_in = sum(float(r["amount_paid"]) for r in ins)
    first = ins[0]["timestamp"] if ins else None
    held = 0
    if first:
        end = S["outbound"][0]["timestamp"] if S["outbound"] else S["clock"]
        held = int((parse_ts(end) - parse_ts(first)).total_seconds() // 60)
    new_senders = len({r["sender"] for r in ins if float(r.get("new_pair", 0)) >= 1 or float(r.get("pair_prior_cnt", 1)) == 0})
    out_amt = float(S["outbound"][0]["amount_paid"]) if S["outbound"] else 0
    return {
        "inbound_count": len(ins),
        "unique_new_senders": new_senders,
        "unique_senders": len({r["sender"] for r in ins}),
        "total_in": round(total_in, 2),
        "minutes_held": held,
        "outbound_ratio": round(out_amt / total_in, 2) if total_in else 0,
        "account_age_hours": round(float(ins[0]["r_age_h"]), 1) if ins else None,
    }


def lead_time():
    """How long before the money left did each warning fire? None until the outbound transfer arrives."""
    if not S["outbound"]:
        return None
    out_ts = S["outbound"][0]["timestamp"]
    first = lambda lv: next((r["timestamp"] for r, res in S["inbound"] if res["level"] in lv), None)
    stu, ana = first({"student"}), first({"student", "analyst"})
    mins = lambda ts: (parse_ts(out_ts) - parse_ts(ts)).total_seconds() / 60 if ts else None
    s_min, a_min = mins(stu), mins(ana)
    if s_min is not None and s_min >= 0:
        text = f"Student warned {span_text(s_min)} before the money moved out"
        if a_min is not None and a_min - s_min >= 1:
            text += f" (analyst alerted {span_text(a_min)} before)"
        kind = "student"
    elif a_min is not None and a_min >= 0:
        text, kind = f"Analyst alerted {span_text(a_min)} before the money moved out", "analyst"
    else:
        text, kind = "No warning before the money moved out", "none"
    return {"text": text, "kind": kind, "student_minutes": s_min, "analyst_minutes": a_min,
            "out_time": stamp(out_ts)}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/demo")
def demo():
    return render_template("demo.html")


@app.route("/live")
def live():
    """The full test-day replay dashboard, served by the scoring service."""
    return proxy("/")


# ---------------------------------------------------------------------------
# Story API
# ---------------------------------------------------------------------------
@app.route("/api/state")
def state():
    with lock:
        try:
            advance()
        except Exception as e:
            S["error"] = f"scoring service error ({type(e).__name__})"
        tiles = [{"id": a, "label": "real account", "risk": p, "status": status_of(lvl)}
                 for a, (p, lvl) in list(S["tiles"].items())[-7:]]

        alert = None
        if S["inbound"]:
            best = S["best"]
            status = status_of(best["level"])
            f = case_features()
            acct = S["case"]["account"]
            tiles.insert(min(4, len(tiles)), {"id": acct, "label": "Student (persona)",
                                              "risk": best["probability"], "status": status})
            timeline = [{"time": stamp(r["timestamp"]),
                         "text": f"{float(r['amount_paid']):,.0f} in from {r['sender']}"
                                 + (" (new sender)" if float(r.get('pair_prior_cnt', 1)) == 0 else "")
                                 + (f" · score {res['probability']:.2f}, {res['level']}" if res["level"] != "none"
                                    else f" · score {res['probability']:.2f}"),
                         "kind": "in"} for r, res in S["inbound"]]
            if S["outbound"]:
                row, held = S["outbound"]
                timeline.append({"time": stamp(row["timestamp"]),
                                 "text": f"{float(row['amount_paid']):,.0f} out to {row['receiver']}"
                                         + (": HELD for review" if held else ""),
                                 "kind": "out"})
            text, source = explanation()
            alert = {
                "account_id": acct, "holder": "Student (persona)",
                "risk": best["probability"], "risk_percentile": best["risk_score"],
                "rarity": rarity_text(best["risk_score"]),
                "lead_time": lead_time(),
                "level": best["level"], "status": status, "features": f,
                "reasons": best.get("reasons", []),
                "senders": [{"id": r["sender"], "amount": round(float(r["amount_paid"]), 2),
                             "laundering": r.get("y") == "1"} for r, _ in S["inbound"]],
                "destination": S["outbound"][0]["receiver"] if S["outbound"] else None,
                "outbound_amount": round(float(S["outbound"][0]["amount_paid"]), 2) if S["outbound"] else None,
                "outbound_held": S["outbound"][1] if S["outbound"] else False,
                "timeline": timeline,
                "explanation": text, "explanation_source": source,
                "student_response": S["student_response"],
                "case_done": S["ev_i"] >= len(S["events"]),
            }

        return jsonify({
            "sim_time": short_time(S["clock"]) if S["clock"] else "--:--:--",
            "sim_date": S["clock"][:10] if S["clock"] else "",
            "sim_day": day_label(S["clock"]) if S["clock"] else "",
            "feed": S["feed"][:18],
            "accounts": tiles,
            "alert": alert,
            "error": S["error"],
            "platform": {"arch": platform.machine(), "host": platform.node()},
        })


@app.route("/api/run-scenario", methods=["POST"])
def run_scenario():
    with lock:
        if S["scenario_start"] is None:
            try:
                if S["case"] is None:
                    load_case()
                S["scenario_start"] = time.time()
                S["error"] = None
            except Exception as e:
                S["error"] = f"could not load a case ({e})"
    return jsonify(ok=S["error"] is None, error=S["error"])


@app.route("/api/reset", methods=["POST"])
def reset():
    global S
    with lock:
        S = fresh_state()
        try:
            model("/reset", {})
        except Exception:
            pass
    return jsonify(ok=True)


@app.route("/api/student-action", methods=["POST"])
def student_action():
    action = (request.json or {}).get("action")
    labels = {
        "help": "Student paused and asked for help",
        "asked": "Student reported: someone asked them to move this money",
        "legit": "Student says the funds are legitimate (escalated for review)",
    }
    with lock:
        S["student_response"] = {"text": labels.get(action, action),
                                 "time": stamp(S["clock"] or "")}
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# Proxy to the scoring service, so /live and its API work through this one public port
# ---------------------------------------------------------------------------
def proxy(path):
    url = MODEL_URL + path + (("?" + request.query_string.decode()) if request.query_string else "")
    body = request.get_data() if request.method == "POST" else None
    req = urllib.request.Request(url, data=body, method=request.method,
                                 headers={"Content-Type": request.headers.get("Content-Type", "application/json")})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return Response(r.read(), status=r.status, content_type=r.headers.get("Content-Type"))
    except HTTPError as e:
        return Response(e.read(), status=e.code, content_type=e.headers.get("Content-Type"))
    except Exception as e:
        return jsonify(error=f"scoring service unreachable ({type(e).__name__})"), 502


for _p in ["/health", "/stats", "/alerts", "/explain/<int:aid>", "/score", "/reset",
           "/demo/start", "/demo/stop", "/demo/status"]:
    app.add_url_rule(_p, "proxy" + _p, lambda aid=None, _p=_p: proxy(request.path), methods=["GET", "POST"])


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False, threaded=True)
