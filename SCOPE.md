# Scope: Manchester.Ai_IBM Z Datathon 2026 Project

**Idea:** Real-time money mule early warning on IBM LinuxONE. When suspicious money lands in a student's account, we flag it *before* they forward it on, warn the student first, and give the bank analyst an AI-written explanation.

**Deadline:** Submit by **09:00 Sun 18 Oct** (hard deadline 10:00). Venue closes 17:00 Sat.

## Must-have (MVP)
1. **Data:** IBM AML **HI-Small** loaded on the LinuxONE VM.
2. **Point-in-time features** for every incoming payment, using only data from *before* its timestamp:
   - Payment: amount vs the account's normal, new sender?, payment type
   - Receiving account: account age, number of unrelated senders recently
   - Sender: fan-out (how many new accounts they've paid recently)
3. **Models:** rules baseline + XGBoost + anomaly score, combined (covers the multi-model lab).
4. **Generative AI:** LLM turns the top reasons into (a) a student warning and (b) an analyst explanation (covers the predictive + generative lab).
5. **Live demo:** replay script streams transactions in time order -> scoring service in Docker on LinuxONE -> web page with:
   - Student phone view (warning)
   - Analyst dashboard (accounts turning red + explanation)
6. **Evidence:** screenshots of VM, containers, training and live scoring.

## Should-have (only after MVP works)
- Checkpoint 2: pause the outbound transfer with a confirmation step (can be simulated)
- Graph view of the sender's mule ring
- Survey results slide

## Won't do
See `later.md`.

## Stop rules
- **Model:** train on earlier time, test on a *later* time period (never a random split). Metric: recall at a fixed alert rate (e.g. top 1% of scores). Stop tuning when it clearly beats the rules baseline, or at **21:00**, whichever first.
- **LLM:** if Granite isn't running on the VM by **18:00**, switch to template explanations built from the model's top features.
- **Graph features:** if sender fan-out is too slow, precompute in time windows. Max 1 hour on this.

## Checkpoints
| Time | Goal |
|---|---|
| 13:00 | Labs done, VM + Jupyter running, dataset loaded |
| 15:00 | Features + baseline working |
| 17:00 | Model trained, scoring service running on LinuxONE |
| 21:00 | Front end connected to live scoring, model frozen |
| 23:00 | Feature freeze: fixes only |
| 05:00 | Code freeze, README done |
| 07:00 | Video recorded, pitch deck PDF done |
| **09:00** | **Submit** |

## Roles
- **Data & model:** features, training, evaluation
- **Platform:** VM, Docker, scoring service, LLM, screenshots
- **Front end:** student view + analyst dashboard
- **Pitch:** surveys, deck, video script, open-source list, README

## Risks
- VM memory: start with a sample of HI-Small, scale up only if comfortable
- 200MB Jupyter upload limit: download to the VM via Kaggle API or `scp`
- Stuck >30 mins on setup: ask in #ibm-z-sme-helpdesk

## Submission checklist
- [ ] Title: **Manchester.Ai_IBM Z Datathon 2026 Project**
- [ ] Event code **SSF2026** in description
- [ ] Video <= 3 min showing LinuxONE instance + model
- [ ] GitHub link
- [ ] Pitch deck PDF
- [ ] Links to all open-source libraries used
- [ ] Architecture diagram
