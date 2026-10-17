# Scoring service: setup on LinuxONE

The live part of the demo. Payments stream in, each one is scored in milliseconds, risky ones become **analyst alerts** (top 1%), and the riskiest become **student warnings** (top 0.1%), each with plain-English reasons.

```
replay.py ──POST /score──▶  scoring service (Docker, LinuxONE)  ◀──GET /alerts, /stats, /explain──  dashboard
 (test-day payments,          XGBoost + reasons + thresholds                                        (student view +
  in time order)              LLM explanations on demand                                             analyst view)
```

Which terminal each step uses:
- **Jupyter terminal**: Jupyter → Launcher → Terminal (prompt `ibm-user@...`)
- **VM terminal**: Mac Terminal → `ssh -i ~/Documents/arda.pem linux1@148.100.108.113` (prompt `linux1@hulmeai`)

---

## Step 1: Export the model for the service (Jupyter terminal, once)

```
cd ~/shared/manchester-imbz-datathon-2026 && git pull
python service/export_for_service.py
```

This:
- copies the model into `/home/jovyan/shared/service_data/`, the folder shared with the VM. It's also a **backup**: anything only in the Jupyter container is lost if that container is removed.
- sets the alert thresholds **on validation days** and prints how they perform on the test days
- writes `replay_sample.csv`: every test laundering payment plus 30,000 normal ones, in time order

**Send the printed thresholds table to the team chat.** It gives the student-warning precision for the pitch.

## Step 2: Check the folder is visible on the VM (VM terminal)

```
ls ~/shared/service_data
```

You should see `models  replay_sample.csv  thresholds.json`.
If it's empty or missing, find where the Jupyter container's shared folder lives:
```
docker inspect notebook --format '{{json .Mounts}}'
```
and use that host path instead of `~/shared` below.

## Step 3: Build and start the service container (VM terminal)

```
cd ~/shared/manchester-imbz-datathon-2026 && git pull
docker build -t mule-service service/
docker run -d --name mule-service --restart unless-stopped \
  -p 5000:5000 -v ~/shared/service_data:/data mule-service
sudo iptables -I INPUT -p tcp --dport 5000 -j ACCEPT
curl localhost:5000/health
```

`/health` should return `"status":"ok"` and `"machine":"s390x"`. **Screenshot `docker ps` and this output** (containerisation evidence for judges).

If it fails: `docker logs mule-service`.

## Step 4: Replay payments (VM terminal)

```
cd ~/shared/manchester-imbz-datathon-2026
python3 service/replay.py --url http://localhost:5000 --file ~/shared/service_data/replay_sample.csv --rate 20
```

- `--rate` is payments per second. Use 20 for a watchable demo, 0 for as fast as possible.
- Alerts print as they happen. Totals print at the end.
- Press `Ctrl+C` to stop. Each new run clears the previous alerts.

## Step 5: Front end connects to the API

Base URL: `http://148.100.108.113:5000`

| Endpoint | Returns |
|---|---|
| `GET /alerts?limit=50` | Latest alerts, newest first. Poll every 1–2 s |
| `GET /stats` | Payments scored, alerts, student warnings, catch rate, average latency |
| `GET /explain/<id>` | Student warning + analyst note for one alert (LLM if configured, else template) |
| `GET /health` | Status, machine type, thresholds |

Each alert contains: `id, timestamp, sender, receiver, amount, payment_format, risk_score, level ("analyst" or "student"), reasons[], student_message, analyst_message, latency_ms`.
`is_laundering` is the dataset's ground truth, for the **analyst demo view only**. Never show it in the student view.

## Optional: LLM explanations (Granite)

Scoring never waits for the LLM. Explanations are generated only when `/explain/<id>` is called, so the payment path stays fast.

If a Granite model is served on the VM with an OpenAI-compatible endpoint (e.g. llama.cpp `server` or Ollama), restart the container with it:
```
docker rm -f mule-service
docker run -d --name mule-service --restart unless-stopped -p 5000:5000 \
  -v ~/shared/service_data:/data \
  -e LLM_URL=http://172.17.0.1:8080/v1/chat/completions -e LLM_MODEL=granite \
  mule-service
```
(`172.17.0.1` is the VM as seen from inside a Docker container. Change the port to wherever the LLM server listens.)
If the LLM is down or slow, `/explain` falls back to the templates, so the demo never breaks.
