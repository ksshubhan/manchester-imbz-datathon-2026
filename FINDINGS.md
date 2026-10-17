# Data Findings & Modelling Decisions

What we learned from the data, **what we decided, and why**. Read this before building your part, so everyone understands the reasoning and can explain it to judges. Update it when a decision changes.

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

## Phase 3 plan: the model, and why

### XGBoost as the main model
**Why:** it's the go-to model for table-shaped data like ours. It's fast to train on a CPU (no GPU on the VM), copes with features on very different scales (counts vs amounts) without extra work, and tells us **which features drove each decision**, which we need for the explanations.

### Isolation Forest as a second, "anomaly" model
**Why:** XGBoost only learns patterns that appear in the labels. Isolation Forest needs no labels: it flags payments that are simply *unusual*, which can catch new laundering tricks the labels don't cover. Combining the two scores gives a more robust system, and it covers the guidebook's **multi-model lab requirement**.

### Class weighting for the 1-in-1,000 problem
**What:** we tell XGBoost to treat each laundering example as roughly 1,000 times more important (`scale_pos_weight`).

**Why:** otherwise the model learns that predicting "not laundering" is almost always right and barely tries to find the rare cases. We weight rather than generate fake laundering examples, because fake data could teach the model patterns that don't exist.

### Tune on validation, report test once
**Why:** keeps the final number honest. See decision 4.

### Top reasons per alert, fed to the LLM
**What:** for each flagged payment, we take the 3 features that pushed the score up most (e.g. "sender paid 12 new accounts today", "account is 2 hours old") and give them to the LLM. It writes the student warning and the analyst explanation from them.

**Why:** the LLM only explains what the model actually found, so it can't make things up. It also covers the **predictive + generative lab requirement**.

---

## Watch-outs (be ready if judges ask)

- **"Isn't it just detecting ACH?"** Format is a strong signal, so we'll check the model still beats the baseline *within ACH payments only*. If it does, it's learning real mule behaviour, not just payment type.
- **"This is synthetic data."** True, and we say so. The results show the approach works. Real-world accuracy would need real bank data. Being upfront earns trust.
- **Stop rule (from SCOPE.md):** stop tuning when the model clearly beats the baseline, or at **21:00**, whichever comes first. A working demo matters more than an extra 2% of recall.

---

## Results log
| Model | Test recall@1% | Test precision@1% | Test PR-AUC |
|---|---|---|---|
| Rules baseline | _to fill_ | _to fill_ | _to fill_ |
| XGBoost | _to fill_ | _to fill_ | _to fill_ |
| XGBoost + Isolation Forest | _to fill_ | _to fill_ | _to fill_ |
