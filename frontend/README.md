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
- **Reset**: restarts the story and clears the live stats
- **Full test-day replay**: opens `/live`

Open-source used: Flask (https://flask.palletsprojects.com), XGBoost (https://xgboost.ai), IBM Plex fonts (https://github.com/IBM/plex).
