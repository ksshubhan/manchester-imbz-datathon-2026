# Data Findings & Modelling Decisions

What we learned from the data, **what we decided, and why**. Read this before building your part, so everyone understands the reasoning and can explain it to judges. Update it when a decision changes.

> **Current numbers (18 Oct, 01:30):** the live service runs the model retrained on **US-dollar amounts with 25 features** (decision 8). Phase 3 and Phase 4b below show these numbers; the older 24-feature figures are kept underneath each table for the record.

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

ACH (bank-to-bank transfers) is 12% of payments but carries **87% of laundering**. By currency, Saudi Riyal stands out (0.42% laundering, about 4x the average).

**Payments per day:** 1–10 Sep look normal (200k–1.1M payments a day, 300–540 of them laundering). **From 11 Sep, normal activity stops.** Only a handful of payments remain each day and most are laundering (e.g. 18 Sep: 11 payments, 8 laundering).

---

## Decisions and why

### 1. We only use 1–10 September

**What:** we throw away every payment from 11 Sep onwards.

**Why:** this is a synthetic dataset. After 10 Sep the generator appears to stop producing normal payments while laundering chains carry on finishing, so the last week is almost all laundering. That isn't how real banking looks.

**What would go wrong otherwise:** if we tested on those days, nearly every payment would be laundering, so any model would look amazing. An IBM judge who knows this dataset would spot it immediately and stop trusting everything else we say.

---

### 2. We drop self-transfers

**What:** we remove payments where the sender and receiver are the same account (11.6% of the data).

**Why:** a money mule *receives* money from someone else and passes it on. Moving money between your own pots isn't that. Only 11 of 591,212 self-transfers are laundering.

**What would go wrong otherwise:** 591k rows of near-pure noise. The model would waste effort learning "self-transfers are safe" instead of learning what mule activity looks like, and training would be slower on a shared VM.

---

### 3. Every feature only uses the past ("point-in-time")

**What:** when we describe a payment (e.g. "this account received 5 payments in the last 24 hours"), we only count payments that happened **strictly before** it. Even payments in the same minute are excluded.

**Why:** our whole pitch is catching the mule *at the moment the money lands*, before it's forwarded on. At that moment, the bank only knows the past. The features have to match that, or the demo is fake.

**What would go wrong otherwise (data leakage):** say we counted *all* of an account's payments, including future ones. The model would learn "accounts that later send lots of money out are mules". That's true, but at the moment the money lands, the bank can't know it yet. The model would score brilliantly in testing and be useless for real. This is the most common mistake in fraud projects, and judges look for it.

**How we know it's right:** we checked the fast feature code against a slow brute-force calculation on random payments, and they match exactly.

---

### 4. We split train and test by date, never randomly

**What:**

| Split | Days | Purpose |
|---|---|---|
| Warm-up | 1 Sep | Only used as history |
| Train | 2–6 Sep | The model learns from these |
| Validation | 7–8 Sep | We tune settings on these |
| Test | 9–10 Sep | Final score, touched once |

**Why train on earlier days and test on later ones:** in real life, a bank trains on last month and uses the model on next month. Testing on later days copies that.

**What would go wrong with a random split:** payments from the same mule ring would end up in both train and test. The model would recognise the *specific* accounts rather than learning the *pattern*, and the score would be misleadingly high.

**Why day 1 is warm-up only:** on the first day there's no history, so every account looks brand new, and "new account" is one of our mule signals. Day 1 gives the features some history to work from.

**Why validation is separate from test:** if we tuned the model on the test days, we'd slowly fit it to those days and the test score would no longer be honest. We tune on 7–8 Sep and only look at 9–10 Sep at the end.

---

### 5. We measure "recall at a 1% alert rate", not accuracy

**What:** we flag the riskiest 1% of payments and ask: *what share of all the laundering did we catch?* We also report PR-AUC.

