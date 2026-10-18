"""Run ONCE in the Jupyter terminal after notebook 03.

Copies the trained model somewhere the scoring service (and the VM host) can see it,
builds a demo-sized replay file from the test days, and sets the alert thresholds.

    python service/export_for_service.py

Why: files under ~/shared inside the Jupyter container live only in that container.
/home/jovyan/shared is the folder shared with the VM host (/home/linux1/shared), so a
separate Docker container can mount it. It's also a backup if the Jupyter container restarts.
"""
import json
import os
import shutil
import sys

import numpy as np
import pandas as pd
import xgboost as xgb

SRC = os.path.expanduser('~/shared')
OUT = sys.argv[1] if len(sys.argv) > 1 else (
    '/home/jovyan/shared/service_data' if os.path.isdir('/home/jovyan/shared') else f'{SRC}/service_data')
os.makedirs(f'{OUT}/models', exist_ok=True)

# 1. Copy the trained model files
for name in ['mule_xgb.json', 'config.json', 'ref_xgb_val.npy']:
    shutil.copy(f'{SRC}/models/{name}', f'{OUT}/models/{name}')
config = json.load(open(f'{SRC}/models/config.json'))
FEATURES = config['features']

# 2. Thresholds, chosen on VALIDATION only (never on test), with the F-beta score.
#    F-beta weights recall beta^2 times as much as precision. Each level gets the beta that matches
#    who pays for a mistake (see FINDINGS.md, "Alert levels"):
#      analyst alert   -> F2   (missing a mule is worse than an extra review)
#      student warning -> F0.5 (scaring an innocent student is worse; the analyst level still sees it)
# Validation and test days as saved by notebook 02 (feat_val.pkl, feat_test.pkl)
val = pd.read_pickle(f'{SRC}/feat_val.pkl')
test = pd.read_pickle(f'{SRC}/feat_test.pkl')
booster = xgb.Booster()
booster.load_model(f'{SRC}/models/mule_xgb.json')
p_val = booster.predict(xgb.DMatrix(val[FEATURES]))
y_val = val['y'].values
test['prob'] = booster.predict(xgb.DMatrix(test[FEATURES]))
y = test['y'].values
p_test = test['prob'].values


def best_fbeta_threshold(p, yy, beta):
    """Cut-off that maximises F-beta, checking every possible cut-off (not just round numbers)."""
    order = np.argsort(-p)
    ps, ys = p[order], yy[order]
    tp = np.cumsum(ys)
    k = np.arange(1, len(ps) + 1)
    prec, rec = tp / k, tp / ys.sum()
    b2 = beta ** 2
    f = (1 + b2) * prec * rec / np.maximum(b2 * prec + rec, 1e-12)
    valid = np.r_[ps[:-1] != ps[1:], True]       # only cut between different scores
    f = np.where(valid, f, -1)
    i = int(np.argmax(f))
    return float(ps[i]), float(f[i])


thr_a, f_a = best_fbeta_threshold(p_val, y_val, 2.0)
thr_s, f_s = best_fbeta_threshold(p_val, y_val, 0.5)
# Capacity guard-rail: never send analysts more than 5% of payments, whatever F2 says.
MAX_ANALYST_SHARE = 0.05
cap = float(np.quantile(p_val, 1 - MAX_ANALYST_SHARE))
capped = thr_a < cap
thr_a = max(thr_a, cap)
thr_s = max(thr_s, thr_a)                        # a student warning is always also an analyst alert
print(f'F2 best on validation = {f_a:.3f}' + ('  (capped at 5% of payments)' if capped else ''))
print(f'F0.5 best on validation = {f_s:.3f}')
thresholds = {'analyst_alert': thr_a, 'student_warning': thr_s,
              'method': 'F-beta on validation days: analyst F2 (max 5% of payments), student F0.5'}


def measure(p, yy, thr):
    f = p >= thr
    tp = int(yy[f].sum())
    return f, tp


