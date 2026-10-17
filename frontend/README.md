# StudentShield front end

Design by the front-end team; wired to the real model by the data team.

Pages
- `/` landing page (pitch, problem stats, how it works, impact)
- `/demo` three-panel story view: payment stream, the student's phone, and the bank analyst console
- `/live` full replay of the two unseen test days with live stats (served by `mule-service`, proxied here)

## What is real and what is illustrative

- **Real:** every payment shown on `/demo` and `/live` comes from the IBM AML test days (9 and 10 Sep), the
  days the model never saw in training. Every score, alert level, reason and explanation comes from our
  XGBoost model running in `mule-service` on LinuxONE.
- **Illustrative:** the "Student (persona)" label. The dataset has no ages, so the persona tells the story.
- `/demo` plays the strongest real **fan-in then send-on** account in the test days: an account that
  received several laundering payments and then sent money on. It is chosen automatically by
  `mule-service /cases` and ranked by how many of its incoming payments reached the student level.
- Amounts have no £ sign because the dataset mixes currencies.

## The two demos

| | `/demo` (story view) | `/live` (full test-day replay) |
|---|---|---|
| Job | Show the experience: one real mule case, step by step | Show it works at scale on unseen data |
| Payments | One real fan-in account + background traffic from the same hours, slowed down | All replayed test-day payments in order, 5-100 per second |
| Takeaway | Student warned ~19 h before the money moved; analyst sees why | Alerts, catch rate, false alarms, ~1 ms per payment on LinuxONE |
| Phone | That one account | The most recently warned account |

## Phone rules (same on both pages)

Decided 17 Oct, 16:43. Both phones follow these rules; change them here first, then in both pages.

1. **Below the analyst cut-off**: phone normal. Nothing is shown to the student.
2. **Analyst level only**: phone stays normal; the analyst reviews. About 5 in 6 of these are innocent
   (16.8% precision, ~1,090 false alarms a day), too many to contact students.
3. **Student level**: warning screen, "Has someone asked you to move this money?", with three answers:
   *Pause, I need help* / *Someone asked me to move it* / *This is legitimate*. The question is about all the
   money in the account (the recruiter, not each sender), so one answer covers every payment.
4. **After an answer**: any new **flagged** payment (analyst or student level) into that account asks
   "Does your answer still stand?". Unflagged payments don't re-ask.
5. **Holding transfers out**: only once the account has reached the student level (~7 in 10 laundering).
   The student cannot refuse incoming money; the bank can hold money going out.
6. **Which account (replay only)**: the phone follows the most recently warned account; answers are kept per account.
7. **Analyst view** always shows every analyst- and student-level alert. The phone never shows scores, reasons
   or the dataset's answer key.
8. **When asking stops**: as soon as the student says *Someone asked me to move it*, or after 3 answers
   (first warning + 2 re-asks). The phone then shows "A specialist is handling this" and lists later money
   without asking. The analyst sees the final state: on `/demo` in the timeline and the answer list, on `/live`
   under the Level badge and in the alert panel ("Student answers").

The buttons record the student's answer for the analyst. The hold itself comes from rule 5 (the model's level),
not from the button. On `/live` answers are kept in the browser tab only and reset on reload or Start.

## Run it on the LinuxONE VM

Both containers sit on one Docker network. Only StudentShield is published, on port 5000.
Run these in the **VM terminal** (Mac Terminal, `linux1@hulmeai`), from the repo folder:

```bash
cd ~/shared/manchester-imbz-datathon-2026
git pull
docker network create mule-net 2>/dev/null || true

# 1. the model (no public port needed any more)
docker build -t mule-service service/
docker rm -f mule-service
docker run -d --name mule-service --network mule-net --restart unless-stopped \
  -v ~/shared/service_data:/data mule-service

# 2. the front end, on the public port
docker build -t studentshield frontend/
docker rm -f studentshield
docker run -d --name studentshield --network mule-net --restart unless-stopped \
  -p 5000:5000 -e MODEL_URL=http://mule-service:5000 studentshield
```

Open `http://148.100.108.113:5000` in a browser. The badge shows **s390x** on LinuxONE.

## Run it on a laptop (design iteration)

Needs the scoring service running somewhere (for example `python service/app.py` with `DATA_DIR` set).

```bash
pip install flask
MODEL_URL=http://localhost:5001 python app.py
```

## Controls (`/demo`)
- **Play a real case**: streams the case account's payments one by one through the model
- **Reset**: restarts the story and clears the live stats (background payments only; analyst-level flags among them don't reach the phone, rule 2)
- **Full test-day replay**: opens `/live`

Open-source used: Flask (https://flask.palletsprojects.com), XGBoost (https://xgboost.ai), IBM Plex fonts (https://github.com/IBM/plex).
