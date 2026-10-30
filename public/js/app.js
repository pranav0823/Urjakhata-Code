/* UrjaKhata demo site. Reads window.URJA (public/data/urjakhata-data.js), renders ten views. */
(function () {
  "use strict";
  const D = window.URJA;
  const app = document.getElementById("app");
  if (!D) { app.innerHTML = "<p>Data file missing: run <code>python -m engine.pipeline</code>.</p>"; return; }
  const H = D.headline, C = D.config, B0 = H.baseline, S1 = H.steady_state;
  const RB = D.robustness, RS = RB.savings.percentiles.rs, NS = D.nilm.seeds.tests;
  const charts = [];

  /* ---------- helpers ---------- */
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const inr = (n, d = 0) => Number(n).toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: d });
  const lakh = n => (n / 1e5).toFixed(1);
  const pct = (n, d = 1) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(d)}%`;
  const hhmm = h => { const m = Math.round(h * 60); return `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`; };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const badge = kind => `<span class="badge ${kind === "sim" ? "sim" : kind === "src" || kind === "real" ? "src" : "asm"}">${kind === "sim" ? "Simulated" : kind === "src" ? "Sourced" : kind === "real" ? "Real data" : "Assumption"}</span>`;
  const LOADS = { cooling_pump: "Cooling tower pump", fume_extraction: "Fume extraction", sand_mixer: "Sand mixer",
    shot_blast: "Shot blast", grinders: "Grinders (3, grouped)", lighting_office: "Lighting and office" };
  const PEAK_TXT = "7 to 11 am and 6 to 10 pm";
  const wearEnd = H.reline_day;
  const EVENTS = [
    [1, "Three meters installed. Days 1 to " + C.baseline_days + " record the baseline; nothing is changed."],
    [C.sop_start, "Owner starts acting on the daily briefings: tap on time, check the pyrometer, keep the lid closed, cleaner charge."],
    [C.compressor_fix, "Compressed-air leaks fixed and a shutdown timer fitted to the compressor."],
    [C.tod_start, "Melts follow the Time-of-Day plan for the Gujarat tariff: heats move out of both peaks."],
    [C.wear_start, "Hidden fault injected: furnace lining wear starts lowering efficiency. The plant does not know."],
    [H.drift_alert.day, `Drift alert on heat ${H.drift_alert.heat_id}: melting uses more energy than the logged practice explains.`],
    [wearEnd, "Lining repaired after the alert; efficiency recovers."],
  ];

  function chartDefaults() {
    if (!window.Chart) return;
    Chart.defaults.font.family = css("--ui");
    Chart.defaults.font.size = 12;
    Chart.defaults.color = css("--muted");
    Chart.defaults.borderColor = css("--line");
    Chart.defaults.plugins.legend.labels.boxWidth = 10;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.animation = false;
  }
  const bands = list => ({ id: "bands", beforeDatasetsDraw(ch) {
    const { ctx, chartArea: a, scales: { x } } = ch; ctx.save();
    for (const b of list) {
      const x0 = Math.max(a.left, x.getPixelForValue(b.from)), x1 = Math.min(a.right, x.getPixelForValue(b.to));
      ctx.fillStyle = b.color; ctx.fillRect(x0, a.top, x1 - x0, a.bottom - a.top);
      if (b.label) { ctx.fillStyle = css("--muted"); ctx.font = `11px ${css("--ui")}`; ctx.fillText(b.label, x0 + 4, a.top + 12); }
    }
    ctx.restore(); } });
  const vlines = list => ({ id: "vlines", afterDatasetsDraw(ch) {
    const { ctx, chartArea: a, scales: { x } } = ch; ctx.save(); ctx.lineWidth = 1.2;
    list.forEach((l, i) => {
      const px = x.getPixelForValue(l.at); ctx.setLineDash(l.solid ? [] : [4, 4]);
      ctx.strokeStyle = l.color; ctx.beginPath(); ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); ctx.stroke();
      ctx.fillStyle = l.color; ctx.font = `600 11px ${css("--ui")}`;
      const w = ctx.measureText(l.label).width;
      ctx.fillText(l.label, Math.min(px + 4, a.right - w - 2), a.top + 14 + (l.row || 0) * 14);
    });
    ctx.restore(); } });
  function hatch(color) {
    const c = document.createElement("canvas"); c.width = c.height = 8;
    const g = c.getContext("2d"); g.fillStyle = color + "55"; g.fillRect(0, 0, 8, 8);
    g.strokeStyle = color; g.lineWidth = 2; g.beginPath(); g.moveTo(0, 8); g.lineTo(8, 0); g.stroke();
    return g.createPattern(c, "repeat");
  }
  function mk(id, cfg) { if (!window.Chart) return null; const c = new Chart(document.getElementById(id), cfg); charts.push(c); return c; }

  /* ---------- views ---------- */
  const V = {};

  V.overview = () => {
    const B = D.mv.option_b;
    const lo = (B.savings_pct * (1 - B.fsu_90) * 100).toFixed(1), hi = (B.savings_pct * (1 + B.fsu_90) * 100).toFixed(1);
    const rows = [
      ["Furnace energy", "kWh per liquid tonne", B0.sec_liquid, S1.sec_liquid, 0],
      ["Whole plant", "kWh per good tonne of castings", B0.sec_good_plant, S1.sec_good_plant, 0],
      ["Holding after melt-down", "minutes per heat", B0.hold_min, S1.hold_min, 1],
      ["Superheat above target", "degrees C", B0.superheat_c, S1.superheat_c, 1],
      ["Compressor", "kWh per day", B0.compressor_kwh_per_day, S1.compressor_kwh_per_day, 0],
      ["Energy in peak hours", "% of plant energy", B0.peak_share * 100, S1.peak_share * 100, 0],
    ];
    app.innerHTML = `
    <section class="view">
      <div><h1>One foundry, 90 days: ${H.sec_good_plant_reduction_pct.toFixed(0)}% less energy per good tonne, with output and quality unchanged</h1>
      <p class="lede">A Rajkot grey-iron foundry melting ${inr(H.annual_liquid_t)} t a year in a 500 kg, 550 kW induction furnace. Three meters and a production log feed one ledger. Days 1 to ${C.baseline_days} are the baseline; from day ${C.sop_start} the owner acts on the daily briefing.</p></div>
      <div class="kpis" id="kpis">
        <div class="kpi"><div class="lab">Furnace energy per liquid tonne</div><div class="val">${inr(S1.sec_liquid)} <small>kWh/t</small></div>
          <div class="from">was ${inr(B0.sec_liquid)} <span class="delta good">${pct(-H.sec_liquid_reduction_pct)}</span></div>
          <div class="band">Verified (IPMVP Option B): ${lo}% to ${hi}% saving at 90% confidence</div></div>
        <div class="kpi"><div class="lab">Saved per year, full adoption</div><div class="val">Rs ${lakh(H.annual_rs_headline)} <small>lakh</small></div>
          <div class="from">Rs ${lakh(H.annual_rs_from_energy)} lakh less energy + Rs ${lakh(H.tod_isolated_annual_rs)} lakh cheaper hours; payback ${H.payback_months[0].toFixed(1)} to ${H.payback_months[1].toFixed(1)} months</div>
          <div class="band">Typical case over ${inr(RB.savings.n)} runs: Rs ${lakh(RS.p50)} lakh (P10 to P90: ${lakh(RS.p10)} to ${lakh(RS.p90)})</div></div>
        <div class="kpi"><div class="lab">CO2 avoided per year</div><div class="val">${inr(H.annual_tco2_reporting)} <small>tCO2</small></div>
          <div class="from">${inr(H.annual_mwh_saved)} MWh at CEA ${C.grid_ef}; ${inr(H.annual_tco2_ccts)} t at the CCTS factor ${C.grid_ef_ccts}</div>
          <div class="band">Electricity (Scope 2); not priced by EU CBAM for iron and steel</div></div>
      </div>
      <div class="mini">
        <div><b>${S1.liquid_t_per_day.toFixed(2)} t/day</b>liquid metal, was ${B0.liquid_t_per_day.toFixed(2)} (${pct(H.throughput_change_pct)})</div>
        <div><b>${(S1.reject_rate * 100).toFixed(1)}% rejects</b>was ${(B0.reject_rate * 100).toFixed(1)}%: quality held</div>
        <div><b>${H.drift_heats_after_onset} heats</b>to catch a hidden lining fault; false alarms in ${(RB.drift.scenarios.no_fault.residual.alarm_share * 100).toFixed(0)}% of months</div>
        <div><b>${inr(H.annual_furnace_kwh_saved / 1000)} + ${inr(H.annual_compressor_kwh_saved / 1000)} MWh</b>furnace practice + compressed air, per year</div>
      </div>
      <div class="grid g3">
        <div class="panel" id="dumbbell">${badge("sim")}<h2>Before and after</h2>
          <p class="note" style="margin-top:0">Grey: baseline (days 1 to ${C.baseline_days}). Green: steady state with UrjaKhata (days 40 to 90, lining-wear days ${C.wear_start} to ${wearEnd} left out).</p>
          <div class="dumb">${rows.map(r => dumbRow(...r)).join("")}</div></div>
        <div class="panel">${badge("sim")}<h2>What happened</h2><div class="timeline">${EVENTS.map(e => `<div class="ev"><b>Day ${e[0]}</b><p>${esc(e[1])}</p></div>`).join("")}</div></div>
      </div>
      <div class="panel" id="secchart">${badge("sim")}<h2>Energy per good tonne, day by day</h2>
        <div class="legend"><span><i style="background:${css("--base")}"></i>Daily value</span><span><i style="background:${css("--good")}"></i>7-day average</span><span><i style="background:${css("--band-peak")};outline:1px solid ${css("--bad")}"></i>Lining wear (hidden fault)</span></div>
        <div class="chart tall"><canvas id="c1" role="img" aria-label="Daily plant energy per good tonne over 90 days, falling after day ${C.sop_start}"></canvas></div></div>
    </section>`;
    const days = D.daily.map(d => d.day), sec = D.daily.map(d => d.sec_good_plant);
    const ma = sec.map((_, i) => { const w = sec.slice(Math.max(0, i - 6), i + 1); return w.reduce((a, b) => a + b, 0) / w.length; });
    mk("c1", { type: "line", data: { labels: days, datasets: [
        { data: sec, borderColor: css("--base"), backgroundColor: css("--base"), pointRadius: 2, showLine: false },
        { data: ma, borderColor: css("--good"), borderWidth: 2.5, pointRadius: 0, tension: .3 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { title: i => `Day ${i[0].label}`, label: i => `${inr(i.raw)} kWh per good tonne` } } },
        scales: { x: { type: "linear", min: 1, max: C.days, title: { display: true, text: "Operating day" }, grid: { display: false } },
                  y: { title: { display: true, text: "kWh per good tonne" } } } },
      plugins: [bands([{ from: 0.5, to: C.baseline_days + .5, color: css("--tint"), label: "Baseline" }, { from: C.wear_start - .5, to: wearEnd - .5, color: css("--band-peak") }]),
        vlines([{ at: C.sop_start, label: "Actions start", color: css("--muted") }, { at: C.tod_start, label: "ToD plan", color: css("--muted"), row: 1 }, { at: H.drift_alert.day, label: "Drift alert", color: css("--bad"), row: 2 }])] });
  };
  function dumbRow(name, unit, b, n, d) {
    const lo = Math.min(b, n), hi = Math.max(b, n), pad = (hi - lo) * 0.6 || 1;
    const min = Math.max(0, lo - pad), max = hi + pad, p = v => ((v - min) / (max - min)) * 100;
    const ch = 100 * (n / b - 1);
    return `<div class="drow"><div class="name">${esc(name)}<small>${esc(unit)} <span class="delta ${ch < 0 ? "good" : "bad"}">${pct(ch)}</span></small></div>
      <div class="track" role="img" aria-label="${esc(name)}: ${inr(b, d)} to ${inr(n, d)} ${esc(unit)}"><div class="rule"></div>
      <div class="link" style="left:${p(lo)}%;width:${p(hi) - p(lo)}%"></div>
      <div class="dot b" style="left:${p(b)}%"></div><div class="dot n" style="left:${p(n)}%"></div>
      <div class="tag b" style="left:${p(b)}%">${inr(b, d)}</div><div class="tag n" style="left:${p(n)}%">${inr(n, d)}</div></div></div>`;
  }

  let bDay = 85, bLang = "en";
  V.briefing = () => {
    app.innerHTML = `
    <section class="view">
      <div><h1>The owner's 7:30 am briefing</h1><p class="lede">Yesterday's energy per good tonne and the three actions worth the most money, valued at the Gujarat tariff, in the owner's language. Pick a day to see what the ledger sent.</p></div>
      <div class="panel controls">
        <label for="dsl">Day <b id="dlab"></b></label>
        <input type="range" id="dsl" min="2" max="${C.days}" value="${bDay}">
        <button class="btn" id="pre1" type="button">Day 15: baseline</button><button class="btn" id="pre2" type="button">Day ${H.drift_alert.day + 1}: drift</button><button class="btn" id="pre3" type="button">Day 85: steady</button>
        <span class="controls" role="group" aria-label="Language" style="margin-left:auto"><button class="btn" id="len" type="button" aria-pressed="${bLang === "en"}">English</button><button class="btn" id="lhi" type="button" aria-pressed="${bLang === "hi"}" lang="hi">हिन्दी</button></span>
      </div>
      <div class="grid g3">
        <div class="phone" id="phone"><div class="screen"><div class="chat-head">UrjaKhata <span id="ptime"></span></div><div class="msgs" id="msgs"></div></div></div>
        <div class="panel">${badge("sim")}<h2>Yesterday's heats</h2><div class="tablewrap"><table id="ytab"></table></div>
        <p class="note">Rupee values: 6 operating days a week at the effective PGVCL rate (energy, FPPAS and 15% duty). Holding time and peak use come from the furnace meter; superheat and slag from the pyrometer and the WhatsApp heat log.</p></div>
      </div>
    </section>`;
    const sl = document.getElementById("dsl");
    const draw = () => {
      const b = D.briefings[bDay]; document.getElementById("dlab").textContent = bDay;
      const hi = bLang === "hi";
      const head = hi
        ? `सुप्रभात रमेशभाई। कल (दिन ${bDay - 1}): <b>${inr(b.yesterday_sec_good)} kWh प्रति अच्छा टन</b>। इस हफ़्ते का सबसे अच्छा: ${inr(b.best_week_sec_good)}। कल का बिजली खर्च: Rs ${inr(b.yesterday_cost)}।`
        : `Good morning, Rameshbhai. Yesterday (day ${bDay - 1}): <b>${inr(b.yesterday_sec_good)} kWh per good tonne</b>. Best this week: ${inr(b.best_week_sec_good)}. Electricity yesterday: Rs ${inr(b.yesterday_cost)}.`;
      const cards = b.cards.map((c, i) => `<div class="msg ${c.kind === "drift" ? "alert" : ""}">${i + 1}. ${esc(hi ? c.hi : c.text)}<span class="rs">${hi ? `लगभग Rs ${inr(c.rs_week)} प्रति हफ़्ता बचत` : `Worth about Rs ${inr(c.rs_week)} a week`}</span><span class="t">7:30</span></div>`).join("");
      document.getElementById("msgs").innerHTML = `<div class="msg"${hi ? ' lang="hi"' : ""}>${head}<span class="t">7:30</span></div>${cards || `<div class="msg">${hi ? "कल कोई बड़ी गड़बड़ी नहीं मिली।" : "No costly issues found yesterday."}</div>`}`;
      document.getElementById("ptime").textContent = hi ? `दिन ${bDay}, सुबह 7:30` : `Day ${bDay}, 7:30 am`;
      const ys = D.heats.filter(h => h.day === bDay - 1);
      const inPeak = h => (h.start_h < 11 && h.end_h > 7) || (h.start_h < 22 && h.end_h > 18);
      document.getElementById("ytab").innerHTML = `<thead><tr><th>Heat</th><th>Start</th><th class="num">kWh/t</th><th class="num">Hold min</th><th>Flags</th></tr></thead><tbody>${ys.map(h => {
        const f = [];
        if (h.hold_min > 12) f.push(`<span class="chip warn">long hold</span>`);
        if (h.superheat_c > 20) f.push(`<span class="chip warn">superheat</span>`);
        if (h.slag_pct > 2.8) f.push(`<span class="chip warn">slag</span>`);
        if (inPeak(h)) f.push(`<span class="chip mute">peak hours</span>`);
        return `<tr><td>${h.heat_no}</td><td>${hhmm(h.start_h)}</td><td class="num">${inr(h.sec_liquid)}</td><td class="num">${h.hold_min.toFixed(0)}</td><td>${f.join(" ") || `<span class="chip ok">ok</span>`}</td></tr>`; }).join("")}</tbody>`;
    };
    sl.oninput = () => { bDay = +sl.value; draw(); };
    [["pre1", 15], ["pre2", H.drift_alert.day + 1], ["pre3", 85]].forEach(([id, d]) => document.getElementById(id).onclick = () => { bDay = d; sl.value = d; draw(); });
    document.getElementById("len").onclick = () => { bLang = "en"; V.briefing(); };
    document.getElementById("lhi").onclick = () => { bLang = "hi"; V.briefing(); };
    draw();
  };

  let hDay = null;
  V.drift = () => {
    const a = H.drift_alert, m = H.drift_model, th = C.cusum_h;
    const hs = D.heats;
    if (hDay === null) hDay = a.day;
    const iOn = hs.findIndex(h => h.day >= C.wear_start), iAl = hs.findIndex(h => h.heat_id === a.heat_id), iFix = hs.findIndex(h => h.day >= wearEnd);
    app.innerHTML = `
    <section class="view">
      <div><h1>A hidden fault, caught in ${H.drift_heats_after_onset} heats</h1>
      <p class="lede">Each heat's melting energy is compared with what the logged practice (superheat, slag, charge weight) predicts. The leftover, which the operators cannot explain, is tracked with a CUSUM test. In the simulation the furnace lining starts wearing on day ${C.wear_start}; the alert fires on heat ${a.heat_id}.</p></div>
      <div class="kpis">
        <div class="kpi"><div class="lab">Unexplained extra energy at alert</div><div class="val">${a.unexplained_kwh_t.toFixed(1)} <small>kWh/t</small></div><div class="from">Normal heat-to-heat spread: ${a.resid_sd.toFixed(1)} kWh/t</div></div>
        <div class="kpi"><div class="lab">Detected after</div><div class="val">${H.drift_heats_after_onset} <small>heats</small></div><div class="from">about ${(H.drift_heats_after_onset / 10).toFixed(1)} days after the fault began</div></div>
        <div class="kpi"><div class="lab">Energy avoided by early repair</div><div class="val">${inr(H.drift_avoided_kwh_to_day90)} <small>kWh</small></div><div class="from">to day ${C.days}, compared with no alert</div></div>
      </div>
      <div class="panel" id="cusum">${badge("sim")}<h2>Drift score for every heat</h2>
        <div class="chart"><canvas id="c3" role="img" aria-label="CUSUM drift score by heat, crossing the alert threshold after the lining fault starts"></canvas></div>
        <p class="note">Model fitted on days ${C.tod_start} to ${C.wear_start - 1}: melting kWh/t = ${m.beta[0].toFixed(0)} + ${m.beta[1].toFixed(2)} x superheat + ${m.beta[2].toFixed(1)} x slag% + ${m.beta[3].toFixed(3)} x charge kg. Alert when the score passes ${th}. That threshold was chosen by testing ${RB.drift.runs} simulated plant-months per case: false alarms in ${(RB.drift.scenarios.no_fault.residual.alarm_share * 100).toFixed(0)}% of months (see Stress tests).</p></div>
      <div class="grid g2">
        <div class="panel">${badge("sim")}<h2>Unexplained energy per heat</h2><div class="chart"><canvas id="c4" role="img" aria-label="Residual melting energy per heat"></canvas></div></div>
        <div class="panel"><h2>Heats on day <span id="hdl"></span></h2>
          <div class="controls"><label for="hsel">Day</label><select id="hsel">${D.daily.map(d => `<option ${d.day === hDay ? "selected" : ""}>${d.day}</option>`).join("")}</select></div>
          <div class="tablewrap"><table id="htab"></table></div></div>
      </div>
    </section>`;
    const marks = [{ at: iOn, label: "Fault starts", color: css("--warn") }, { at: iAl, label: "Alert", color: css("--bad"), solid: true, row: 1 }, { at: iFix, label: "Repaired", color: css("--good"), row: 2 }];
    const tick = v => hs[v] ? `Day ${hs[v].day}` : "";
    mk("c3", { type: "line", data: { labels: hs.map((_, i) => i), datasets: [
        { data: hs.map(h => h.cusum), borderColor: css("--accent"), borderWidth: 1.6, pointRadius: 0 },
        { data: hs.map(() => th), borderColor: css("--bad"), borderDash: [5, 4], borderWidth: 1, pointRadius: 0 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { title: i => hs[i[0].dataIndex].heat_id, label: i => i.datasetIndex ? `Alert threshold ${th}` : `Score ${i.raw.toFixed(1)}` } } },
        scales: { x: { type: "linear", min: 0, max: hs.length - 1, grid: { display: false }, ticks: { callback: tick, maxTicksLimit: 10 } }, y: { title: { display: true, text: "Drift score" } } } },
      plugins: [vlines(marks)] });
    const col = h => h.day >= C.wear_start && h.day < wearEnd ? css("--bad") : h.day <= C.baseline_days ? css("--base") : css("--good");
    mk("c4", { type: "scatter", data: { datasets: [{ data: hs.map((h, i) => ({ x: i, y: h.drift_resid })), pointBackgroundColor: hs.map(col), pointBorderWidth: 0, pointRadius: 2 }] },
      options: { plugins: { legend: { display: false }, tooltip: { callbacks: { label: i => `${hs[i.dataIndex].heat_id}: ${i.raw.y.toFixed(1)} kWh/t unexplained` } } },
        scales: { x: { type: "linear", grid: { display: false }, ticks: { callback: tick, maxTicksLimit: 6 } }, y: { title: { display: true, text: "kWh/t not explained by practice" } } } } });
    const sel = document.getElementById("hsel");
    const draw = () => {
      document.getElementById("hdl").textContent = hDay;
      const rows = hs.filter(h => h.day === hDay);
      document.getElementById("htab").innerHTML = `<thead><tr><th>Heat</th><th>Start</th><th class="num">kWh</th><th class="num">Melt kWh/t</th><th class="num">Unexplained</th><th class="num">Score</th></tr></thead><tbody>${rows.map(h => `<tr><td>${h.heat_no}</td><td>${hhmm(h.start_h)}</td><td class="num">${inr(h.furnace_kwh)}</td><td class="num">${inr(h.melt_sec)}</td><td class="num">${h.drift_resid.toFixed(1)}</td><td class="num">${h.cusum > th ? `<span class="chip bad">${h.cusum.toFixed(1)}</span>` : h.cusum.toFixed(1)}</td></tr>`).join("")}</tbody>`;
    };
    sel.onchange = () => { hDay = +sel.value; draw(); }; draw();
  };

  let mView = "improved";
  V.machines = () => {
    const t = D.traces[mView], loads = D.nilm.loads, T1 = D.nilm.tests.days_5_7, T2 = D.nilm.tests.days_80_82;
    const tierChip = x => `<span class="chip ${x === "High" ? "ok" : x === "Medium" ? "warn" : "bad"}">${x}</span>`;
    app.innerHTML = `
    <section class="view">
      <div><h1>Machine-level energy from three meters</h1>
      <p class="lede">The furnace and the compressor have their own meters. The rest of the load (pump, fume fans, sand mixer, shot blast, grinders, lights) is split by a machine-learning model plus two physics rules from commissioning: the cooling pump runs only while the furnace is energised or for 20 minutes after, and the fume fans run only while melting. The model learned from a ${D.nilm.train_days[1]}-day clamp-on survey and was refreshed with one more clamp-on day when the melt schedule changed (day ${C.nilm_relabel_day}).</p></div>
      <div class="panel controls" role="group" aria-label="Sample day"><button class="btn" id="mb" type="button" aria-pressed="${mView === "baseline"}">Day ${D.traces.baseline.day}: baseline schedule</button><button class="btn" id="mi" type="button" aria-pressed="${mView === "improved"}">Day ${D.traces.improved.day}: Time-of-Day schedule</button></div>
      <div class="panel" id="stack">${badge("sim")}<h2>Whole plant, minute by minute, day ${t.day}</h2>
        <div class="legend"><span><i style="background:${css("--accent")}"></i>Furnace (metered)</span><span><i style="background:#56635F"></i>Compressor (metered)</span><span><i class="hatch"></i>Hatched: AI estimate</span><span><i style="background:${css("--band-solar")};outline:1px solid ${css("--warn")}"></i>Solar hours</span><span><i style="background:${css("--band-peak")};outline:1px solid ${css("--bad")}"></i>Peak hours</span></div>
        <div class="chart tall"><canvas id="c5" role="img" aria-label="Stacked plant load for day ${t.day}"></canvas></div></div>
      <div class="panel">${badge("sim")}<h2>Accuracy on days the model never saw</h2><div class="tablewrap"><table class="wraphead">
        <thead><tr><th>Machine</th><th class="num">Energy error, days 5 to 7</th><th class="num">Energy error, days 80 to 82 (after re-label)</th><th class="num">On/off F1, AI</th><th class="num">On/off F1, simple share model</th><th>Confidence, days 80 to 82</th></tr></thead>
        <tbody>${loads.map((k, i) => `<tr><td>${LOADS[k]}</td><td class="num">${(T1[i].sae * 100).toFixed(1)}%</td><td class="num">${(T2[i].sae * 100).toFixed(1)}%</td><td class="num">${T2[i].f1_on_off.toFixed(2)}</td><td class="num">${T2[i].naive_f1.toFixed(2)}</td><td>${tierChip(T2[i].tier)}</td></tr>`).join("")}</tbody></table></div>
        <p class="note">Energy error is the gap between estimated and true energy over the window. Days 5 to 7 have the same schedule as training. By days 80 to 82 the melt schedule had moved to the Time-of-Day plan. Repeated over ${D.nilm.seeds.seeds.length} independent simulated runs: average error ${(NS.days_5_7.mean_sae_median * 100).toFixed(1)}% on days 5 to 7; on days 80 to 82, ${(NS.days_80_82_no_relabel.mean_sae_median * 100).toFixed(1)}% without the one-day re-label and ${(NS.days_80_82.mean_sae_median * 100).toFixed(1)}% with it, against ${(NS.days_80_82.mean_sae_naive_median * 100).toFixed(1)}% for a simple fixed-share split. So on daily kWh the two are close; in the simulation the model's edge is knowing when each machine runs (on/off F1 ${NS.days_80_82.mean_f1.toFixed(2)} against ${NS.days_80_82.mean_f1_naive.toFixed(2)}). On the real factory below, that edge did not carry over. Field accuracy will be lower, so the product shows a confidence tier per machine and targets plus or minus 10 to 15% per auxiliary.</p></div>
      ${realPanel()}
    </section>`;
    document.getElementById("mb").onclick = () => { mView = "baseline"; V.machines(); };
    document.getElementById("mi").onclick = () => { mView = "improved"; V.machines(); };
    const mins = t.mains.map((_, i) => i / 60);
    const pal = ["#2F7F6F", "#7E9C96", "#B7811F", "#8C5A9E", "#4F86A8", "#9AA5A2"];
    const ds = [
      { label: "Furnace (metered)", data: t.furnace, backgroundColor: css("--accent"), borderWidth: 0, fill: true, pointRadius: 0 },
      { label: "Compressor (metered)", data: t.compressor, backgroundColor: "#56635F", borderWidth: 0, fill: true, pointRadius: 0 },
      ...loads.map((k, i) => ({ label: LOADS[k] + " (AI estimate)", data: t.nilm[k], backgroundColor: hatch(pal[i]), borderColor: pal[i], borderWidth: 0.5, fill: true, pointRadius: 0 }))];
    const tb = D.tariffs[C.base_state].bands.map(b => ({ from: b.start, to: b.end, color: b.label === "peak" ? css("--band-peak") : css("--band-solar") }));
    mk("c5", { type: "line", data: { labels: mins, datasets: ds },
      options: { interaction: { mode: "index", intersect: false }, plugins: { legend: { display: false }, tooltip: { callbacks: { title: i => hhmm(i[0].label), label: i => `${i.dataset.label}: ${i.raw.toFixed(1)} kW` } } },
        scales: { x: { type: "linear", min: 0, max: 24, ticks: { stepSize: 2, callback: v => `${v}:00` }, grid: { display: false } }, y: { stacked: true, title: { display: true, text: "kW" } } } },
      plugins: [bands(tb)] });
  };

  function realPanel() {
    const RD = window.URJA_REAL;
    if (!RD) return "";
    const pr = v => `${(v * 100).toFixed(1)}%`;
    const tierChip = x => `<span class="chip ${x === "High" ? "ok" : x === "Medium" ? "warn" : "bad"}">${x}</span>`;
    const tag = { A_hybrid: "A", B_unmetered: "B", C_milling: "C" };
    const rows = RD.tests.flatMap(t => t.per_load.map(p => ({ t, p })));
    const nHigh = rows.filter(r => r.p.tier === "High").length;
    const A = RD.tests[0], A0 = RD.first_run[0], ef = A.per_load.find(p => p.load === "exhaustfan-II"), ef0 = A0.per_load.find(p => p.load === "exhaustfan-II");
    const dpc = A.per_load.find(p => p.load === "doublepolecontactor-II");
    const f1min = Math.min(...rows.map(r => r.p.naive_f1_all));
    return `<div class="panel" id="realdata">${badge("real")}<h2>Tested on real factory data</h2>
      <p class="note" style="margin-top:0">${esc(RD.dataset)}. ${esc(RD.source)}. Same model and protocol as above: learn from ${RD.train_days} labelled days, then measure the energy error week by week on days the model never saw, against the simple fixed-share split. ${nHigh} of ${rows.length} machine estimates reached High confidence.</p>
      <div class="tablewrap"><table class="wraphead"><thead><tr><th>Test</th><th>Machine</th><th class="num">Weekly energy error, UrjaKhata (median, worst)</th><th class="num">Simple split</th><th class="num">On/off F1, UrjaKhata vs simple</th><th>Confidence</th></tr></thead><tbody>
      ${rows.map(({ t, p }) => `<tr><td>${tag[t.name]}</td><td>${esc(p.name)}</td><td class="num">${pr(p.sae_week_median)}, ${pr(p.sae_week_worst)}</td><td class="num">${pr(p.naive_sae_week_median)}</td><td class="num">${p.f1_all.toFixed(2)} vs ${p.naive_f1_all.toFixed(2)}</td><td>${tierChip(p.tier)}</td></tr>`).join("")}
      </tbody></table></div>
      <p class="note">${RD.tests.map(t => `<b>${tag[t.name]}:</b> ${esc(t.title)}, ${t.total_days} complete days (${t.test_days} unseen). ${esc(t.note)}`).join(" ")}</p>
      <h3 style="margin-top:14px">What the real data taught us</h3>
      <ul class="lessons">
        <li><b>A flaw the simulation could not show, now fixed.</b> The model's energy-balance step assumed every machine in the leftover was labelled. Here two were not, so the exhaust fan came out ${pr(ef0.sae_week_median)} too high. An explicit "other, unlabelled" bucket brought it to ${pr(ef.sae_week_median)}.</li>
        <li><b>Look-alike machines need labels.</b> Contactor II has an identical twin in the same leftover that was not labelled, so no method can separate them (UrjaKhata ${pr(dpc.sae_week_median)}, simple split ${pr(dpc.naive_sae_week_median)}). The confidence tier flags it Low. Commissioning rule: clamp every machine in the leftover, or report look-alikes as one group.</li>
        <li><b>The simulation's timing advantage did not carry over.</b> Machines on these circuits start and stop together, so the simple split gets on/off timing right too (F1 ${f1min.toFixed(2)} or better). On energy, the model was slightly better on the unmetered circuits.</li>
        <li><b>Limits.</b> Only complete days are used; the milling test has ${RD.tests[2].test_days} unseen days, so treat it as indicative.</li>
      </ul></div>`;
  }

  let pState = C.base_state;
  V.planner = () => {
    const st = D.tod.states[pState], tf = D.tariffs[pState];
    const nPlan = "10", plan = st.plans[nPlan];
    const rates = tf.hourly, rmin = Math.min(...rates), rmax = Math.max(...rates);
    const col = r => { const f = (r - rmin) / Math.max(rmax - rmin, 1e-6); return f > 0.66 ? "rgba(179,38,30,.55)" : f < 0.2 ? "rgba(61,205,88,.55)" : "rgba(242,179,61,.45)"; };
    const isPeak = h => tf.bands.some(b => b.label === "peak" && h >= b.start && h < b.end);
    const track = heats => `<div class="gtrack">${tf.bands.map(b => `<div class="band" style="left:${b.start / 24 * 100}%;width:${(b.end - b.start) / 24 * 100}%;background:${b.label === "peak" ? css("--band-peak") : css("--band-solar")}"></div>`).join("")}${heats.map(h => {
      const pk = tf.bands.some(b => b.label === "peak" && h.s < b.end && h.e > b.start);
      return `<div class="heat ${pk ? "inpeak" : ""}" style="left:${h.s / 24 * 100}%;width:${(h.e - h.s) / 24 * 100}%" title="Heat ${h.n}: ${hhmm(h.s)} to ${hhmm(h.e)}${pk ? " (touches peak)" : ""}">${h.n}</div>`; }).join("")}</div>`;
    const hours = `<div class="hours">${[0, 3, 6, 9, 12, 15, 18, 21, 24].map(h => `<span style="left:${h / 24 * 100}%;transform:translateX(${h === 0 ? "0" : h === 24 ? "-100%" : "-50%"})">${h}:00</span>`).join("")}</div>`;
    const habit = Array.from({ length: 10 }, (_, i) => { const s = C.baseline_first_heat + i * st.heat_minutes / 60; return { s, e: s + st.heat_minutes / 60 - 10 / 60, n: i + 1 }; });
    const opt = plan.start_hours.map((s, i) => ({ s, e: s + st.heat_minutes / 60 - 10 / 60, n: i + 1 }));
    const actual = D.heats.filter(h => h.day === D.traces.improved.day).map(h => ({ s: h.start_h, e: h.end_h, n: h.heat_no }));
    app.innerHTML = `
    <section class="view">
      <div><h1>Time-of-Day melt planner on real tariffs</h1>
      <p class="lede">Melting is the biggest load, and it can move. A mixed-integer optimiser (SciPy HiGHS) places each day's heats into the cheapest hours with one furnace, the moulding crew's shifts (${hhmm(C.crew_window[0])} to ${hhmm(C.crew_window[1])}, at most ${C.max_heats_per_shift} heats per shift) and the same number of heats. Rates include energy charge, ToU adder${pState === "GJ" ? ", fuel surcharge (FPPAS) and 15% electricity duty" : " and tax where known"}.</p></div>
      <div class="panel controls" role="group" aria-label="State tariff">${Object.keys(D.tariffs).map(s => `<button class="btn" type="button" data-st="${s}" aria-pressed="${s === pState}">${esc(D.tariffs[s].short)}</button>`).join("")}</div>
      <div class="kpis">
        <div class="kpi"><div class="lab">Worth per year, timing only</div><div class="val">Rs ${lakh(st.annual_rs)} <small>lakh</small></div><div class="from">same heats, same energy, cheaper hours (${C.operating_days} days)</div></div>
        <div class="kpi"><div class="lab">Rate spread</div><div class="val">Rs ${(tf.max - tf.min).toFixed(2)} <small>per kWh</small></div><div class="from">Rs ${tf.min.toFixed(2)} cheapest to Rs ${tf.max.toFixed(2)} dearest</div></div>
        ${pState === "GJ" ? `<div class="kpi"><div class="lab">Energy in peak hours (simulated plant)</div><div class="val">${(S1.peak_share * 100).toFixed(0)}%</div><div class="from">was ${(B0.peak_share * 100).toFixed(0)}% with the habitual 08:00 start</div></div>` : `<div class="kpi"><div class="lab">Data confidence</div><div class="val" style="font-size:20px">Sensitivity case</div><div class="from">${esc(tf.confidence)}</div></div>`}
      </div>
      <div class="panel" id="gantt">${badge(pState === "GJ" ? "src" : "asm")}<h2>${esc(tf.name)}: effective rate by hour</h2>
        <div class="ratestrip">${rates.map((r, h) => `<div style="background:${col(r)}" title="${h}:00 Rs ${r.toFixed(2)}/kWh">${r.toFixed(1)}</div>`).join("")}</div>${hours}
        <div class="gantt" style="margin-top:14px">
          <div class="rowlab">Habitual: 10 heats from ${hhmm(C.baseline_first_heat)}, back to back <span>furnace cost Rs ${inr(plan.habitual_cost_rs)} a day</span></div>${track(habit)}
          <div class="rowlab">Optimised plan, 10 heats <span>furnace cost Rs ${inr(plan.plan_cost_rs)} a day</span></div>${track(opt)}
          ${pState === "GJ" ? `<div class="rowlab">Day ${D.traces.improved.day}: what the plant actually ran <span>real heat lengths</span></div>${track(actual)}` : ""}
          ${hours}
        </div>
        <p class="note">Shaded: solar-hour discount (amber) and peak hours (red). Striped red heats touch a peak. Source: ${esc(tf.source)}.</p></div>
      <div class="grid g2">
        <div class="panel"><h2>Constraints the plan respects</h2><div class="tablewrap"><table><tbody>
          <tr><td>Single furnace</td><td>Heats never overlap; each includes tapping and a 10-minute recharge</td></tr>
          <tr><td>Moulding line staffed</td><td>Melting and pouring only from ${hhmm(C.crew_window[0])} to ${hhmm(C.crew_window[1])}</td></tr>
          <tr><td>Crew per shift</td><td>At most ${C.max_heats_per_shift} heats in shift A (06 to 14) and in shift B (14 to 23): ${Object.entries(D.tod.shifts_check).map(([n, v]) => `${n} heats: ${v.per_shift.join(" + ")} ${v.ok ? "ok" : "over"}`).join("; ")}</td></tr>
          <tr><td>Output</td><td>Same number of heats every day as without the plan</td></tr>
          <tr><td>Contract demand</td><td>One furnace at ${C.rated_kw} kW plus auxiliaries stays under the ${tf.demand.contract_kva} kVA contract demand</td></tr>
        </tbody></table></div></div>
        <div class="panel"><h2>All three states</h2><div class="tablewrap"><table>
          <thead><tr><th>State and DISCOM</th><th class="num">Cheapest</th><th class="num">Dearest</th><th class="num">Timing value a year</th></tr></thead>
          <tbody>${Object.keys(D.tariffs).map(s => `<tr><td>${esc(D.tariffs[s].short)}</td><td class="num">Rs ${D.tariffs[s].min.toFixed(2)}</td><td class="num">Rs ${D.tariffs[s].max.toFixed(2)}</td><td class="num">Rs ${lakh(D.tod.states[s].annual_rs)} lakh</td></tr>`).join("")}</tbody></table></div>
          <p class="note">Value depends on how far the habitual schedule sits in the peaks. Maharashtra and Tamil Nadu are sensitivity cases: their FY 2026-27 figures need confirming.</p></div>
      </div>
    </section>`;
    app.querySelectorAll("[data-st]").forEach(b => b.onclick = () => { pState = b.dataset.st; V.planner(); });
  };

  let pigShare = null, pigEf = null;
  V.carbon = () => {
    const p = D.carbon.passport, c0 = D.carbon.baseline, c1 = D.carbon.current;
    if (pigShare === null) pigShare = +(c1.pig_iron_share * 100).toFixed(1);
    if (pigEf === null) pigEf = C.pig_iron_ef;
    const liqPerGood = c1.liquid_t / c1.good_t;
    const calc = () => { const prec = pigShare / 100 * liqPerGood * pigEf; return { prec, tot: prec + c1.direct_tco2_per_t }; };
    app.innerHTML = `
    <section class="view">
      <div><h1>Carbon passport: two boundaries, kept apart</h1>
      <p class="lede">For iron and steel goods, the EU CBAM prices direct emissions plus those embedded in purchased precursors such as pig iron. Electricity emissions are reported but not priced. So electricity savings cut the Scope 2 footprint and India's carbon-market view, while the CBAM figure is set by fuel burnt on site and the charge mix. The ledger proves both from meters and heat logs, so an importer can replace the EU default values (marked up 10% in 2026, 20% in 2027, 30% from 2028) with verified actuals.</p></div>
      <div class="split" id="boundaries">
        <div class="priced"><span>CBAM embedded emissions (priced)</span><b>${c1.cbam_embedded_tco2_per_t.toFixed(3)}</b><span>tCO2 per tonne of castings: direct ${c1.direct_tco2_per_t.toFixed(3)} + precursor ${c1.precursor_tco2_per_t.toFixed(3)}</span></div>
        <div><span>Indirect, electricity (reported, not priced)</span><b>${c1.indirect_tco2_per_t.toFixed(3)}</b><span>was ${c0.indirect_tco2_per_t.toFixed(3)} <span class="delta good">${pct(100 * (c1.indirect_tco2_per_t / c0.indirect_tco2_per_t - 1))}</span></span></div>
        <div><span>Scope 1 + 2 footprint, CEA ${C.grid_ef}</span><b>${c1.scope12_tco2_per_t.toFixed(3)}</b><span>was ${c0.scope12_tco2_per_t.toFixed(3)} <span class="delta good">${pct(100 * (c1.scope12_tco2_per_t / c0.scope12_tco2_per_t - 1))}</span></span></div>
        <div><span>Scope 1 + 2 at CCTS factor ${C.grid_ef_ccts}</span><b>${c1.scope12_ccts_tco2_per_t.toFixed(3)}</b><span>was ${c0.scope12_ccts_tco2_per_t.toFixed(3)}</span></div>
      </div>
      <div class="grid g3">
        <article class="passport" id="passport" aria-label="Carbon passport">
          <div class="pp-head"><h2>Passport ${esc(p.passport_id)}</h2><span class="note">Shipment ${esc(p.shipment_id)}: ${p.quantity_t} t</span></div>
          <dl class="pp-grid">
            <div><dt>Installation</dt><dd>${esc(p.installation)}</dd></div>
            <div><dt>Product and CN code</dt><dd>${esc(p.product)}; ${esc(p.cn_code)}</dd></div>
            <div><dt>Production route</dt><dd>${esc(p.production_route)}</dd></div>
            <div><dt>Monitoring period</dt><dd>Operating days ${p.monitoring_period_days[0]} to ${p.monitoring_period_days[1]}</dd></div>
            <div><dt>Charge mix</dt><dd>Pig iron ${(p.charge_mix.pig_iron * 100).toFixed(0)}%, steel scrap ${(p.charge_mix.steel_scrap * 100).toFixed(0)}%, own returns ${(p.charge_mix.returns * 100).toFixed(0)}%</dd></div>
            <div><dt>Embedded (CBAM boundary)</dt><dd><b>${p.specific_embedded_cbam_tco2_per_t.toFixed(3)} tCO2/t</b>; this shipment ${p.embedded_cbam_tco2.toFixed(2)} tCO2</dd></div>
            <div><dt>Indirect, reported only</dt><dd>${p.indirect_reported_tco2_per_t.toFixed(3)} tCO2/t; ${p.electricity_mwh_per_t.toFixed(3)} MWh/t</dd></div>
            <div><dt>Factors</dt><dd>${esc(p.factors)}</dd></div>
            <div><dt>Evidence trail</dt><dd>${p.evidence.map(esc).join("; ")}</dd></div>
          </dl>
          <div class="stamp">${esc(p.status)} ${esc(p.cbam_note)}</div>
        </article>
        <div class="panel">${badge("asm")}<h2>What moves the CBAM number</h2>
          <p class="note" style="margin-top:0">Pig iron carries blast-furnace emissions; steel scrap carries none. Try the charge mix.</p>
          <div class="grid" style="gap:12px;margin-top:10px">
            <label class="sl" for="pig">Pig iron share of charge <b id="pigv"></b><input type="range" id="pig" min="0" max="35" step="0.5" value="${pigShare}"></label>
            <label class="sl" for="pef">Pig iron embedded emissions, tCO2/t <b id="pefv"></b><input type="range" id="pef" min="1.4" max="2.4" step="0.05" value="${pigEf}"></label>
          </div>
          <div class="mini" style="margin-top:14px"><div><b id="cbamv"></b>tCO2 per tonne of castings, CBAM boundary</div><div><b id="shipv"></b>tCO2 for the ${p.quantity_t} t shipment</div></div>
          <p class="note">Scale check, not a castings value: India's EU default for hot-rolled steel (CN 7208) is 4.28 tCO2/t before mark-ups (GreenSutra, citing IR (EU) 2025/2621). Defaults for CN 7326 differ; read the current table in IR (EU) 2026/1740.</p></div>
      </div>
    </section>`;
    const upd = () => {
      const r = calc(); document.getElementById("pigv").textContent = `${pigShare.toFixed(1)}%`; document.getElementById("pefv").textContent = pigEf.toFixed(2);
      document.getElementById("cbamv").textContent = r.tot.toFixed(3); document.getElementById("shipv").textContent = (r.tot * p.quantity_t).toFixed(2);
    };
    document.getElementById("pig").oninput = e => { pigShare = +e.target.value; upd(); };
    document.getElementById("pef").oninput = e => { pigEf = +e.target.value; upd(); };
    upd();
  };

  V.proof = () => {
    const B = D.mv.option_b, Cm = D.mv.option_c;
    const card = (x, title, head) => `<div class="panel">${badge("sim")}<h2>${title}</h2><p class="note" style="margin-top:0">${esc(x.method)}</p><dl class="kv">
      <dt>Baseline model</dt><dd><code>${esc(x.model)}</code></dd>
      <dt>Points</dt><dd>${x.baseline_points} baseline, ${x.reporting_points} reporting</dd>
      <dt>Model fit, CV(RMSE)</dt><dd>${(x.cv_rmse * 100).toFixed(1)}%</dd>
      <dt>Adjusted baseline</dt><dd>${inr(x.adjusted_baseline_kwh)} kWh</dd>
      <dt>Actual, metered</dt><dd>${inr(x.actual_kwh)} kWh</dd>
      <dt>Verified saving</dt><dd><b>${inr(x.savings_kwh)} kWh (${(x.savings_pct * 100).toFixed(1)}%)</b></dd>
      <dt>90% confidence</dt><dd>${inr(x.savings_low_kwh)} to ${inr(x.savings_high_kwh)} kWh (ASHRAE Guideline 14 ${x.ashrae_ok ? "test passed" : "test not passed"})</dd></dl>${head ? "" : '<p class="note">Indicative: over 60 days whole-facility savings near 8% are hard to separate from noise at a real site.</p>'}</div>`;
    const rep = D.daily.filter(d => d.day > C.baseline_days);
    app.innerHTML = `
    <section class="view">
      <div><h1>Savings proof a lender can use</h1><p class="lede">ADEETIE (5% interest subvention for micro and small units, with post-implementation M&amp;V), SIDBI 4E and ESCOs need a baseline and verified savings. The ledger fits a model on the ${C.baseline_days}-day baseline, adjusts it to each reporting day's output and reports the gap with an uncertainty band, following IPMVP and ASHRAE Guideline 14.</p></div>
      <div class="grid g2" id="mvcards">${card(B, "Headline: furnace sub-meter (Option B)", true)}${card(Cm, "Whole plant (Option C)", false)}</div>
      <div class="panel" id="mvchart">${badge("sim")}<h2>Whole plant: verified savings building up</h2>
        <div class="legend"><span><i style="background:${css("--good")}"></i>Adjusted baseline minus metered use, added day by day</span><span><i style="background:${css("--tint")};outline:1px solid ${css("--line")}"></i>90% band</span></div>
        <div class="chart"><canvas id="c7" role="img" aria-label="Cumulative verified savings rising over the reporting period"></canvas></div></div>
      <div class="panel"><h2>What sits behind the saving</h2><div class="tablewrap"><table>
        <thead><tr><th>Practice</th><th class="num">Baseline</th><th class="num">With UrjaKhata</th><th>Measured by</th></tr></thead><tbody>
        <tr><td>Holding after melt-down</td><td class="num">${B0.hold_min.toFixed(1)} min</td><td class="num">${S1.hold_min.toFixed(1)} min</td><td>Furnace power profile</td></tr>
        <tr><td>Superheat above target</td><td class="num">${B0.superheat_c.toFixed(1)} C</td><td class="num">${S1.superheat_c.toFixed(1)} C</td><td>Pyrometer reading in the heat log</td></tr>
        <tr><td>Slag</td><td class="num">${B0.slag_pct.toFixed(2)}%</td><td class="num">${S1.slag_pct.toFixed(2)}%</td><td>Heat log</td></tr>
        <tr><td>Lid open while melting</td><td class="num">${(B0.lid_open * 100).toFixed(0)}%</td><td class="num">${(S1.lid_open * 100).toFixed(0)}%</td><td>Not metered: supervisor checklist (simulated)</td></tr>
        <tr><td>Compressor energy</td><td class="num">${inr(B0.compressor_kwh_per_day)} kWh/day</td><td class="num">${inr(S1.compressor_kwh_per_day)} kWh/day</td><td>Compressor sub-meter</td></tr>
        <tr><td>Liquid metal</td><td class="num">${B0.liquid_t_per_day.toFixed(2)} t/day</td><td class="num">${S1.liquid_t_per_day.toFixed(2)} t/day</td><td>Charge log: output held</td></tr>
        <tr><td>Casting rejects</td><td class="num">${(B0.reject_rate * 100).toFixed(1)}%</td><td class="num">${(S1.reject_rate * 100).toFixed(1)}%</td><td>Fettling log: quality held</td></tr>
        </tbody></table></div><p class="note">Bands are narrow because the simulation's noise is modest. A real site will show wider bands, which is why the pilot keeps a 4-week baseline and a reporting period of at least 60 days.</p></div>
    </section>`;
    let cum = 0, k = 0;
    const cumS = rep.map(d => (cum += d.adjusted_baseline_kwh - d.plant_kwh));
    const unc = rep.map(() => { k += 1; return Cm.daily_band_kwh * Math.sqrt(k); });
    mk("c7", { type: "line", data: { labels: rep.map(d => d.day), datasets: [
        { data: cumS.map((v, i) => v + unc[i]), borderWidth: 0, pointRadius: 0, fill: "+1", backgroundColor: css("--line"), order: 3 },
        { data: cumS.map((v, i) => Math.max(0, v - unc[i])), borderWidth: 0, pointRadius: 0, fill: false, order: 2 },
        { data: cumS, borderColor: css("--good"), borderWidth: 2.5, pointRadius: 0, order: 1 }] },
      options: { plugins: { legend: { display: false }, tooltip: { filter: i => i.datasetIndex === 2, callbacks: { title: i => `Day ${i[0].label}`, label: i => `Verified saving so far: ${inr(i.raw)} kWh` } } },
        scales: { x: { grid: { display: false }, title: { display: true, text: "Operating day" }, ticks: { maxTicksLimit: 12 } }, y: { min: 0, title: { display: true, text: "Cumulative kWh saved" } } } } });
  };

  V.stress = () => {
    const S = RB.savings, P = S.percentiles, st = S.stress_case, ad = RB.adherence, dr = RB.drift.scenarios, sw = RB.drift_sweep;
    const z = ad[0], kit = H.kit_rs;
    const NAMES = { practice_adherence: "Share of the practice advice operators follow", compressor_realised: "Share of the compressed-air saving realised",
      tariff_level: "Tariff level (fuel surcharge and duty move)", tod_days_followed: "Days the melt plan is followed", furnace_eff: "Furnace efficiency assumption (65 to 75%)" };
    const R = S.ranges;
    const rng = k => k === "furnace_eff" ? `${(R[k][0] * 100).toFixed(0)} to ${(R[k][1] * 100).toFixed(0)}%` : k === "tariff_level" ? `${R[k][0]} to ${R[k][1]}x` : `${(R[k][0] * 100).toFixed(0)} to ${(R[k][1] * 100).toFixed(0)}%`;
    const drivers = Object.entries(S.drivers).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
    const ns = D.nilm.seeds.tests, pctx = v => (v * 100).toFixed(0) + "%";
    const fm = RB.fast_model_check;
    app.innerHTML = `
    <section class="view">
      <div><h1>Stress tests: does it hold up when things go wrong?</h1>
      <p class="lede">The 90-day run is one scenario in which operators adopt all the advice. Here the same equations run ${inr(S.n)} times with the inputs we are least sure of, the drift alarm is tested on ${RB.drift.runs} simulated plant-months per case, and each model is compared with the simplest thing that could replace it.</p></div>
      <div class="kpis">
        <div class="kpi"><div class="lab">Saved per year, typical case (P50)</div><div class="val">Rs ${lakh(P.rs.p50)} <small>lakh</small></div>
          <div class="from">P10 to P90: Rs ${lakh(P.rs.p10)} to ${lakh(P.rs.p90)} lakh across ${inr(S.n)} runs</div>
          <div class="band">Full-adoption scenario: Rs ${lakh(H.annual_rs_headline)} lakh</div></div>
        <div class="kpi"><div class="lab">Payback, typical case</div><div class="val">${P.payback_months.p50.toFixed(1)} <small>months</small></div>
          <div class="from">P90 ${P.payback_months.p90.toFixed(1)} months; ${pctx(S.share_payback_under_6m)} of runs pay back within 6 months</div>
          <div class="band">Stress case, every input at its worst: ${st.payback_months.toFixed(1)} months</div></div>
        <div class="kpi"><div class="lab">Drift alarm, false alarms</div><div class="val">${pctx(dr.no_fault.residual.alarm_share)} <small>of months</small></div>
          <div class="from">Catches 2%, 5% and 10% faults in ${pctx(dr.fault_2pct.residual.detect_share)} of runs: median ${dr.fault_2pct.residual.delay_heats_p50}, ${dr.fault_5pct.residual.delay_heats_p50} and ${dr.fault_10pct.residual.delay_heats_p50} heats</div>
          <div class="band">At the first threshold (6) it was ${pctx(sw.find(r => r.h === 6).false_alarm_month)}</div></div>
      </div>
      <div class="grid g3">
        <div class="panel" id="adh">${badge("sim")}<h2>Savings against how much advice operators follow</h2>
          <div class="legend"><span><i style="background:${css("--good")}"></i>Typical (P50)</span><span><i style="background:${css("--tint")};outline:1px solid ${css("--line")}"></i>P10 to P90</span><span><i style="background:${css("--bad")}"></i>Needed for a 12-month payback on the dearest kit</span></div>
          <div class="chart"><canvas id="c8" role="img" aria-label="Annual savings rising with operator adherence, always above the 12-month payback line"></canvas></div>
          <p class="note">At 0%, with no change in melting practice at all, the compressed-air fix and melt timing still save Rs ${lakh(z.rs_p50)} lakh a year (payback ${z.payback_p50.toFixed(1)} months). Each point samples the other inputs ${inr(200)} times.</p></div>
        <div class="panel">${badge("sim")}<h2>What moves the rupees</h2>
          <div class="bars">${drivers.map(([k, v]) => `<div class="brow"><div class="bl">${esc(NAMES[k])}<small>range tested: ${rng(k)}</small></div><div class="bt"><i style="width:${Math.abs(v) * 100}%"></i></div><div class="bv">${v.toFixed(2)}</div></div>`).join("")}</div>
          <p class="note">Rank correlation with annual savings across the ${inr(S.n)} runs. Savings depend on operators acting, not on the furnace efficiency assumption, which is why the product is built around a daily briefing.</p></div>
      </div>
      <div class="grid g2">
        <div class="panel">${badge("sim")}<h2>Choosing the drift alarm threshold</h2><div class="tablewrap"><table class="wraphead">
          <thead><tr><th class="num">Threshold</th><th class="num">Months with a false alarm</th><th class="num">Blames equipment for operator slips</th><th class="num">Heats to catch a 2%, 5%, 10% fault</th></tr></thead>
          <tbody>${sw.map(r => `<tr class="${r.h === C.cusum_h ? "sel" : ""}"><td class="num">${r.h}${r.h === C.cusum_h ? " (used)" : ""}</td><td class="num">${pctx(r.false_alarm_month)}</td><td class="num">${pctx(r.slip_alarm)}</td><td class="num">${r.delay_2}, ${r.delay_5}, ${r.delay_10}</td></tr>`).join("")}</tbody></table></div>
          <p class="note">Each row: ${RB.drift.runs} simulated plant-months per case, ${RB.drift.ref_days} reference days, faults ramping in over ${RB.drift.ramp_days} days. Raising the threshold from 6 to ${C.cusum_h} cut false alarms sharply for a few heats of extra delay.</p></div>
        <div class="panel"><h2>Inputs sampled in the savings runs</h2><div class="tablewrap"><table><thead><tr><th>Input</th><th>Range</th></tr></thead><tbody>
          ${Object.keys(NAMES).map(k => `<tr><td>${esc(NAMES[k])}</td><td>${rng(k)}</td></tr>`).join("")}
          <tr><td>Kit cost and subscription</td><td>Rs ${inr(R.kit_rs[0])} to ${inr(R.kit_rs[1])}; Rs ${inr(R.subscription_rs_month[0])} to ${inr(R.subscription_rs_month[1])} a month</td></tr></tbody></table></div>
          <p class="note">The fast model behind these runs reproduces the full simulator: baseline ${fm.fast.sec_baseline.toFixed(1)} against ${fm.sim.sec_baseline.toFixed(1)} kWh/t, improved ${fm.fast.sec_improved.toFixed(1)} against ${fm.sim.sec_improved.toFixed(1)} kWh/t. Ranges are set in <code>engine/robustness.py</code>.</p></div>
      </div>
      <div class="panel" id="ablation"><h2>Each model against the simplest alternative</h2><div class="tablewrap"><table>
        <thead><tr><th>Part</th><th>Simplest alternative</th><th>UrjaKhata</th><th>What we conclude</th></tr></thead><tbody>
        <tr><td>Machine split, after a schedule change (median of ${D.nilm.seeds.seeds.length} runs)</td><td>Fixed share of the leftover load: energy error ${(ns.days_80_82.mean_sae_naive_median * 100).toFixed(1)}%, on/off F1 ${ns.days_80_82.mean_f1_naive.toFixed(2)}</td><td>Energy error ${(ns.days_80_82.mean_sae_median * 100).toFixed(1)}%, on/off F1 ${ns.days_80_82.mean_f1.toFixed(2)}</td><td>Close on daily kWh; the model is needed to know when each machine runs. Without the one-day re-label its error rises to ${(ns.days_80_82_no_relabel.mean_sae_median * 100).toFixed(1)}%, so re-labelling is part of the product.</td></tr>
        ${window.URJA_REAL ? (() => { const RT = window.URJA_REAL.tests, B = RT[1], Cc = RT[2], all = RT.flatMap(t => t.per_load), nH = all.filter(p => p.tier === "High").length;
          return `<tr><td>Machine split on a real factory (IMDELD)</td><td>Fixed share, unmetered circuits: ${(B.weighted_naive_sae_week_median * 100).toFixed(1)}% and ${(Cc.weighted_naive_sae_week_median * 100).toFixed(1)}% weekly energy error</td><td>${(B.weighted_sae_week_median * 100).toFixed(1)}% and ${(Cc.weighted_sae_week_median * 100).toFixed(1)}%; ${nH} of ${all.length} machine estimates High confidence</td><td>Slightly better than the simple split on energy, equal on timing. Fails on a look-alike machine without labels, and says so (Low). See Machines.</td></tr>`; })() : ""}
        <tr><td>Drift alarm</td><td>CUSUM on raw kWh/t: false alarms ${pctx(dr.no_fault.raw.alarm_share)} of months; blames equipment for operator slips in ${pctx(dr.practice_slip.raw.alarm_share)} of cases; 5% fault caught in ${dr.fault_5pct.raw.delay_heats_p50} heats</td><td>${pctx(dr.no_fault.residual.alarm_share)}; ${pctx(dr.practice_slip.residual.alarm_share)}; ${dr.fault_5pct.residual.delay_heats_p50} heats</td><td>Same speed. Ours separates operator slips (sent to the briefing as practice actions) from equipment wear (sent to maintenance).</td></tr>
        <tr><td>Melt timing</td><td>Habitual 08:00 start: ${(B0.peak_share * 100).toFixed(0)}% of plant energy in peak hours</td><td>${(S1.peak_share * 100).toFixed(0)}% in peak hours; Rs ${lakh(H.tod_isolated_annual_rs)} lakh a year from timing alone</td><td>Real value on the PGVCL tariff; the optimiser also guarantees the shift and moulding-line limits.</td></tr>
        <tr><td>Savings figure</td><td>One 90-day run: Rs ${lakh(H.annual_rs_headline)} lakh, assuming full adoption</td><td>${inr(S.n)} runs: Rs ${lakh(P.rs.p10)} to ${lakh(P.rs.p90)} lakh, typical ${lakh(P.rs.p50)}</td><td>We quote the range. Even the stress case (Rs ${lakh(st.rs)} lakh) pays back in under a year.</td></tr>
        </tbody></table></div>
        <p class="note">All rows except the real-factory row run on simulated plants. Next: pilot data from Rajkot foundries.</p></div>
    </section>`;
    const labels = ad.map(r => `${Math.round(r.adherence * 100)}%`);
    const L = v => v / 1e5;
    const needRs = (kit[1] + 12 * RB.savings.ranges.subscription_rs_month[1]) / 1e5;
    mk("c8", { type: "line", data: { labels, datasets: [
        { data: ad.map(r => L(r.rs_p90)), borderWidth: 0, pointRadius: 0, fill: "+1", backgroundColor: css("--line"), order: 4 },
        { data: ad.map(r => L(r.rs_p10)), borderWidth: 0, pointRadius: 0, fill: false, order: 3 },
        { data: ad.map(r => L(r.rs_p50)), borderColor: css("--good"), backgroundColor: css("--good"), borderWidth: 2.5, pointRadius: 3, order: 1 },
        { data: ad.map(() => needRs), borderColor: css("--bad"), borderDash: [5, 4], borderWidth: 1.4, pointRadius: 0, order: 2 }] },
      options: { plugins: { legend: { display: false }, tooltip: { filter: i => i.datasetIndex === 2 || i.datasetIndex === 3,
          callbacks: { title: i => `Operators follow ${i[0].label} of the advice`, label: i => i.datasetIndex === 3 ? `12-month payback needs Rs ${i.raw.toFixed(1)} lakh` : `Typical saving Rs ${i.raw.toFixed(1)} lakh a year` } } },
        scales: { x: { grid: { display: false }, title: { display: true, text: "Share of the practice advice operators follow" } },
                  y: { min: 0, title: { display: true, text: "Rs lakh a year" } } } } });
  };

  V.feasibility = () => {
    const kit = H.kit_rs;
    app.innerHTML = `
    <section class="view">
      <div><h1>Feasibility and cost</h1><p class="lede">Everything here is off-the-shelf: Class 1 Modbus meters, standard CTs, a 4G gateway and open-source software. The design choices below answer the questions a Schneider engineer would ask first.</p></div>
      <div class="grid g3">
        <div class="panel" id="sld"><h2>Where the meters go</h2><div class="tablewrap"><div style="min-width:560px">${sldSvg()}</div></div>
          <p class="note">The furnace is metered at 415 V, 50 Hz on the supply side of its SCR or IGBT converter, never on the medium-frequency coil circuit. RS485 runs in shielded twisted pair with 120 ohm termination and surge protection, on a tray away from the furnace bus bars.</p></div>
        <div class="panel" id="bom"><h2>Kit for one plant</h2><div class="tablewrap"><table><thead><tr><th>Item</th><th class="num">Rs</th></tr></thead><tbody>
          ${D.bom.map(b => `<tr><td>${esc(b.item)}<br><span class="note">${esc(b.basis)}</span></td><td class="num">${inr(b.low)} to ${inr(b.high)}</td></tr>`).join("")}
          <tr><td><b>Total kit</b></td><td class="num"><b>${inr(kit[0])} to ${inr(kit[1])}</b></td></tr></tbody></table></div>
          <div class="mini" style="margin-top:12px"><div><b>Rs ${lakh(H.year1_cost_rs[0])} to ${lakh(H.year1_cost_rs[1])} lakh</b>year-one cost with subscription</div><div><b>${H.payback_months[0].toFixed(1)} to ${H.payback_months[1].toFixed(1)} months</b>payback (energy only: ${H.payback_months_energy_only[0].toFixed(1)} to ${H.payback_months_energy_only[1].toFixed(1)})</div></div>
          <p class="note">Financing: ADEETIE interest subvention (5% for micro and small, 3% for medium units) or a vendor lease, so the owner can start at zero upfront.</p></div>
      </div>
      <div class="grid g2">
        <div class="panel"><h2>Data points and polling</h2><div class="tablewrap"><table><thead><tr><th>Quantity</th><th>Meters</th><th>Every</th></tr></thead><tbody>
          <tr><td>Active power kW, per phase current</td><td>All three</td><td>1 s</td></tr>
          <tr><td>Active energy kWh (import)</td><td>All three</td><td>15 s</td></tr>
          <tr><td>Reactive power, power factor</td><td>All three</td><td>60 s</td></tr>
          <tr><td>Voltage and current THD</td><td>Mains, furnace</td><td>60 s</td></tr>
          <tr><td>Modbus CRC errors, gaps</td><td>Gateway</td><td>60 s, shown as data completeness</td></tr>
          </tbody></table></div><p class="note">About 5 MB a day raw; the gateway stores 7 days if 4G drops and the cloud keeps 1-minute and 15-minute aggregates. Register addresses come from the chosen meter's datasheet.</p></div>
        <div class="panel"><h2>Top risks and what we do about them</h2><div class="tablewrap"><table><thead><tr><th>Risk</th><th>Mitigation</th></tr></thead><tbody>
          <tr><td>AI machine split less accurate in the field</td><td>Two big loads metered directly; confidence tier per machine; one-day clamp-on check after schedule changes</td></tr>
          <tr><td>Wrong carbon boundary for CBAM</td><td>Direct and precursor emissions priced; electricity reported separately; verifier-ready evidence trail</td></tr>
          <tr><td>Tariff savings overstated</td><td>Real FY 2026-27 PGVCL tariff with FPPAS and duty; timing value reported separately</td></tr>
          <tr><td>Late or missing heat log entries</td><td>WhatsApp and voice entry; furnace meter detects every heat so gaps are flagged</td></tr>
          <tr><td>Harmonics corrupt readings</td><td>Meter on 50 Hz side, shielded cable, CRC counter, completeness tile</td></tr>
          <tr><td>Owner does not act</td><td>Three actions a day, priced in rupees, in his language; weekly progress against his best week</td></tr>
          <tr><td>Personal data (DPDP Act 2023)</td><td>Consent screen, purpose limitation, India-region hosting, role-based access, deletion on request</td></tr>
          </tbody></table></div></div>
      </div>
    </section>`;
  };
  function sldSvg() {
    return `<svg class="sld" viewBox="0 0 720 320" role="img" aria-label="Single-line diagram: transformer, main bus with mains meter M1, furnace feeder with meter M2 before the converter, compressor feeder with meter M3, and auxiliaries">
      <style>.l{stroke:currentColor;stroke-width:2;fill:none}.t{font:12px ${css("--ui")};fill:currentColor}.m{fill:${css("--good-fill")};stroke:currentColor;stroke-width:1.5}.b{fill:${css("--tint")};stroke:currentColor;stroke-width:1.5}</style>
      <g style="color:${css("--ink")}">
      <circle class="l" cx="60" cy="38" r="16"/><circle class="l" cx="60" cy="60" r="16"/><text class="t" x="86" y="53">11 kV / 415 V transformer, 600 kVA contract demand</text>
      <line class="l" x1="60" y1="76" x2="60" y2="130"/><rect class="m" x="44" y="92" width="32" height="20" rx="3"/><text class="t" x="84" y="107">M1 mains meter (CT 1000/5 A)</text>
      <line class="l" x1="20" y1="130" x2="700" y2="130" style="stroke-width:4"/><text class="t" x="600" y="122">415 V main bus</text>
      <line class="l" x1="100" y1="130" x2="100" y2="236"/><rect class="m" x="84" y="148" width="32" height="20" rx="3"/><text class="t" x="124" y="163">M2 furnace meter</text>
      <rect class="b" x="62" y="192" width="76" height="28" rx="3"/><text class="t" x="70" y="211">SCR/IGBT</text><text class="t" x="146" y="211">converter; M2 is on its 50 Hz side</text>
      <rect class="b" x="62" y="236" width="76" height="34" rx="3"/><text class="t" x="76" y="258">550 kW</text><text class="t" x="146" y="258">500 kg induction furnace</text>
      <line class="l" x1="430" y1="130" x2="430" y2="196"/><rect class="m" x="414" y="148" width="32" height="20" rx="3"/><text class="t" x="454" y="163">M3 compressor meter</text>
      <rect class="b" x="402" y="196" width="56" height="28" rx="3"/><text class="t" x="411" y="215">15 kW</text><text class="t" x="466" y="215">screw compressor</text>
      <line class="l" x1="640" y1="130" x2="640" y2="248"/><rect class="b" x="560" y="248" width="150" height="44" rx="3"/><text class="t" x="568" y="266">Auxiliaries, AI split:</text><text class="t" x="568" y="284">pump, fans, sand, blast</text>
      <text class="t" x="20" y="312">M1 to M3 on one RS485 bus to a 4G gateway with a 7-day buffer</text>
      </g></svg>`;
  }

  let sens = { yield: C.yield_ * 100, rej: 5, rate: 1.0, ef: C.grid_ef };
  V.method = () => {
    app.innerHTML = `
    <section class="view">
      <div><h1>Sources and assumptions</h1><p class="lede">Every number on this site comes from a simulation calibrated to the sources below. "Sourced" values come from a cited document; "Assumption" values are engineering estimates that a pilot will replace with site data. Move the sliders to see how the headline changes.</p></div>
      <div class="panel" id="sens"><h2>Sensitivity</h2>
        <div class="grid g2" style="gap:14px">
          <label class="sl" for="sy">Yield, liquid metal to castings <b id="syv"></b><input type="range" id="sy" min="55" max="85" value="${sens.yield}"></label>
          <label class="sl" for="sr">Casting rejects <b id="srv"></b><input type="range" id="sr" min="2" max="12" value="${sens.rej}"></label>
          <label class="sl" for="st">Tariff level versus PGVCL FY 2026-27 <b id="stv"></b><input type="range" id="st" min="0.7" max="1.3" step="0.05" value="${sens.rate}"></label>
          <label class="sl" for="se">Grid emission factor, tCO2/MWh <b id="sev"></b><input type="range" id="se" min="0.6" max="0.8" step="0.005" value="${sens.ef}"></label>
        </div>
        <div class="mini" style="margin-top:14px" id="sensout"></div></div>
      <div class="panel"><h2>Parameters</h2><div class="tablewrap"><table><thead><tr><th>Parameter</th><th>Value</th><th>Status</th><th>Source</th></tr></thead><tbody>
        ${D.params.map(p => `<tr><td>${esc(p.key)}</td><td>${esc(p.value)} ${esc(p.unit)}</td><td><span class="chip ${p.status === "sourced" ? "ok" : "mute"}">${p.status === "sourced" ? "Sourced" : p.status === "design" ? "Design choice" : "Assumption"}</span></td><td>${esc(p.source)}</td></tr>`).join("")}
      </tbody></table></div></div>
      <div class="panel"><h2>What is real and what is simulated</h2><div class="tablewrap"><table><tbody>
        <tr><td>Real</td><td>BEE furnace energy rules, FY 2026-27 PGVCL tariff structure, CEA grid factors, CBAM rules and timelines, ADEETIE terms, meter prices, and the machine-split test on IMDELD factory data (Machines view)</td></tr>
        <tr><td>Simulated</td><td>The plant, its 90 days of 10-second data, operator behaviour, the lining fault, and therefore every saving and accuracy figure</td></tr>
        <tr><td>Next</td><td>Pilot three Rajkot foundries with clamp-on checks, to replace the simulated plant with real foundry data</td></tr>
      </tbody></table></div></div>
    </section>`;
    const out = () => {
      const goodPerLiq = (sens.yield / 100) * (1 - sens.rej / 100);
      const plantB = B0.sec_good_plant * (C.yield_ * (1 - B0.reject_rate)), plantS = S1.sec_good_plant * (C.yield_ * (1 - S1.reject_rate));
      const mwh = (plantB - plantS) * H.annual_liquid_t / 1000;
      const rs = H.annual_rs_from_energy * sens.rate + H.tod_isolated_annual_rs * sens.rate;
      document.getElementById("syv").textContent = `${sens.yield}%`; document.getElementById("srv").textContent = `${sens.rej}%`;
      document.getElementById("stv").textContent = `${sens.rate.toFixed(2)}x`; document.getElementById("sev").textContent = sens.ef.toFixed(3);
      document.getElementById("sensout").innerHTML = `<div><b>${inr(plantB / goodPerLiq)} to ${inr(plantS / goodPerLiq)}</b>plant kWh per good tonne</div>
        <div><b>${inr(mwh)} MWh</b>saved per year (does not depend on yield)</div><div><b>Rs ${lakh(rs)} lakh</b>saved per year</div><div><b>${inr(mwh * sens.ef)} tCO2</b>avoided per year</div>`;
    };
    [["sy", "yield", 1], ["sr", "rej", 1], ["st", "rate", 1], ["se", "ef", 1]].forEach(([id, k]) => document.getElementById(id).oninput = e => { sens[k] = +e.target.value; out(); });
    out();
  };

  /* ---------- router ---------- */
  const ORDER = ["overview", "briefing", "drift", "machines", "planner", "carbon", "proof", "stress", "feasibility", "method"];
  function show(v, opts) {
    charts.splice(0).forEach(c => c.destroy());
    if (!V[v]) v = "overview";
    document.querySelectorAll("#tabs a").forEach(a => a.setAttribute("aria-current", a.getAttribute("href") === "#" + v ? "page" : "false"));
    chartDefaults();
    V[v]();
    if (!(opts && opts.keepScroll)) window.scrollTo(0, 0);
    return v;
  }
  window.UK = { show, order: ORDER };
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
  document.querySelectorAll("[data-goto]").forEach(b => b.addEventListener("click", () => { location.hash = b.dataset.goto; }));
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => show(location.hash.slice(1) || "overview", { keepScroll: true }));
  show(location.hash.slice(1) || "overview");
})();
