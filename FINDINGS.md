# Data Findings & Modelling Decisions

Living record of what we learned from the data and **why** the model is built the way it is. Update it when a decision changes.

---

## Phase 1: what the data looks like

Dataset: **IBM Transactions for Anti-Money Laundering, HI-Small** (`HI-Small_Trans.csv`, 476 MB). Loaded on **IBM LinuxONE (s390x)** in ~20 s, 1.42 GB in memory.

| Fact | Value |
|---|---|
| Payments | **5,078,345** |
| Accounts | **515,088** |
| Laundering payments | **5,177 (0.10%)**, about 1 in 1,000 |
| Accounts that received laundered money | **3,984**, our mule candidates |
| Date range | 1 Sep 2022 to 18 Sep 2022 |
| Self-transfers (same sender and receiver) | 591,212 (11.6%), only 11 laundering |

**Laundering by payment format**

| Format | Payments | Laundering | Rate |
|---|---|---|---|
| ACH | 600,797 | **4,483** | 0.75% |
| Cheque | 1,864,331 | 324 | 0.02% |
| Credit Card | 1,323,324 | 206 | 0.02% |
| Cash | 490,891 | 108 | 0.02% |
| Bitcoin | 146,091 | 56 | 0.04% |
| Reinvestment | 481,056 | 0 | 0% |
| Wire | 171,855 | 0 | 0% |

ACH is 12% of payments but carries **87% of laundering**. By currency, Saudi Riyal stands out (0.42% laundering, about 4x the average).

**Payments per day**

Days 1–10 have normal volume (200k–1.1M payments a day, with 300–540 laundering). **From 11 Sep, normal activity stops.** Only a few hundred payments remain, and most of them are laundering (e.g. 18 Sep: 11 payments, 8 laundering).

---

## Decisions and why

### 1. Drop everything from 11 Sep onwards
The tail is a quirk of how the synthetic data was generated, not real behaviour. Testing on it would inflate results (most remaining payments are laundering), and an IBM judge could spot that straight away. **We use 1–10 Sep only.**

### 2. Drop self-transfers
Money moving within one account is not a mule receiving funds, and only 11 of 591k are laundering. They would add noise without adding signal.

### 3. Every feature is "point-in-time"
Each payment's features use only transactions from **strictly before** its timestamp (same-minute payments are excluded too). This mirrors what a bank actually knows the moment money lands. It's the core of the pitch: *catch it in the window between money arriving and being sent on.* Checked against a brute-force calculation.

### 4. Split by time, never randomly
| Split | Days | Purpose |
|---|---|---|
| Warm-up | 1 Sep | History only. Every account looks new on day 1 |
| Train | 2–6 Sep | Fit models |
| Validation | 7–8 Sep | Tune and choose thresholds |
| Test | 9–10 Sep | Final, untouched score |

A random split would let the model learn from the "future" and overstate performance.

### 5. Metric: recall at a 1% alert rate (plus PR-AUC)
With 0.10% positives, **accuracy is useless**: flagging nothing scores 99.9%. A bank can only review a small share of payments, so we ask: *if we flag the riskiest 1%, what share of all laundering do we catch?* PR-AUC is reported alongside because it suits very rare positives.

### 6. Features: three groups, matching the story
- **The payment:** amount, format, currency, cross-bank, cross-currency, hour, *first time this pair has transacted?*
- **The receiving account (possible mule):** account age, money in over 1h, 24h and all-time, **new senders in the last 24h (fan-in)**, money already passed through in the last 24h, how unusual this amount is for this account
- **The sender (possible recruiter):** **new receivers in the last 24h (fan-out)**, activity volume, whether money is also flowing through the sender

### 7. Rules baseline first
A hand-written bank-style rule (ACH + new pair + fan-out + fan-in + new account). **The ML model must clearly beat this** on the test days, or it isn't adding value.

---

## Phase 3 plan: the model (and why)

| Choice | Reason |
|---|---|
| **XGBoost** (main model) | Best-in-class on tabular data, fast to train on CPU, gives feature importances we can explain to judges |
| **Isolation Forest** (anomaly score) | Unsupervised, so it can flag unusual patterns the labels miss. Combined with XGBoost this covers the **multi-model** lab requirement |
| **Class weighting** (`scale_pos_weight`) | Compensates for 1-in-1,000 positives without inventing fake data |
| **Tune on validation, report on test once** | Keeps the test score honest |
| **Top reasons per alert** | Feed the strongest features behind each flag to the LLM, which writes the student warning and the analyst explanation (the **predictive + generative** lab requirement) |

### Watch-outs
- **ACH dependence.** The model will lean heavily on payment format. We'll check it still adds value beyond "is it ACH?" by comparing against the baseline and looking at performance within ACH payments only.
- **Synthetic data.** Results show the approach works. They don't prove real-world accuracy. Say this honestly in the pitch.
- **Stop rule (from SCOPE.md):** stop tuning when the model clearly beats the baseline, or at **21:00**, whichever comes first.

---

## Results log
| Model | Test recall@1% | Test precision@1% | Test PR-AUC |
|---|---|---|---|
| Rules baseline | _to fill_ | _to fill_ | _to fill_ |
| XGBoost | _to fill_ | _to fill_ | _to fill_ |
| XGBoost + Isolation Forest | _to fill_ | _to fill_ | _to fill_ |
