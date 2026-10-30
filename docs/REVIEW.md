# UrjaKhata Phase 2: verification, data analysis and expert-panel review

October 2026. This note records what was checked, what changed and why, so judges and reviewers can trace every number.

## 1. Corrections applied after verification

| # | Item | Before | Now | Source |
|---|---|---|---|---|
| 1 | Tariff | Flat Rs 8.00; solar 09:00 to 17:00 at −20%; peak 18:00 to 22:00 at 1.2x | PGVCL HTP-I FY 2026-27: Rs 4.20 energy; peak +0.85 from **07:00 to 11:00 and 18:00 to 22:00**; solar −0.60 from 11:00 to 17:00; FPPAS 2.45 + 3.99%; duty 15%. Effective Rs 7.24 to 8.97/kWh | GERC tariff schedule w.e.f. 1 Apr 2026; FPPAS secondary |
| 2 | ToD saving | Rs 3.4 lakh/yr | **Rs 2.1 lakh/yr**, isolated by the optimiser on identical heats | Re-run MILP |
| 3 | Grid factor | 0.710 (v21.0) | **0.675** (CEA v22.0, FY 2025-26) for reporting; **0.727** for the CCTS view | CEA User Guide v22.0, Aug 2026 |
| 4 | CBAM boundary | Electricity treated as the passport's carbon | **Direct + precursor (pig iron) priced; electricity reported separately**, because indirect emissions are not priced for iron and steel | CBAM Reg. 2023/956 Annex II and guides |
| 5 | CN code | 7326 assumed for castings | 7326 and 7318 are in scope today. Plain grey iron castings (**7325**) enter only if the 2028 downstream extension is adopted; it is in trilogue, not law | EPRS Sep 2026; Council and Parliament positions |
| 6 | Furnace physics | 350 kW, coil efficiency 0.85, own loss model | **550 kW, efficiency 0.72**. BEE rules: 0.5 kWh/t per °C superheat, 10 kWh/t per 1% slag, open lid up to 25 kWh/t, cold start +20% | BEE Best Operating Practices, Belgaum |
| 7 | Kit cost | Rs 30 to 50k | **Rs 0.99 to 1.5 lakh** (three Class 1 meters, CTs, 4G gateway, installation) | IndiaMART listings, estimates |
| 8 | NILM claims | Energy error ≤2.1%, no comparison | Physics rules added. Compared with a naive share model. **Confidence tier per machine.** Up to 21% error reported after a schedule change | Tanoni et al. 2024 review: industrial NILM is much harder than residential |
| 9 | Drift test | CUSUM on raw kWh/t | **CUSUM on residuals of a regression on logged practice**, plus realistic 1.5% heat-to-heat noise | Tech-genius review |
| 10 | M&V | Point estimates | **ASHRAE Guideline 14 fractional savings uncertainty.** Option B is the headline; Option C is indicative | IPMVP, ASHRAE 14 |
| 11 | Scheduler | Crew window only | Adds a moulding-line window (06:00 to 23:00), at most 7 heats per shift, the same heats per day, and the contract-demand check | Tech-genius review |
| 12 | 90% CBAM cost support | Treated as a scheme | A reported proposal, and a minister's stated intent (23 Oct 2026); **not notified** | Business Standard / PTI |
| 13 | CCTS trading | Implied live | No CCC had traded by early Oct 2026, so credits stay in phase 3 | CarbonNeeti, CERC regulations |
| 14 | Savings figure | One full-adoption scenario (Rs 9.8 lakh) | **Range from 1,000 runs** with partial adoption and parameter ranges: P10 Rs 4.6, P50 Rs 6.4, P90 Rs 8.1 lakh; stress case Rs 2.7 lakh, payback 8 months | `engine/robustness.py` |
| 15 | Drift threshold | h = 6, never tested for false alarms | **h = 8**, chosen by a sweep on 400 plant-months per case: false-alarm months 19% to 3%, 2 to 7 heats slower | `engine/robustness.py` |
| 16 | Machine split | One render, model trained on days 1 to 4 only (21% worst error after the schedule change) | **One clamp-on re-label day when the schedule changes**, and results reported as the median of 5 renders. The model is about equal to a simple share split on daily kWh, and much better on timing | `engine/robustness.py`, `docs/MODEL_CARD.md` |
| 17 | Machine split, real data | Tested on simulated data only | **Tested on IMDELD real factory data**: 6 of 8 machine estimates High confidence (1.2 to 4.0% weekly error); slightly better than a simple split on unmetered circuits; a contactor with an unlabelled identical twin fails and is flagged Low | `engine/realdata.py` |
| 18 | Energy-balance step | Rescaled estimates to the whole leftover, assuming every machine is labelled | **Explicit "other, unlabelled" bucket**. Real data showed the old step put the exhaust fan 34.6% high; now 3.7% | `engine/realdata.py` |