**Why not accuracy:** only 1 in 1,000 payments is laundering. A model that says "nothing is ever laundering" is 99.9% accurate and completely useless. Accuracy hides the thing we care about.

**Why 1%:** a bank can't review every payment. Its fraud team has limited time. "If you look at the top 1% we flag, you catch X% of all the laundering" is how a real bank would judge us, and it's a clear line for the pitch.

**Why PR-AUC as well:** it summarises how well the model ranks laundering above normal payments across *every* alert level, not just 1%. It's the standard metric when positives are rare. (Random guessing scores about 0.001 here, the base rate.)

---

### 6. Features in three groups that match the story

**What and why:** each group answers a question a fraud analyst would ask:

- **The payment.** *Is this payment itself unusual?* Amount, format (ACH carries most laundering), currency, whether it crosses banks or currencies, time of day, and **is this the first time these two accounts have ever transacted?** Mule payments typically come from strangers.
- **The receiving account, the possible mule.** *Is this account behaving like a mule?*
  - **Account age:** mules are often new accounts opened for the job.
  - **New senders in the last 24h (fan-in):** a mule suddenly receives from several unknown people.
  - **Money already passed through in 24h:** mules forward money on quickly.
  - **How unusual this amount is for this account:** a student who normally gets £200 suddenly receiving £2,000.
- **The sender, the possible recruiter.** *Is the money coming from a suspicious source?* **New receivers in the last 24h (fan-out):** a recruiter sends money to many mules at once. If the sender is fanning out, every receiver is at risk, even one with a clean history. This is our strongest "early warning" signal, because it can flag a *first-time* mule.

**Why this matters for the pitch:** every feature can be explained in one plain sentence. That makes the AI-written warnings and explanations meaningful ("flagged because the sender paid 12 new accounts today") and lets judges trust the model.

---

### 7. A simple rules baseline comes first

**What:** before any machine learning, we score payments with a hand-written rule like a bank might use: ACH + first-time pair + sender fanning out + receiver collecting from new senders + brand-new account.

**Why:** it gives us a fair yardstick. "Our model catches X% vs Y% for a typical rule" proves the ML adds value. Without a baseline, a number like "60% recall" means nothing to a judge.

**What would go wrong otherwise:** if a simple rule did just as well, building a model would be pointless, and we'd want to know that early rather than in the pitch.

---

### 8. All amounts are converted to US dollars (18 Oct)

**What:** notebook 01 converts every amount to US dollars with one fixed rate per currency (`amount_paid_usd`, `amount_received_usd`). Amount features use the dollar values.

**Why:** the dataset mixes 15 currencies and 63% of payments aren't in dollars. Without converting, "a payment of 10,000" means very different things in yen and in pounds, so the amount features compared unlike things. IBM's generator uses one fixed rate per currency (we checked this on all 5 million rows), so a fixed table is exact, not an approximation.

**Effect:** together with one new feature (`s_passthrough_24h`, below), test recall at the 1% level rose from 59.3% to **69.5%**, and PR-AUC from 0.303 to **0.430**.

---

## Phase 2: features and rules baseline (`notebooks/01_cleaning.ipynb`, `notebooks/02_features.ipynb`)

**Goal:** turn raw transactions into numbers a model can learn from, and set the score the model has to beat.

**Steps**
1. Notebook 01 loads the CSV, removes self-transfers and everything after 10 Sep (decisions 1–2) and converts amounts to US dollars (decision 8). That leaves 4,486,418 payments, 4,514 laundering.
2. Notebook 02 builds **25 point-in-time features** for every incoming payment (decision 3).
3. Split by date: warm-up, train, validation, test (decision 4).
4. Score the **rules baseline** on the test days (decision 7).
5. Save `feat_train.pkl`, `feat_val.pkl`, `feat_test.pkl` and `models/features.json` for Phase 3.

### The 25 features

All of them use **only transactions before the payment**.

