# Initial Pitch

Guys, I think we should go with money mule detection, but aimed at protecting students, not just helping banks catch them.

## 💡 The idea
A mule is the middle link in a money laundering chain. Dirty money lands in someone's account and they're told to send it on fast, usually within hours. Students get recruited into this with "easy money" offers, often without realising it's a crime.

We build a real-time system on LinuxONE that spots the mule pattern the moment suspicious money lands in an account, before it's forwarded on. Then:
1. The student gets a plain-English warning on their phone so they can stop before they've committed a crime
2. The bank's analyst gets an AI-written explanation of why the account was flagged

## 🔄 Usual approach vs ours
❌ **Usual:** the bank detects the mule AFTER the money has already moved, then freezes or reports the account. The student gets punished, sometimes with a criminal record and a banned bank account.

✅ **Ours:** we catch it in the window between the money arriving and the student sending it on, and warn the student FIRST. The student is protected, and the chain gets broken before the money disappears.

## 🏆 Why it's the best option
- Real problem with hard numbers: around a fifth of suspected mule cases in the UK involve under-21s, 65% of mules are under 30, and UK payment fraud hit £1.28bn last year
- It's literally about us. We're the age group being targeted, which makes the pitch personal and believable
- We can use IBM's own anti-money-laundering dataset. Judges are IBM people, so "IBM's data on IBM's platform" is an easy win
- It hits Theme 1 (real-time AI) and lines up with both mandatory labs (multi-model + predictive & generative AI). Final build: XGBoost with template explanations; the planned LLM (Granite) layer wasn't connected in time

## ⚠️ "Won't loads of teams do fraud?"
Probably, but most will build a generic bank-side fraud detector in a notebook. Here's how we make ours impossible to copy:

**1️⃣ Our own data**
We can run our own quick surveys online to get real evidence from students, so we're not just quoting the same stats as everyone else.

**2️⃣ A specific mechanism**
Not just "detect fraud". We decide exactly which signal we catch (e.g. money arriving and leaving within hours, many unknown senders) and exactly what the student sees at that moment.

**3️⃣ A live demo, not a notebook**
Payments stream in on LinuxONE, an account turns red, the student gets the warning, the analyst gets the explanation. Most teams won't have anything running live.

**4️⃣ Our story**
"We're students, we're the ones being recruited, here's what we found." No other team can say that the same way.

## ✅ Next steps
- Agree on this in the next 10 mins
- 1 person: surveys
- 1-2 people: get LinuxONE + the labs running, then load the IBM dataset
- 1 person: demo front end (student warning + analyst view)
- 1 person: own the pitch deck PDF + video script from this afternoon

Thoughts? If we're agreed let's split up and go 🚀

---
**Sources for stats:**
- [Fifth of suspected money mule cases involve under-21s](https://news.stv.tv/world/fifth-of-suspected-money-mule-cases-involve-under-21s)
- [65% of UK money mules are under 30](https://financialit.net/news/cybersecurity/new-research-reveals-65-uk-money-mules-are-under-30)
- [UK payment fraud losses topped £1.28bn in 2025 (UK Finance)](https://www.fintechfutures.com/financial-crime-fraud-prevention/uk-payment-fraud-losses-top-1-28bn-in-2025-new-uk-finance-report-finds)