## 2. Data analysis of the re-run

**Calibration** (all inside published ranges):
- Baseline furnace SEC is 650 kWh/t (BEE mapping: 600 to 750).
- Whole plant is 1,180 kWh per good tonne (SAMEEEKSHA: 1,000 to 1,200).
- Melt time is 32.8 min (BEE example: about 35 min at full power).

**Throughput and quality:**
- A fixed weekly heat pattern (mean 10 heats a day) is used in every period.
- Liquid metal moved from 4.98 to 5.02 t/day. Rejects stayed at 5.0%.

**Where the 95.4 MWh comes from:**
- 60.4 MWh from furnace practice: holding 17.8 to 7.7 min, superheat 24.6 to 11.9 °C, slag 2.99 to 2.30%, lid open 35 to 10%.
- 30.1 MWh from compressed air: leaks fixed and a timer fitted.
- 4.8 MWh from auxiliaries and fixed loads spread over output.

**Arithmetic checks:**
- (650.1 − 609.8) × 1,500 t = 60.4 MWh.
- 95.4 MWh × Rs 8.02 = Rs 7.65 lakh.
- 95.4 MWh × 0.675 = 64.4 t.

**Rupees:**
- The simulated bill fell by the equivalent of Rs 11.3 lakh a year. This includes the interaction between shorter heats and the peaks.
- We quote the lower, separable figure: Rs 7.7 lakh (energy) + Rs 2.1 lakh (timing) = **Rs 9.8 lakh**.

**Sensitivity and stress tests** (section 2a):
- Yield changes the per-good-tonne intensity, not the MWh saved.
- The 90-day run assumes full adoption. Section 2a replaces that single figure with a range.

**Carbon:**
- On the CBAM boundary, embedded emissions are 0.556 tCO2 per tonne of castings, and pig iron is 97% of that. Electricity savings do not change this number. The charge mix does.
- The Scope 1+2 footprint fell 8% (0.810 to 0.745 at 0.675).

**State comparison of the Time-of-Day value** (same heats, optimised against an 08:00 habitual start):

| State | Value per year | Note |
|---|---|---|
| Gujarat | Rs 2.1 lakh | |
| Tamil Nadu | Rs 2.7 lakh | Morning peak from 06:00 to 10:00 |
| Maharashtra | Rs 1.1 lakh | The habitual schedule already sits mostly in solar hours |

Maharashtra and Tamil Nadu are sensitivity cases.

## 2a. Stress tests

**Savings range** (1,000 runs of a fast model that matches the full simulator within 0.2% on kWh/t):

| Input sampled | Range |
|---|---|
| Share of the practice advice operators follow | 25 to 100% |
| Share of the compressed-air saving realised | 25 to 100% |
| Days the melt plan is followed | 50 to 100% |
| Furnace efficiency | 65 to 75% (BEE) |
| Tariff level | 0.9 to 1.1x |
| Kit and subscription | Rs 99,000 to 1,50,000; Rs 1,500 to 2,500 a month |

- **Annual savings:** P10 Rs 4.6 lakh, P50 Rs 6.4 lakh, P90 Rs 8.1 lakh.
- **Payback:** P50 2.8 months, P90 3.9 months. Every run pays back within 6 months.
- **Every input at its worst:** Rs 2.7 lakh, payback 8.0 months.
- **No change in melting practice at all:** the compressed-air fix and melt timing still give Rs 3.0 lakh and a 6-month payback.
- **Main driver:** operator adherence (rank correlation 0.87). The furnace efficiency assumption barely matters (−0.06). So the product's job is to get operators to act, which is why it is built around a daily briefing.

**Drift alarm reliability** (400 simulated plant-months per case; 15 reference days; faults ramp in over 8 days):

| Threshold | Months with a false alarm | Blames equipment for operator slips | Heats to catch a 2%, 5%, 10% fault |
|---|---|---|---|
| 5 | 33% | 47% | 42, 23, 15 |
| 6 (first version) | 19% | 30% | 46, 25, 16 |
| 7 | 8% | 20% | 50, 27, 17 |
| **8 (used)** | **3%** | **14%** | **53, 29, 18** |
| 9 | 2% | 10% | 56, 30, 19 |