**About the payment (8)**

| Feature | Meaning |
|---|---|
| `log_amount` | How big the payment is, on a log scale so huge amounts don't dominate |
| `payment_format` | ACH, cheque, card, cash, Bitcoin, wire or reinvestment |
| `payment_currency` | Which currency it was paid in |
| `cross_currency` | Was it converted between currencies? |
| `cross_bank` | Did it move between two different banks? |
| `hour` | Hour of day it was sent |
| `new_pair` | Is this the **first ever** payment between these two accounts? |
| `pair_prior_cnt` | How many times this sender has paid this receiver before |

**About the receiver, the possible mule (10)**

| Feature | Meaning |
|---|---|
| `r_age_h` | Hours since this account was first seen. New accounts are suspicious |
| `r_in_cnt_all` | Total payments it has ever received |
| `r_in_cnt_24h` | Payments received in the last 24 hours |
| `r_in_cnt_1h` | Payments received in the last hour |
| `r_out_cnt_all` | Total payments it has ever sent |
| `r_out_cnt_24h` | Payments it sent out in the last 24 hours |
| `r_distinct_senders` | How many different people have ever paid it |
| `r_new_senders_24h` | **New** senders in the last 24h (**fan-in**: a mule suddenly gets money from strangers) |
| `amt_vs_r_avg` | This payment compared with the account's usual incoming amount (e.g. 10x normal) |
| `r_passthrough_24h` | Share of the last 24h's incoming money already sent back out (**pass-through**: mules forward money fast) |

**About the sender, the possible recruiter (7)**

| Feature | Meaning |
|---|---|
| `s_age_h` | Hours since the sender was first seen |
| `s_out_cnt_all` | Total payments the sender has ever made |
| `s_out_cnt_24h` | Payments the sender made in the last 24 hours |
| `s_in_cnt_24h` | Payments the sender **received** in the last 24h (money flowing *through* the sender too) |
| `s_distinct_receivers` | How many different accounts the sender has ever paid |
| `s_new_receivers_24h` | **New** accounts paid in the last 24h (**fan-out**: a recruiter spraying money to several mules) |
| `s_passthrough_24h` | Money the sender has sent out in the last 24h (including this payment) compared with what it received (**added 18 Oct**: a sender passing on money it just received may itself be a mule) |

**How it's computed fast:** a helper called `window_stats` sorts payments by (account, time) and uses binary search to count, for example, "payments this account received in the 24h before this one". It does this for all 4.5M payments in about a minute (59 s on LinuxONE) instead of hours. Payments in the same minute are excluded, so nothing leaks.

### The rules baseline

A simple checklist like a bank might hand-write. Each payment gets **one point per red flag** (0–5):

1. Paid by **ACH**, the format carrying 87% of laundering
2. **First ever payment** between these two accounts
3. Sender has paid **3+ new accounts** in the last 24h (fan-out)
4. Receiver has been paid by **2+ new senders** in the last 24h (fan-in)
5. Receiving account is **less than 24 hours old**

Payments with the most points are flagged first, with payment size as a tie-breaker. We measure how much laundering lands in the **top 1%**. That's the number Phase 3 must beat. The model learns its own combination and thresholds from all 25 features instead of 5 fixed rules.

---

## Phase 3 plan: the model, and why

### XGBoost as the main model
**Why:** it's the go-to model for table-shaped data like ours. It's fast to train on a CPU (no GPU on the VM), copes with features on very different scales (counts vs amounts) without extra work, and tells us **which features drove each decision**, which we need for the explanations.

### Isolation Forest as a second, "anomaly" model (tried, then dropped: see Phase 3 results)
**Why we tried it:** XGBoost only learns patterns that appear in the labels. Isolation Forest needs no labels: it flags payments that are simply *unusual*, which can catch new laundering tricks the labels don't cover. Combining the two scores gives a more robust system, and it covers the guidebook's **multi-model lab requirement**.

