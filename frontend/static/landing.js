// StudentShield landing page: nav shadow, animated pipeline, count-up stats, scroll reveals.

// Nav gets a background once you scroll
const nav = document.getElementById("nav");
const onScroll = () => nav.classList.toggle("scrolled", window.scrollY > 10);
window.addEventListener("scroll", onScroll, { passive: true });
onScroll();

// Hero pipeline: light up each step in turn, then loop
const steps = [...document.querySelectorAll("#pipeline .step")];
let active = 0;
function tickPipeline() {
  steps.forEach((s, i) => s.classList.toggle("on", i <= active));
  active = active >= steps.length ? 0 : active + 1;
}
tickPipeline();
setInterval(tickPipeline, 1300);

// Count-up numbers when the stats scroll into view
function countUp(el) {
  const target = parseFloat(el.dataset.count);
  const dec = parseInt(el.dataset.dec || "0", 10);
  const pre = el.dataset.prefix || "";
  const suf = el.dataset.suffix || "";
  const start = performance.now();
  const dur = 1200;
  function frame(now) {
    const t = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = pre + (target * eased).toFixed(dec) + suf;
    if (t < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

// Fade sections in as they appear
const revealTargets = document.querySelectorAll(".strip, .problem-grid > *, .how li, .stack, .compare .col, .cta-inner");
revealTargets.forEach((el) => el.classList.add("reveal"));

const io = new IntersectionObserver((entries) => {
  entries.forEach((e) => {
    if (!e.isIntersecting) return;
    e.target.classList.add("in");
    e.target.querySelectorAll?.("[data-count]").forEach(countUp);
    io.unobserve(e.target);
  });
}, { threshold: 0.2 });
revealTargets.forEach((el) => io.observe(el));