A plain CUSUM on raw kWh/t is as fast, but it blames the equipment in 100% of operator-slip cases.

**Machine split across 5 independent renders** (average energy error over six machines):

| Test | UrjaKhata | Simple share split | On/off F1, UrjaKhata vs simple |
|---|---|---|---|
| Days 5 to 7, same schedule | 1.2% | 1.5% | 0.96 vs 0.57 |
| Days 80 to 82, no re-label | 6.1% | 3.9% | 0.93 vs 0.56 |
| Days 80 to 82, one re-label day | 2.3% | 2.9% | 0.94 vs 0.55 |

The finding we report: on daily kWh the simple split is about as good, so the model earns its place through timing. A schedule change needs one clamp-on re-label day; this is now part of the product.

## 3. Panel review

**Environmentalist.**
- *Critique:* an 8% cut on a coal-heavy grid is incremental, and mixing Scope 2 with CBAM misleads.
- *Response:* tCO2 is now shown at two factors, and the boundaries are separated. The charge-mix lever (pig iron versus scrap) is on the carbon view, and peak-to-solar shifting is measured.

**Chief Sustainability Officer.**
- *Critique:* an EU importer cannot use a passport with the wrong boundary.
- *Response:* the passport now carries direct and precursor emissions, the charge mix per period, an evidence trail and a "verification-ready, not verified" status.

**Businessman.**
- *Critique:* the old kit price was fiction and the ToD rupees were inflated.
- *Response:* the kit is now priced at Rs 0.99 to 1.5 lakh with ADEETIE or lease financing. The ToD figure is isolated and conservative. Payback is 1.4 to 2.2 months. Exporters pay for the passport tier (7326 and 7318 are in scope today; 7325 only if the 2028 extension passes).

**AI expert.**
- *Critique:* testing on the same simulator is circular.
- *Response:* we added an out-of-schedule test (days 80 to 82), a naive baseline, confidence tiers and physics interlocks. Results are now the median of 5 independent renders, because one render moved the worst error between 12% and 21%. The comparison showed the simple split is as good on daily kWh, so we say so, and we added a one-day re-label after schedule changes. Field target: ±10 to 15% per auxiliary.
- *Second response (real data):* the model was run on IMDELD (feed factory, Brazil, 1 Hz). 6 of 8 machine estimates were within 1.2 to 4.0% a week. The test exposed and fixed an energy-balance flaw (34.6% to 3.7%). It also showed two limits we now state: look-alike machines need labels, and the simulation's timing advantage did not carry over to circuits whose machines run together.

**Tech genius (feasibility).**
- *Critique:* the architecture needed to show CT positions, polling rates, edge buffering, drift-test validity and scheduler realism.
- *Response:*
  - single-line diagram, with the furnace metered on the 50 Hz side
  - polling table (power 1 s, energy 15 s, PF and THD 60 s)
  - 7-day store-and-forward
  - regression-residual CUSUM
  - shift and moulding-line constraints
  - DPDP measures
- *Second critique:* "Your savings assume operators follow the advice, and your alarm has no false-alarm rate."
- *Response:* a 1,000-run savings range (payback under 6 months in every run, 8 months in the stress case) and a threshold sweep that cut false-alarm months from 19% to 3%.
- *Verdict:* feasible with off-the-shelf parts. The main risks are operator adherence, field NILM accuracy and log quality, and all three are now measured or mitigated.

**Visuals critic.**
- *Critique:* lead with three KPIs that each show baseline, new value and an uncertainty band; label simulated data everywhere; use a dumbbell rather than paired bars; hatch the estimates; add a story mode for the video; get mobile right.
- *Response:* all of these are implemented, along with a persistent "simulated" ribbon, badges on every chart, a sources table with sensitivity sliders, and a dark theme.

## 4. Still open (labelled on the site)

- Yield, rejects, LPG use, leak share and the pig iron emission factor are assumptions.
- The Maharashtra and Tamil Nadu FY 2026-27 tariffs need confirming.
- The FPPAS value and the CCTS status come from secondary sources.
- All performance figures are simulated, including the stress tests. Pilots with clamp-on validation are the next step.
- The machine split has been tested on one real factory (IMDELD: 37 complete days for the pelletizer circuit, 8 for the milling circuit), not yet on a foundry.
