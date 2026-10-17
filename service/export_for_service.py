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

# 2. Thresholds, set on VALIDATION scores only (never on test)
ref = np.load(f'{SRC}/models/ref_xgb_val.npy')            # sorted validation probabilities
thresholds = {
    'analyst_alert': float(np.quantile(ref, 0.99)),       # top 1%  -> analyst queue
    'student_warning': float(np.quantile(ref, 0.999)),    # top 0.1% -> student also warned
}

# 3. Check how those thresholds perform on the untouched TEST days
data = pd.read_pickle(f'{SRC}/features.pkl')
test = data[data['split'] == 'test'].copy()
booster = xgb.Booster()
booster.load_model(f'{SRC}/models/mule_xgb.json')
test['prob'] = booster.predict(xgb.DMatrix(test[FEATURES]))
y = test['y'].values
rows = []
for label, thr in [('top 1% (analyst alert)', thresholds['analyst_alert']),
                   ('top 0.1% (student warning)', thresholds['student_warning'])]:
    flagged = test['prob'].values >= thr
    rows.append({
        'level': label,
        'payments flagged': int(flagged.sum()),
        'share of test payments': f'{flagged.mean():.2%}',
        'laundering caught (recall)': f'{y[flagged].sum() / y.sum():.1%}',
        'alerts that are real (precision)': f'{y[flagged].mean():.1%}' if flagged.any() else 'n/a',
    })
report = pd.DataFrame(rows)
print('\nThresholds chosen on validation, measured on test (9-10 Sep):')
print(report.to_string(index=False))
json.dump({**thresholds, 'test_report': rows}, open(f'{OUT}/thresholds.json', 'w'), indent=2)

# 4. Demo replay file: every test laundering payment + a random sample of normal ones, in time order.
#    Replaying all 845k would take hours; this keeps the real mix of alerts at demo speed.
normal = test[test['y'] == 0].sample(n=min(30_000, int((test['y'] == 0).sum())), random_state=7)
replay = pd.concat([test[test['y'] == 1], normal]).sort_values('timestamp', kind='stable')
cols = ['timestamp', 'sender', 'receiver', 'amount_paid', 'payment_format_name', 'y'] + FEATURES
replay[cols].to_csv(f'{OUT}/replay_sample.csv', index=False)
print(f'\nReplay file: {len(replay):,} payments ({int(replay["y"].sum()):,} laundering) -> {OUT}/replay_sample.csv')
print(f'Everything the service needs is in {OUT}')
