# UrjaKhata model card

One page per model: what it is for, what it was tested on, how well it did and where it fails. Results come from simulated plants (see `engine/sim.py`), except the machine split, which was also tested on real factory data (IMDELD, `engine/realdata.py`). The robustness code is in `engine/robustness.py`, and `python -m engine.pipeline` reproduces all of it.

## 1. Machine split (hybrid NILM)

| | |
|---|---|
| **Purpose** | Split the leftover load (mains minus the furnace and compressor sub-meters) into six auxiliary machines, so the briefing can say which machine ran when. |
| **Model** | One scikit-learn `HistGradientBoostingRegressor` per machine. Inputs are a window of leftover load, time of day and furnace state. Two physics rules from commissioning: the cooling pump runs only while the furnace is energised or for 20 min after; fume extraction runs only while melting. Estimates are rescaled so they add up to the measured leftover load. |
| **Training data** | 4 commissioning days with portable clamp meters on each machine (days 1 to 4). One more clamp-on day whenever the melt schedule changes (day 43, when the Time-of-Day plan starts). |
| **Test data** | Unseen days 5 to 7 (same schedule as training) and 80 to 82 (Time-of-Day schedule). Repeated over 5 independent simulated renders. |
| **Results (median of 5 runs)** | Days 5 to 7: average energy error 1.2%, worst machine 2.6%. Days 80 to 82 with the one-day re-label: 2.3% average, worst about 8%. Without the re-label: 6.1% average, worst up to 17%. On/off F1 0.94 to 0.96. |
| **Simple alternative** | A fixed share of the leftover load gets daily energy about as close (1.5% and 2.9%), but its on/off F1 is only 0.55 to 0.57. **Conclusion:** the model earns its place through timing, not daily kWh. |
| **Real factory data (IMDELD)** | Feed factory in Brazil, 1 Hz, 4 labelled days, weekly error on up to 33 unseen days. 6 of 8 machine estimates were High confidence, with 1.2 to 4.0% weekly energy error. On unmetered circuits the model was slightly better than a simple share split (2.2% vs 2.8%, and 3.2% vs 4.0%). A small contactor whose identical twin was unlabelled failed (21 to 57%; the simple split also failed) and was flagged Low. On these circuits machines start and stop together, so the simple split's timing was as good (F1 0.96 or better). Code: `engine/realdata.py`. |
| **Fix found by real data** | The energy-balance step assumed every machine in the leftover was labelled; with two unlabelled machines the exhaust fan came out 34.6% high. An explicit "other, unlabelled" bucket brought it to 3.7%. In the simulation every machine is labelled, so the bucket is empty. |
| **Known failure modes** | Schedule changes without a re-label; new or replaced machines; look-alike machines where only one is labelled; very small loads (under about 1 kW) next to large ones. |
| **Safeguards** | Confidence tier (High, Medium, Low) per machine on every report; Low machines are shown as part of "other", not as a number. An "other, unlabelled" bucket. A one-day clamp-on re-label after any schedule change. Commissioning rule: clamp every machine in the leftover, or report look-alikes as one group. The two biggest loads are metered directly, never estimated. |
| **Field target** | Plus or minus 10 to 15% per auxiliary. Next check: pilot clamp-on data from Rajkot foundries. |

## 2. Drift alarm (regression-residual CUSUM)

| | |
|---|---|
| **Purpose** | Flag equipment wear (furnace lining or coil) that raises melting energy, without blaming operators for practice they logged. |
| **Model** | Linear regression of melting kWh/t on logged superheat, slag % and charge weight, fitted on 15 reference days. A one-sided CUSUM runs on the standardised residuals, with slack k = 0.5 and threshold h = 8. |
| **Threshold choice** | Swept h from 5 to 9 on 400 simulated plant-months per case. Raising h from 6 to 8 cut false-alarm months from 19% to 3%, and added 2 to 7 heats of delay. |
| **Results at h = 8** | Months with a false alarm: 3%. Faults of 2%, 5% and 10% (ramping in over 8 days) were caught in 100% of runs, after a median of 53, 29 and 18 heats. In the 90-day scenario, a lining fault (about 7%) was caught 22 heats after onset. |
| **Simple alternative** | The same CUSUM on raw kWh/t is as fast. But when operators slip back (superheat 12 to 22 °C, slag 2.3 to 2.8%), it blames the equipment in 100% of cases; ours does so in 14%. |
| **Known failure modes** | Wear that starts during the reference period; unlogged practice changes (lid left open); a wrong pyrometer. |
| **Safeguards** | An alarm sends an inspection request, not a shutdown. The reference period is refreshed after each relining. Practice slips go to the briefing as rupee actions instead. |

## 3. Time-of-Day melt planner (MILP)

| | |
|---|---|
| **Purpose** | Place each day's heats in the cheapest tariff hours without changing output. |
| **Model** | Mixed-integer program (SciPy HiGHS) on 5-minute slots. Constraints: one furnace with no overlapping heats; the 06:00 to 23:00 moulding-line window; at most 7 heats per shift; and the same number of heats each day. |
| **Inputs** | Effective tariff (PGVCL HTP-I FY 2026-27, including FPPAS and duty) and the heat energy profile. MSEDCL and TNPDCL are sensitivity cases. |
| **Results** | Rs 2.1 lakh a year on PGVCL from timing alone (same heats). Plant energy in peak hours falls from 41% to 14%. Every plan passes the shift check. |
| **Simple alternative** | The habitual 08:00 back-to-back start. |
| **Known failure modes** | Tariff revisions; rush orders; power cuts; crew availability. |
| **Safeguards** | The plan is advice, re-solved daily. Value is reported separately from energy savings and scaled by the share of days followed (50 to 100% in the robustness runs). |

## 4. Savings verification (IPMVP Options B and C)

| | |
|---|---|
| **Purpose** | Verified savings for lenders, ADEETIE and ESCOs. |
| **Model** | Option B: kWh per heat against charge weight and first heat of the day (furnace sub-meter). Option C: kWh per day against liquid tonnes (main meter). Both use a 28-day baseline and ASHRAE Guideline 14 fractional savings uncertainty at 90% confidence. |
| **Results** | Option B: 11,613 kWh (5.7%), 90% band 11,203 to 12,023 kWh. Option C: 18,062 kWh (7.4%), indicative only. |
| **Known failure modes** | Bands are narrow because simulated noise is modest; real sites will be wider. Non-routine changes (a new furnace, a product mix shift) need adjustments. |

## 5. Savings range (Monte Carlo)

| | |
|---|---|
| **Purpose** | Replace the single full-adoption figure with a range. |
| **Method** | 1,000 runs of a fast vectorised model, which matches the full simulator within 0.2% on kWh/t. Inputs sampled uniformly: practice adherence 25 to 100%; compressed-air saving realised 25 to 100%; melt plan followed 50 to 100% of days; furnace efficiency 65 to 75%; tariff 0.9 to 1.1x; kit and subscription across their price ranges. |
| **Results** | Annual savings: P10 Rs 4.6 lakh, P50 Rs 6.4 lakh, P90 Rs 8.1 lakh. Payback: P50 2.8 months, P90 3.9 months; every run is under 6 months. Stress case (every input at its worst): Rs 2.7 lakh and 8.0 months. With no practice change at all: Rs 3.0 lakh and 6 months. |
| **Main driver** | Operator adherence (rank correlation 0.87). The furnace efficiency assumption barely matters (−0.06). |
