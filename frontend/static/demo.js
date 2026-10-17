// StudentShield frontend: polls the Flask API and renders the three panels.

const POLL_MS = 800;
const $ = (id) => document.getElementById(id);

let seenRows = new Set();
let lastFeedHtml = "";
let lastAlertJson = null;
let phoneMode = null;
let pausedAt = 0;        // inbound payments covered by the student's latest answer

// What the phone says after each answer. The question is about ALL the money, so one answer covers every sender.
const ANSWER_COPY = {
  help:  { short: "Pause, I need help", title: "Payments out of your account are paused.",
           body: "Money can still come in, but nothing can be sent out until a specialist has spoken to you. You did the right thing by stopping." },
  asked: { short: "Someone asked me to move it", title: "Thank you for telling us.",
           body: "Payments out of your account are paused and a specialist will call you. Don't reply to whoever asked you to move it." },
  legit: { short: "This is legitimate", title: "Thanks, we'll check this quickly.",
           body: "Payments out stay on hold while we confirm. This usually takes less than a day." },
};   // "idle" | "notif" | "warn" | "done"
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
    <div class="acct ${a.status}" title="${esc(a.id)}">
      <div class="id">${esc(a.id)}</div>
      <div class="lbl">${esc(a.label)} · ${Math.round(a.risk * 100)}%</div>
    </div>`).join("");
}

function feedRow(p) {
  const cls = p.kind === "held" ? "held" : p.flag ? "flag" : "";
  const arrow = "→";
  return `<li class="${cls}">
    <span class="t">${esc(p.time)}</span>
    <span class="ft"><span title="${esc(p.from)}">${esc(p.from)}</span><span class="to" title="${esc(p.to)}">${arrow} ${esc(p.to)}</span></span>
    <span class="amt">${p.kind === "held" ? "HELD " : ""}${gbp(p.amount)}</span></li>`;
}

function renderFeed(feed) {
  // Rebuilt each poll (max 18 rows): a day divider goes above each run of same-day payments.
  // Only rows not seen before get the slide-in animation.
  const key = (p) => (p.date || "") + p.time + p.from + p.to + p.amount;
  const html = [];
  let day = null;
  feed.forEach((p) => {
    if (p.date && p.date !== day) { html.push(`<li class="day">${esc(p.date)}</li>`); day = p.date; }
    const row = feedRow(p);
    html.push(seenRows.has(key(p)) ? row.replace("<li ", '<li style="animation:none" ') : row);
  });
  const next = html.join("");
  if (next !== lastFeedHtml) { $("feed").innerHTML = next; lastFeedHtml = next; }
  seenRows = new Set(feed.map(key));
}

// ---------------- middle panel: phone ----------------
function renderPhone(alert, simTime, simDate) {
  let mode = "idle";
  if (alert && alert.student_response) mode = "done:" + alert.student_responses.length;
  else if (alert && alert.status === "red") mode = "warn";
  else if (alert && alert.status === "amber") mode = "notif";

  const hhmm = simTime.slice(0, 5);
  if (mode === phoneMode && mode === "idle") {
    const t = document.querySelector(".big-time");
    if (t) t.textContent = hhmm;
    return;
  }
  if (mode === phoneMode) {
    if (mode === "warn") updateWarnFacts(alert, simTime);
    if (mode.startsWith("done")) updateDone(alert, simTime);
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
        <div class="warn-new" id="wNew"></div>
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
  } else if (mode.startsWith("done")) {
    const r = alert.student_response;
    const copy = ANSWER_COPY[r.action] || ANSWER_COPY.help;
    screen.innerHTML = `
      <div class="done">
        <div class="tick ${r.action === "legit" ? "info" : ""}">${r.action === "legit" ? "i" : "✓"}</div>
        <h3>${copy.title}</h3>
        <p>${copy.body}</p>
        <div class="since" id="dSince"></div>
      </div>
      <div class="warn-new" id="wNew"></div>`;
    pausedAt = r.covers;
    updateDone(alert, simTime);
  }
}

function updateWarnFacts(alert, simTime) {
  // The warning stays up while more money arrives; make each change visible so the screen never looks frozen.
  const f = alert.features;
  const out = alert.outbound_amount ? (alert.outbound_held ? "On hold" : "Sent") : "None yet";
  let changed = false;
  const set = (id, v) => {
    const el = $(id);
    if (!el || el.textContent === String(v)) return;
    el.textContent = v;
    el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump");   // restart the flash
    changed = true;
  };
  const outBefore = $("wOut") ? $("wOut").textContent : out;
  set("wTotal", gbp(f.total_in)); set("wTotal2", gbp(f.total_in));
  set("wSenders", f.unique_senders); set("wSenders2", f.unique_senders);
  set("wOut", out);
  if (!changed) return;
  const msg = out !== outBefore && out === "On hold" ? "Transfer put on hold"
            : out !== outBefore && out === "Sent" ? "Money left your account"
            : "New payment received";
  const banner = $("wNew");
  if (banner) {
    banner.textContent = `${msg} · ${String(simTime || "").slice(0, 5)}`;
    banner.classList.remove("show"); void banner.offsetWidth; banner.classList.add("show");
  }
}

// After the student answers, money can keep arriving. Their answer covers all of it, so when new money lands
// we list it and ask once more whether the answer still stands (one decision about the situation, not per payment).
function updateDone(alert, simTime) {
  const box = $("dSince");
  if (!box) return;
  const r = alert.student_response;
  const later = alert.senders.slice(pausedAt);
  const out = alert.outbound_amount ? (alert.outbound_held ? "On hold" : "Sent") : "None";
  const key = later.length + "|" + out;
  const prev = box.dataset.n;
  if (prev === key) return;
  const grew = prev !== undefined;
  const outChanged = grew && prev.split("|")[1] !== out;
  box.dataset.n = key;

  const shown = later.slice(-3);
  box.innerHTML = `
    <div class="row"><span>Your answer</span><b>${esc((ANSWER_COPY[r.action] || {}).short || r.text)}</b></div>
    <div class="row"><span>Your transfer out</span><b>${out}</b></div>
    ${later.length ? `
      <div class="ask">
        <b>${later.length} more payment${later.length > 1 ? "s" : ""} arrived since you answered</b>
        <ul>${later.length > shown.length ? `<li class="more">+ ${later.length - shown.length} earlier</li>` : ""}${shown.map((x) =>
          `<li>+${gbp(x.amount)} <span>from ${esc(x.id)}</span></li>`).join("")}</ul>
        <p>Does your answer still stand?</p>
        <div class="mini">${Object.entries(ANSWER_COPY).map(([k, v]) =>
          `<button data-act="${k}" class="${k === r.action ? "cur" : ""}">${k === r.action ? "Yes · " : ""}${v.short}</button>`).join("")}</div>
      </div>` : `<p class="note">If more money arrives we'll check in with you again. Don't send any of it on.</p>`}`;
  box.querySelectorAll("button[data-act]").forEach((b) =>
    b.addEventListener("click", () => api("/api/student-action", { action: b.dataset.act }).then(poll)));

  const banner = $("wNew");
  if (grew && banner) {
    const msg = outChanged ? (out === "On hold" ? "Transfer put on hold" : "Money left your account") : "New payment received";
    banner.textContent = `${msg} · ${String(simTime || "").slice(0, 5)}`;
    banner.classList.remove("show"); void banner.offsetWidth; banner.classList.add("show");
  }
}

// ---------------- right panel: analyst ----------------
function flowSvg(alert) {
  // Layout: senders (left) -> account (centre) -> next account (right).
  // Sender cards are wide enough for the account id and the amount side by side,
  // and rows are at least 32px apart, so labels never overlap (up to 8 senders).
  const senders = alert.senders;
  const ROW = 32, PAD = 22;
  const W = 640, H = Math.max(230, PAD * 2 + ROW * (senders.length - 1) + 24);
  const cx = 330, cy = H / 2, R = 44;
  const cardX = 8, cardW = 196;
  const col = { green: "#24a148", amber: "#f1c21b", red: "#fa4d56" }[alert.status];
  const span = ROW * (senders.length - 1);
  const ys = senders.map((_, i) => senders.length === 1 ? cy : cy - span / 2 + i * ROW);
  const mono = 'font-family="IBM Plex Mono, monospace"';

  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Money flow graph">`;
  senders.forEach((snd, i) => {
    s += `<path d="M${cardX + cardW} ${ys[i]} C ${cardX + cardW + 60} ${ys[i]}, ${cx - R - 50} ${cy}, ${cx - R} ${cy}" stroke="#4589ff" stroke-opacity=".55" stroke-width="2" fill="none"/>`;
    s += `<rect x="${cardX}" y="${ys[i] - 12}" width="${cardW}" height="24" rx="6" fill="#18223a" stroke="#24304d"/>`;
    s += `<text x="${cardX + 8}" y="${ys[i] + 4}" fill="#c6d0e8" font-size="11" ${mono}>${esc(snd.id)}</text>`;
    s += `<text x="${cardX + cardW - 8}" y="${ys[i] + 4}" fill="#8b97b3" font-size="10.5" text-anchor="end" ${mono}>${gbp(snd.amount)}</text>`;
  });
  if (alert.destination) {
    const x1 = cx + R, x2 = 470, mid = (x1 + x2) / 2;
    s += `<path d="M${x1} ${cy} L ${x2} ${cy}" stroke="#f1c21b" stroke-width="2.5" stroke-dasharray="6 5" fill="none"/>`;
    // label on two short lines above the arrow, so it fits between the circle and the box
    s += `<text x="${mid}" y="${cy - 22}" fill="#fddc69" font-size="10" font-weight="700" text-anchor="middle">${alert.outbound_held ? "HELD" : "SENT"}</text>`;
    s += `<text x="${mid}" y="${cy - 9}" fill="#fddc69" font-size="10" text-anchor="middle" ${mono}>${gbp(alert.outbound_amount)}</text>`;
    s += `<rect x="${x2 + 2}" y="${cy - 22}" width="${W - x2 - 10}" height="44" rx="8" fill="rgba(241,194,27,.1)" stroke="#f1c21b"/>`;
    const bx = (x2 + 2 + W - 8) / 2;
    s += `<text x="${bx}" y="${cy - 3}" fill="#fddc69" font-size="11" text-anchor="middle" font-weight="600" ${mono}>${esc(alert.destination)}</text>`;
    s += `<text x="${bx}" y="${cy + 12}" fill="#c9b46a" font-size="9.5" text-anchor="middle">next account in the chain</text>`;
  }
  s += `<circle cx="${cx}" cy="${cy}" r="${R}" fill="${col}" fill-opacity=".14" stroke="${col}" stroke-width="2"/>`;
  s += `<text x="${cx}" y="${cy - 3}" fill="#e6ebf5" font-size="12" text-anchor="middle" font-weight="700" ${mono}>${esc(alert.account_id)}</text>`;
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
        <div class="muted small" style="margin-top:6px">${esc(alert.rarity || "")}</div>
      </div>
    </div>

    <div class="chips">
      <div class="chip"><span>Money in</span><b>${gbp(f.total_in)}</b></div>
      <div class="chip"><span>Senders</span><b>${f.unique_senders}</b></div>
      <div class="chip"><span>Minutes held</span><b>${f.minutes_held}</b></div>
    </div>

    ${alert.lead_time ? `
    <div class="lead ${alert.lead_time.kind}">⏱ <b>${esc(alert.lead_time.text)}</b>
      <span>Money left at ${esc(alert.lead_time.out_time)}${alert.outbound_held ? " and was held for review" : ""}.</span></div>` : ""}

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

    ${(alert.student_responses || []).map((r) => `
      <div class="response ${r.action}">📱 <b>${esc(r.time)}</b> · Student ${r.repeat ? (r.changed ? "changed their answer: " : "confirmed: ") : ""}${esc(r.text)}
        <span>covers ${r.covers} payment${r.covers === 1 ? "" : "s"} received so far</span></div>`).join("")}
  `;
}

// ---------------- loop ----------------
async function poll() {
  try {
    latest = await api("/api/state");
    $("simClock").textContent = latest.sim_day ? `${latest.sim_day} · ${latest.sim_time}` : latest.sim_time;
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
  seenRows = new Set(); lastFeedHtml = ""; lastAlertJson = undefined; phoneMode = null;
  $("runBtn").disabled = false;
  poll();
});

poll();
setInterval(poll, POLL_MS);

// Arriving from the landing page's "Run Live Demo" button: reset and start automatically
if (new URLSearchParams(location.search).get("autostart") === "1") {
  setTimeout(async () => {
    await api("/api/reset", {});
    seenRows = new Set(); lastFeedHtml = ""; lastAlertJson = undefined; phoneMode = null;
    setTimeout(() => $("runBtn").click(), 1800);
  }, 400);
}
