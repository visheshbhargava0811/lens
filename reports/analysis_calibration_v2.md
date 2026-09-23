# Judge calibration v2 (owner-adjudicated labels)

Computed from the **same Qwen verdicts** as `analysis_calibration_v1b` (no new model calls), against
`data/evals/judge_calibration/gold_v2.jsonl`: the owner's blind labels (`gold_v1`) with the 21
sentences the judge rejected and the owner had accepted **re-labeled "not supported" by the owner
after reviewing the judge's verdicts** ("I judged too leniently; the judge was right not to let them go").

**Not a blind measurement.** The adjudication was done with knowledge of the judge's verdict, so this
kappa is an upper bound. The blind figure remains kappa 0.473 (`analysis_calibration_v1b`).

| | n | kappa | agreement | judge too lenient | judge too strict |
|---|---|---|---|---|---|
| gold_v2 (adjudicated) | 122 | **0.944** | 0.975 | 3 | 0 |

Per language: en n=52 kappa=0.913, en+hi n=40 kappa=0.942, en+hi+mr n=8 kappa=1.0, en+mr n=2 kappa=1.0, hi n=20 kappa=1.0

Consequence: the judge prompt is kept as is (v1.0). The remaining risk is the 3 sentences the judge
accepted and the owner rejected. The next blind label set should measure the judge again.