### Class weighting for the 1-in-1,000 problem
**What:** we tell XGBoost to treat each laundering example as roughly 1,000 times more important (`scale_pos_weight`).

**Why:** otherwise the model learns that predicting "not laundering" is almost always right and barely tries to find the rare cases. We weight rather than generate fake laundering examples, because fake data could teach the model patterns that don't exist.

### Tune on validation, report test once
**Why:** keeps the final number honest. See decision 4.

### Top reasons per alert, turned into plain English
**What:** for each flagged payment, we take the 3 features that pushed the score up most (e.g. "sender paid 12 new accounts today", "account is 2 hours old") and write the student warning and the analyst explanation from them using templates.

**Why:** the explanation only states what the model actually found, so it can't make things up.

**LLM (planned, not in the final build):** the plan was for an LLM (IBM Granite) to write these texts from the same reasons, covering the **predictive + generative lab**. The scoring service has the hook (`LLM_URL`), but no LLM was running by the 18:00 cut-off in SCOPE.md, so the final build uses the templates. An LLM would only reword the same reasons; it would not change any score, alert or result.

---

## Watch-outs (be ready if judges ask)

- **"Isn't it just detecting ACH?"** Format is a strong signal, so we'll check the model still beats the baseline *within ACH payments only*. If it does, it's learning real mule behaviour, not just payment type.
- **"This is synthetic data."** True, and we say so. The results show the approach works. Real-world accuracy would need real bank data. Being upfront earns trust.
- **Stop rule (from SCOPE.md):** stop tuning when the model clearly beats the baseline, or at **21:00**, whichever comes first. A working demo matters more than an extra 2% of recall.

---

## Phase 3 results (`notebooks/03_models.ipynb`)

Trained on **IBM LinuxONE (s390x)**: XGBoost in **19.0 s** (final model; 22.4 s for the first version) (Isolation Forest, when it was tested, in 6 s). Train 2.09M payments (2,203 laundering), validation 945k (1,036), test 845k (954).

### Results log (test days 9–10 Sep, never seen during training or tuning)

Random guessing would score about 1% recall@1% and 0.001 PR-AUC (base rate 0.11%).

| Model | Recall @ 1% alerts | Precision @ 1% | PR-AUC |
|---|---|---|---|
| Rules baseline | 25.7% | 2.9% | 0.024 |
| Isolation Forest only (tested earlier, dropped) | 1.1% | 0.1% | 0.002 |
| **XGBoost (final model, 25 features, USD)** | **69.5%** | **7.9%** | **0.430** |

*Before 18 Oct (24 features, amounts not converted): XGBoost 59.3% / 6.7% / 0.303, rules 25.5% / 2.9% / 0.022. XGBoost + Isolation Forest scored the same as XGBoost alone (best blend weight was 0).*

**Headline:** flagging the riskiest 1% of payments, the model catches **70% of all laundering vs 26% for the rules**: **2.7x more**, with PR-AUC **18x higher**.

### "Isn't it just detecting ACH?" No.

Re-scored on **ACH payments only** (106,123 payments, 832 laundering):

| Model (ACH only) | Recall @ 1% | Precision @ 1% | PR-AUC |
|---|---|---|---|
| Rules baseline | 2.0% | 1.6% | 0.027 |
| **Our model** | **53.6%** | **42.0%** | **0.492** |

*Before 18 Oct: rules 2.3% / 1.8% / 0.026, model 38.5% / 30.2% / 0.345.*

**Why this matters:** within ACH, "is it ACH?" tells you nothing, so the rules collapse to almost random. The model still catches 53.6% at a 42% hit rate, so it has learned **real mule behaviour** (first-time pairs, sender fan-out, account activity), not just payment type.

### What the model relies on (feature importance)

Final model (25 features, USD), share of gain from `notebooks/03_models.ipynb`:

