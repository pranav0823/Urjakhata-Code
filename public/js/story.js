/* Guided demo ("Play demo"): steps through the views with captions, so a 4-minute
   video can be recorded straight from the site. Arrow keys move, Escape closes. */
(function () {
  "use strict";
  const D = window.URJA;
  if (!D || !window.UK) return;
  const H = D.headline, B0 = H.baseline, S1 = H.steady_state, C = D.config;
  const l = n => (n / 1e5).toFixed(1);
  const n0 = n => Math.round(n).toLocaleString("en-IN");
  const scenes = [
    { v: "overview", sel: "#kpis", cap: `A Rajkot foundry melting ${n0(H.annual_liquid_t)} t a year sees one monthly bill. UrjaKhata adds three meters and a WhatsApp heat log. In this 90-day simulation, furnace energy falls from ${n0(B0.sec_liquid)} to ${n0(S1.sec_liquid)} kWh per tonne and the plant saves Rs ${l(H.annual_rs_headline)} lakh a year.` },
    { v: "overview", sel: "#dumbbell", cap: `No new furnace: shorter holding, less superheat, a closed lid, cleaner charge, a compressor timer. Output (${S1.liquid_t_per_day.toFixed(1)} t a day) and rejects (${(S1.reject_rate * 100).toFixed(0)}%) stay where they were.` },
    { v: "briefing", sel: "#phone", cap: "Every morning at 7:30 the owner gets yesterday's energy per good tonne and three actions priced in rupees, in English or Hindi." },
    { v: "drift", sel: "#cusum", cap: `We hid a lining fault on day ${C.wear_start}. Energy the logged practice cannot explain builds up in the drift score, and the alert fires after ${H.drift_heats_after_onset} heats.` },
    { v: "machines", sel: "#stack", cap: window.URJA_REAL ? `Only the furnace and compressor are metered. A model splits the rest, with a confidence tier for each machine. On real factory data (IMDELD), ${window.URJA_REAL.tests.flatMap(t => t.per_load).filter(p => p.tier === "High").length} of ${window.URJA_REAL.tests.flatMap(t => t.per_load).length} machine estimates were within a few percent a week, and the one it could not split was flagged Low.` : "Only the furnace and compressor are metered. A model plus two physics rules splits the rest into six machines, with a confidence tier for each." },
    { v: "planner", sel: "#gantt", cap: `On the real FY 2026-27 Gujarat tariff, the optimiser moves melts out of both peaks into the 11 am to 5 pm solar window: Rs ${l(H.tod_isolated_annual_rs)} lakh a year with the same heats.` },
    { v: "carbon", sel: "#boundaries", cap: "Carbon is kept in two boundaries. The EU CBAM prices direct and pig-iron emissions, not electricity, so the passport proves the charge mix heat by heat and replaces marked-up EU defaults with verified actuals." },
    { v: "proof", sel: "#mvcards", cap: `For lenders and ADEETIE: an IPMVP Option B report verifies a ${(D.mv.option_b.savings_pct * 100).toFixed(1)}% furnace saving with a 90% confidence band.` },
    { v: "stress", sel: "#adh", cap: `Is that a best case? We re-ran the plant ${n0(D.robustness.savings.n)} times with operators following only part of the advice. Typical saving: Rs ${l(D.robustness.savings.percentiles.rs.p50)} lakh a year; even with every input at its worst, payback is ${D.robustness.savings.stress_case.payback_months.toFixed(0)} months. The drift alarm gives false alarms in ${(D.robustness.drift.scenarios.no_fault.residual.alarm_share * 100).toFixed(0)}% of months.` },
    { v: "feasibility", sel: "#bom", cap: `Off-the-shelf hardware: a Rs ${l(H.kit_rs[0])} to ${l(H.kit_rs[1])} lakh kit that pays back in about ${H.payback_months[0].toFixed(1)} to ${H.payback_months[1].toFixed(1)} months. Next: three Rajkot pilots.` },
  ];
  const el = id => document.getElementById(id);
  const bar = el("story");
  let i = 0, active = false;
  function go(k) {
    i = Math.max(0, Math.min(scenes.length - 1, k));
    const s = scenes[i];
    if (location.hash.slice(1) !== s.v) { history.replaceState(null, "", "#" + s.v); window.UK.show(s.v); }
    document.querySelectorAll(".spot").forEach(e => e.classList.remove("spot"));
    const t = document.querySelector(s.sel);
    if (t) {
      t.classList.add("spot");
      const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
      const y = t.getBoundingClientRect().top + window.scrollY - 120;
      window.scrollTo({ top: Math.max(0, y), behavior: reduce ? "auto" : "smooth" });
    }
    el("storyStep").textContent = `Step ${i + 1} of ${scenes.length}`;
    el("storyCap").textContent = s.cap;
    el("storyProg").style.width = `${((i + 1) / scenes.length) * 100}%`;
    el("storyPrev").disabled = i === 0;
    el("storyNext").textContent = i === scenes.length - 1 ? "Finish" : "Next";
  }
  function open() { active = true; bar.hidden = false; go(0); el("storyNext").focus(); }
  function close() { active = false; bar.hidden = true; document.querySelectorAll(".spot").forEach(e => e.classList.remove("spot")); }
  el("playBtn").addEventListener("click", open);
  el("storyNext").addEventListener("click", () => (i === scenes.length - 1 ? close() : go(i + 1)));
  el("storyPrev").addEventListener("click", () => go(i - 1));
  el("storyClose").addEventListener("click", close);
  document.addEventListener("keydown", e => {
    if (!active) return;
    if (e.key === "ArrowRight") { e.preventDefault(); i === scenes.length - 1 ? close() : go(i + 1); }
    if (e.key === "ArrowLeft") { e.preventDefault(); go(i - 1); }
    if (e.key === "Escape") close();
  });
  if (location.hash === "#demo") open();
})();
