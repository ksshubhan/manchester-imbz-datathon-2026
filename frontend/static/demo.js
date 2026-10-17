// StudentShield frontend: polls the Flask API and renders the three panels.

const POLL_MS = 800;
const $ = (id) => document.getElementById(id);

let lastFeedKey = null;
let lastAlertJson = null;
let phoneMode = null;   // "idle" | "notif" | "warn" | "done"
let latest = null;

// Amounts are in each payment's own currency (the IBM dataset mixes currencies), so no £ sign.
const gbp = (n) => Number(n).toLocaleString("en-GB", { maximumFractionDigits: 0 });
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const res = await fetch(path, opts);
  return res.json();
}

// ---------------- left panel ----------------
function renderAccounts(accounts) {
  $("accounts").innerHTML = accounts.map((a) => `
    <div class="acct ${a.status}">
      <div class="id">${esc(a.id)}</div>
      <div class="lbl">${esc(a.label)} · ${Math.round(a.risk * 100)}%</div>
    </div>`).join("");
}

function feedRow(p) {
  const cls = p.kind === "held" ? "held" : p.flag ? "flag" : "";
  const arrow = "→";
  return `<li class="${cls}">
    <span class="t">${esc(p.time)}</span>
    <span>${esc(p.from)} ${arrow} ${esc(p.to)}</span>
    <span class="amt">${p.kind === "held" ? "HELD " : ""}${gbp(p.amount)}</span></li>`;
}

function renderFeed(feed) {
  if (!feed.length) { $("feed").innerHTML = ""; lastFeedKey = null; return; }
  const key = (p) => p.time + p.from + p.to + p.amount;
  if (lastFeedKey === null) {
    $("feed").innerHTML = feed.map(feedRow).join("");
  } else {
    const fresh = [];
    for (const p of feed) { if (key(p) === lastFeedKey) break; fresh.push(p); }
    if (fresh.length === feed.length) {
      $("feed").innerHTML = feed.map(feedRow).join("");
    } else if (fresh.length) {
      $("feed").insertAdjacentHTML("afterbegin", fresh.map(feedRow).join(""));
      const ul = $("feed");
      while (ul.children.length > 18) ul.lastElementChild.remove();
    }
  }
  lastFeedKey = key(feed[0]);
}

// ---------------- middle panel: phone ----------------
function renderPhone(alert, simTime, simDate) {
  let mode = "idle";
  if (alert && alert.student_response) mode = "done";
  else if (alert && alert.status === "red") mode = "warn";
  else if (alert && alert.status === "amber") mode = "notif";

  const hhmm = simTime.slice(0, 5);
  if (mode === phoneMode && mode === "idle") {
    const t = document.querySelector(".big-time");
    if (t) t.textContent = hhmm;
    return;
  }
  if (mode === phoneMode) {
    if (mode === "warn") updateWarnFacts(alert);
    return;
  }
  phoneMode = mode;

  const screen = $("phoneScreen");
  if (mode === "idle" || mode === "notif") {
    screen.innerHTML = `
      <div class="lock">
        <div class="big-time">${hhmm}</div>
        <div class="date">${simDate ? new Date(simDate + "T12:00:00").toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" }) : ""}</div>
      </div>
      ${mode === "notif" ? `
      <div class="notif">
        <div class="app"><span>🏦 Your Bank</span><span>now</span></div>
        <b>Unusual payments received</b>
        <p>You've received money that matches an unusual pattern. Tap to review before moving it.</p>
      </div>` : ""}`;
  } else if (mode === "warn") {
    const f = alert.features;
    screen.innerHTML = `
      <div class="warn">
        <div class="shield">🛡️</div>
        <h3>Has someone asked you to move this money?</h3>
        <p><span id="wTotal">${gbp(f.total_in)}</span> arrived from <b><span id="wSenders">${f.unique_senders}</span> different ${f.unique_senders === 1 ? "person" : "people"}</b> in a short time.
        If someone asked you to send it on, <b>stop</b>. You could be being used as a money mule,
        which is a crime even if you didn't know.</p>
        <div class="facts">
          <div><span>Received</span><b id="wTotal2">${gbp(f.total_in)}</b></div>
          <div><span>Senders</span><b id="wSenders2">${f.unique_senders}</b></div>
          <div><span>Your transfer out</span><b id="wOut">${alert.outbound_amount ? (alert.outbound_held ? "On hold" : "Sent") : "None yet"}</b></div>
        </div>
        <div class="actions">
          <button class="main" data-act="help">Pause, I need help</button>
          <button data-act="asked">Someone asked me to move it</button>
          <button data-act="legit">This is legitimate</button>
        </div>
        <div class="help">Free, confidential advice is available. You won't be judged for asking.</div>
      </div>`;
    screen.querySelectorAll("button[data-act]").forEach((b) =>
      b.addEventListener("click", () => api("/api/student-action", { action: b.dataset.act }).then(poll)));
  } else if (mode === "done") {
    screen.innerHTML = `
      <div class="done">
        <div class="tick">✓</div>
        <h3>Thanks. Your transfer is paused.</h3>
        <p>Nothing leaves your account until a specialist has spoken to you.
        You did the right thing by stopping.</p>
      </div>`;
  }
}