# 3. Report on the untouched TEST days, next to the old fixed "top 1% / top 0.1%" levels for comparison
days = test['timestamp'].dt.normalize().nunique()
rows = []
for label, thr in [('analyst alert (F2)', thr_a), ('student warning (F0.5)', thr_s),
                   ('old: top 1% of validation', float(np.quantile(p_val, 0.99))),
                   ('old: top 0.1% of validation', float(np.quantile(p_val, 0.999)))]:
    f, tp = measure(p_test, y, thr)
    vf = (p_val >= thr).mean()
    rows.append({
        'level': label,
        'share of validation flagged': f'{vf:.2%}',
        'share of test flagged': f'{f.mean():.2%}',
        'alerts per day': int(f.sum() // days),
        'laundering caught (recall)': f'{tp / y.sum():.1%}',
        'alerts that are real (precision)': f'{tp / max(f.sum(), 1):.1%}',
        'one real case in every': f'{f.sum() / max(tp, 1):.0f} alerts',
    })
report = pd.DataFrame(rows)
print('\nCut-offs chosen on validation (F-beta), measured on test (9-10 Sep):')
print(report.to_string(index=False))
json.dump({**thresholds, 'test_report': rows}, open(f'{OUT}/thresholds.json', 'w'), indent=2)

# Trade-off curve for the deck: every possible cut-off, recall and precision on test
sweep = []
for rate in np.logspace(-3.5, -0.5, 80):
    thr = float(np.quantile(p_val, 1 - rate))
    f, tp = measure(p_test, y, thr)
    sweep.append({'validation_flag_rate': rate, 'test_flag_rate': f.mean(),
                  'recall': tp / y.sum(), 'precision': tp / max(f.sum(), 1)})
sweep = pd.DataFrame(sweep)
sweep.to_csv(f'{SRC}/threshold_sweep.csv', index=False)
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(sweep.test_flag_rate * 100, sweep.recall * 100, label='laundering caught (recall)', lw=2)
    ax.plot(sweep.test_flag_rate * 100, sweep.precision * 100, label='alerts that are real (precision)', lw=2)
    for thr, name in [(thr_a, 'analyst (F2)'), (thr_s, 'student (F0.5)')]:
        x = (p_test >= thr).mean() * 100
        ax.axvline(x, ls=':', c='grey')
        ax.text(x, 98, f' {name}', rotation=90, va='top', fontsize=9, color='grey')
    ax.set_xscale('log')
    ax.set_xlabel('% of payments flagged (log scale)')
    ax.set_ylabel('%')
    ax.set_ylim(0, 100)
    ax.set_title('Flag more, catch more, but more false alarms (unseen test days)')
    ax.legend(loc='center left')
    ax.grid(alpha=.3)
    fig.tight_layout()
    fig.savefig(f'{SRC}/threshold_sweep.png', dpi=160)
    print(f'Chart: {SRC}/threshold_sweep.png')
except Exception as e:
    print('Chart skipped:', e)

# 4. Demo replay file: every test laundering payment + a random sample of normal ones, in time order.
#    Replaying all 845k would take hours; this keeps the real mix of alerts at demo speed.
normal = test[test['y'] == 0].sample(n=min(30_000, int((test['y'] == 0).sum())), random_state=7)
replay = pd.concat([test[test['y'] == 1], normal]).sort_values('timestamp', kind='stable')
# Amounts are in US dollars (converted in notebook 01). The service and front end read the column as amount_paid.
replay['amount_paid'] = replay['amount_paid_usd']
cols = ['timestamp', 'sender', 'receiver', 'amount_paid', 'payment_format_name', 'y'] + FEATURES
replay[cols].to_csv(f'{OUT}/replay_sample.csv', index=False)
print(f'\nReplay file: {len(replay):,} payments ({int(replay["y"].sum()):,} laundering) -> {OUT}/replay_sample.csv')
print(f'Everything the service needs is in {OUT}')