| Feature | Share | Meaning |
|---|---|---|
| `payment_format` | 50.4% | ACH carries most laundering |
| `new_pair` | 11.6% | First ever payment between these two accounts |
| `s_distinct_receivers` | 8.6% | How many accounts the sender pays (fan-out) |
| `pair_prior_cnt` | 6.2% | History between the two accounts |
| `s_out_cnt_24h` / `s_out_cnt_all` | 8.1% | Sender activity |
| `r_in_cnt_1h`, `log_amount`, `payment_currency`, `r_passthrough_24h`, `r_distinct_senders` | ~1.2–1.6% each | Receiver behaviour and payment |

*First version (24 features): payment_format 58.7%.*

Payment format dominates overall, but the ACH-only check above shows the behavioural features do real work.

### Decisions from these results, and why

**1. Isolation Forest is dropped from the score (weight 0).**
*Why:* on its own it scored no better than random (1.1% recall), and every blend with XGBoost made validation worse (77.7% → 63.8% at weight 0.05 → 18.5% at 0.3). The weight was chosen on validation only, so this is a fair decision, not cherry-picking.
*Why it failed, and why that's a useful finding:* mule payments don't look *statistically unusual*. They're often ordinary-sized ACH transfers. Anomaly detection flags the extremes (huge amounts, very busy accounts), which are mostly legitimate. **Mules hide in plain sight, so you need models that learn the specific laundering pattern.** That's a good line for the pitch.
*Effect on the "multi-model" requirement:* XGBoost is the only model in the final build. The plan was **predictive (XGBoost) + generative (LLM explanations)**, but no LLM was connected in time, so explanations come from templates built from the model's reasons. We report both the Isolation Forest result and this honestly rather than hide them.
*Code removed (18 Oct):* the Isolation Forest training and blend were deleted from notebook 03 as dead code. The live service never loaded it (it only uses `mule_xgb.json`), so no numbers change; the result above stays as the record of the experiment.

**2. Validation scored higher than test (77.9% vs 69.5% recall; before 18 Oct, 77.7% vs 59.3%).**
*Why it happens:* patterns drift over time, so a model is always a bit worse on later days. This is expected, and it's exactly why we keep a separate, untouched test set. **We quote the test number (69.5%), never the validation number.** The gap shrank after the dollar conversion, which suggests the model now generalises better to later days.

**3. Alert precision is ~1 in 13 at the 1% level (was ~1 in 15), which shapes the product.**
*What it means:* most alerts at this level are false alarms, as in all real fraud systems.
*Decision:* the **student warning must be gentle and informative** ("this payment matches patterns seen in money-mule scams, check before you send it on"), never accusatory. Analysts see every alert; students could get a warning only at a stricter threshold, where precision is higher. To size this in Phase 4: measure precision at the top 0.1%.

**4. Explanation wording needed a tidy-up (done in the scoring service).**
Top reasons like "0 earlier payments between these two accounts" or "receiving account got 0 payments in the last hour" are correct but read awkwardly. Fix the wording in the scoring service (e.g. "these two accounts have never transacted before").

---

## Phase 4: alert levels (`service/export_for_service.py`)

> **Superseded at 15:25 by Phase 4b below** (cut-offs now chosen with F-beta). Kept for the record.

Thresholds were **set on validation days** (top 1% and top 0.1% of validation scores), then **measured on the untouched test days**:

| Level | Who sees it | Test payments flagged | Laundering caught | Alerts that are real |
|---|---|---|---|---|
| Analyst alert | Bank fraud team | 2.57% | **75.2%** | 3.3% (1 in 30) |
| **Student warning** | Analyst **and** the account holder | **0.13%** (1 in ~770 payments) | **34.3%** | **28.9% (about 1 in 3.5)** |

**Why two levels:** analysts can handle many false alarms, so they get a wide net that catches three quarters of laundering. A student should only be warned when we're fairly sure, so warnings go out for 1 in 770 payments, and about 1 in 3.5 of those really is mule activity. That still catches a third of all laundering **before the money is sent on**.