function updateWarnFacts(alert) {
  const f = alert.features;
  const set = (id, v) => { const el = $(id); if (el) el.textContent = v; };
  set("wTotal", gbp(f.total_in)); set("wTotal2", gbp(f.total_in));
  set("wSenders", f.unique_senders); set("wSenders2", f.unique_senders);
  set("wOut", alert.outbound_amount ? (alert.outbound_held ? "On hold" : "Sent") : "None yet");
}

// ---------------- right panel: analyst ----------------
function flowSvg(alert) {
  const senders = alert.senders;
  const W = 520, H = 230, cx = 260, cy = H / 2;
  const col = { green: "#24a148", amber: "#f1c21b", red: "#fa4d56" }[alert.status];
  const ys = senders.map((_, i) => senders.length === 1 ? cy : 26 + i * ((H - 52) / (senders.length - 1)));

  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Money flow graph">`;
  senders.forEach((snd, i) => {
    s += `<path d="M110 ${ys[i]} C 180 ${ys[i]}, 190 ${cy}, ${cx - 44} ${cy}" stroke="#4589ff" stroke-opacity=".55" stroke-width="2" fill="none"/>`;
    s += `<rect x="8" y="${ys[i] - 12}" width="102" height="24" rx="6" fill="#18223a" stroke="#24304d"/>`;
    s += `<text x="16" y="${ys[i] + 4}" fill="#c6d0e8" font-size="11" font-family="IBM Plex Mono, monospace">${esc(snd.id)}</text>`;
    s += `<text x="104" y="${ys[i] + 4}" fill="#8b97b3" font-size="10" text-anchor="end" font-family="IBM Plex Mono, monospace">${gbp(snd.amount)}</text>`;
  });
  if (alert.destination) {
    s += `<path d="M${cx + 44} ${cy} L 386 ${cy}" stroke="#f1c21b" stroke-width="2.5" stroke-dasharray="6 5" fill="none"/>`;
    s += `<text x="${(cx + 44 + 386) / 2}" y="${cy - 8}" fill="#fddc69" font-size="10" text-anchor="middle">${alert.outbound_held ? "HELD" : "SENT"} ${gbp(alert.outbound_amount)}</text>`;
    s += `<rect x="388" y="${cy - 22}" width="124" height="44" rx="8" fill="rgba(241,194,27,.1)" stroke="#f1c21b"/>`;
    s += `<text x="450" y="${cy - 3}" fill="#fddc69" font-size="11" text-anchor="middle" font-weight="600" font-family="IBM Plex Mono, monospace">${esc(alert.destination)}</text>`;
    s += `<text x="450" y="${cy + 12}" fill="#c9b46a" font-size="9.5" text-anchor="middle">next account in the chain</text>`;
  }
  s += `<circle cx="${cx}" cy="${cy}" r="44" fill="${col}" fill-opacity=".14" stroke="${col}" stroke-width="2"/>`;
  s += `<text x="${cx}" y="${cy - 3}" fill="#e6ebf5" font-size="12" text-anchor="middle" font-weight="700" font-family="IBM Plex Mono, monospace">${esc(alert.account_id)}</text>`;
  s += `<text x="${cx}" y="${cy + 13}" fill="#8b97b3" font-size="10" text-anchor="middle">${esc(alert.holder)}</text>`;
  s += `</svg>`;
  return s;
}

function renderAnalyst(alert) {
  const json = JSON.stringify(alert);
  if (json === lastAlertJson) return;
  lastAlertJson = json;

  if (!alert) {
    $("alertCount").textContent = "No open alerts";
    $("analyst").innerHTML = `
      <div class="empty">
        <div class="empty-icon">✓</div>
        <p>All monitored accounts look normal.</p>
        <p class="muted small">Press <b>Play a real case</b> to stream a real account from the test days through the model.</p>
      </div>`;
    return;
  }

  const f = alert.features;
  const pct = Math.round(alert.risk * 100);
  const col = { green: "var(--green)", amber: "var(--amber)", red: "var(--red)" }[alert.status];
  const label = { green: "Monitoring", amber: "Suspicious", red: "Likely mule" }[alert.status];
  $("alertCount").textContent = alert.status === "green" ? "Watching 1 account" : "1 open alert";

  $("analyst").innerHTML = `
    <div class="alert-top">
      <div class="gauge" style="--pct:${pct};--col:${col}">
        <div class="gauge-inner"><div><b>${pct}%</b><span>model score</span></div></div>
      </div>
      <div class="alert-title">
        <h3>${esc(alert.account_id)} · ${esc(alert.holder)}</h3>
        <span class="pill ${alert.status}">${label}</span>
        <div class="muted small" style="margin-top:6px">Riskier than ${(alert.risk_percentile * 100).toFixed(2)}% of payments</div>
      </div>
    </div>

    <div class="chips">
      <div class="chip"><span>Money in</span><b>${gbp(f.total_in)}</b></div>
      <div class="chip"><span>Senders</span><b>${f.unique_senders}</b></div>
      <div class="chip"><span>Minutes held</span><b>${f.minutes_held}</b></div>
    </div>

    <div class="subhead">Money flow</div>
    <div class="flow">${flowSvg(alert)}</div>

    <div class="subhead">Timeline</div>
    <ul class="timeline">
      ${alert.timeline.map((t) => `<li class="${t.kind}"><span class="tt">${esc(t.time)}</span>${esc(t.text)}</li>`).join("")}
    </ul>

    ${alert.reasons && alert.reasons.length ? `
    <div class="subhead">Why the model flagged it</div>
    <ul class="timeline">${alert.reasons.map((r) => `<li class="in">${esc(r)}</li>`).join("")}</ul>` : ""}

    <div class="ai-box">
      <div class="ai-label">${String(alert.explanation_source || "").startsWith("llm") ? "✦ AI EXPLANATION · IBM GRANITE" : "✦ EXPLANATION · FROM THE MODEL'S REASONS"}</div>
      <p>${esc(alert.explanation || "")}</p>
    </div>

    ${alert.student_response ? `
      <div class="response">📱 <b>${esc(alert.student_response.time)}</b> · ${esc(alert.student_response.text)}</div>` : ""}
  `;
}

// ---------------- loop ----------------
async function poll() {
  try {
    latest = await api("/api/state");
    $("simClock").textContent = latest.sim_time;
    const arch = latest.platform.arch;
    $("platformBadge").textContent = arch === "s390x"
      ? "Running on IBM LinuxONE · s390x"
      : `Running locally · ${arch}`;
    renderAccounts(latest.accounts);
    renderFeed(latest.feed);
    renderPhone(latest.alert, latest.sim_time, latest.sim_date);
    if (latest.error) $("simClock").textContent = latest.error;
    renderAnalyst(latest.alert);
  } catch (e) {
    $("simClock").textContent = "offline";
  }
}

$("runBtn").addEventListener("click", async () => {
  $("runBtn").disabled = true;
  await api("/api/run-scenario", {});
  poll();
});
$("resetBtn").addEventListener("click", async () => {
  await api("/api/reset", {});
  lastFeedKey = null; lastAlertJson = undefined; phoneMode = null;
  $("runBtn").disabled = false;
  poll();
});

poll();
setInterval(poll, POLL_MS);

// Arriving from the landing page's "Run Live Demo" button: reset and start automatically
if (new URLSearchParams(location.search).get("autostart") === "1") {
  setTimeout(async () => {
    await api("/api/reset", {});
    lastFeedKey = null; lastAlertJson = undefined; phoneMode = null;
    setTimeout(() => $("runBtn").click(), 1800);
  }, 400);
}