**Why the analyst level flags 2.57% instead of 1%:** the cut-off was fixed on validation days, and scores on the test days run a little higher (the same drift seen in Phase 3). We keep the validation-set threshold rather than re-tune on test, which would be cheating. In a real bank the threshold would be recalibrated regularly.

**Pitch line:** *"We warn about 1 in 770 payments, and nearly 1 in 3 of those warnings is a real mule payment, caught before the money moves on."*

---

## Phase 4b: alert levels chosen with F-beta (decision closed 17 Oct, 16:00)

**What changed:** instead of picking round numbers (top 1%, top 0.1%), each cut-off is now the one that maximises an **F-beta score on the validation days**, checking every possible cut-off. Then it is measured once on the untouched test days.

**Why F-beta, and why these betas:** F-beta balances recall and precision, with recall counted beta² times as much as precision. We have two levels because the product has two actions, and each action has a different cost of being wrong:
- **Analyst alert: F2** (recall-weighted). Missing a mule is worse than an analyst checking an extra payment. Guard-rail: never more than 5% of payments.
- **Student warning: F0.5** (precision-weighted). Scaring an innocent student is worse than missing a case, because the analyst level still sees it.
- 2 and 0.5 are the standard values. A cost-based beta would need real bank cost figures we don't have, so a precise-looking beta would just be a guess.

**Results on the test days (9-10 Sep, about 845k payments, 0.1% laundering), current model (25 features, USD):**

| Level | Test payments flagged | Alerts per day | False alarms per day | Laundering caught | Alerts that are real |
|---|---|---|---|---|---|
| **Analyst alert (F2)** | 0.10% | ~436 | ~220 | **45.2%** | **49.5% (1 in 2)** |
| **Student warning (F0.5)** | 0.06% | ~259 | ~78 | **37.8%** | **69.7% (7 in 10)** |
| for comparison: top 1% of validation | 2.48% | ~10,500 | | 74.7% | 3.4% (1 in 30) |
| for comparison: top 0.1% of validation | 0.09% | ~360 | | 43.1% | 56.8% |

*Before 18 Oct (24-feature model): analyst 0.31% flagged, ~1,300 alerts a day (~1,090 false), 45.9% caught, 16.8% real; student 0.03%, ~125 a day (~37 false), 18.6% caught, 70.8% real.*

**What this means:**
- F-beta made both levels **stricter** than the old top-1% level: we catch less laundering in total (75% → 45% at analyst level), but alerts are far more likely to be real and the queue is about 24 times smaller.
- With the dollar conversion, analyst alerts became **3 times more precise** (1 in 6 → 1 in 2) with the same recall, and false alarms fell from ~1,090 to ~220 a day.
- Student warnings now catch **twice as much laundering** (18.6% → 37.8%) at the same precision. The cost: ~78 wrong warnings a day instead of ~37.
- For students this fits the pitch: when we interrupt a student, **7 times out of 10 it really is mule activity**.
- The cut-offs are **stable** between validation and test (analyst 0.13% → 0.10% flagged, student 0.07% → 0.06%), unlike the old top-1% level (1% → 2.48%).
- The trade-off is real and the bank controls it. The chart `~/shared/threshold_sweep.png` shows recall and precision for every possible cut-off, so a bank with more analysts can choose a looser one.

**Pitch lines:**
- *"7 in 10 of our student warnings are real mule payments, and each one arrives before the money moves on."*
- *"Half of our analyst alerts are real, against about 1 in 30 if a bank simply reviewed its riskiest 1%."*
- *"Each cut-off is chosen by a standard method, weighted for who bears the cost of a mistake."*
- If asked why we don't catch more: *"We can. Here is the whole trade-off curve. The bank chooses the point that matches its capacity."*
