# Topic tagging eval (160 stories, data/evals/topics/gold_v1.jsonl)

Gold labels are Claude-drafted and owner-reviewed 2026-09-27 (minor deviations accepted).
Thresholds tuned on half A for topical F1; half B is held out. Untagged counts as "none".

| Method | Thresholds | Half | Accuracy | Precision | Recall | F1 | Coverage |
|---|---|---|---|---|---|---|---|
| keyword | - | B | 0.750 | 0.610 | 0.812 | 0.697 | 0.512 |
| keyword | - | all | 0.750 | 0.630 | 0.739 | 0.680 | 0.506 |
| raw | sim ≥ 0.58, margin ≥ 0.03 | B | 0.713 | 0.567 | 0.688 | 0.621 | 0.375 |
| raw | sim ≥ 0.58, margin ≥ 0.03 | all | 0.731 | 0.644 | 0.681 | 0.662 | 0.369 |
| centered | sim ≥ 0.28, margin ≥ 0.0 | B | 0.887 | 0.864 | 0.781 | 0.820 | 0.275 |
| centered | sim ≥ 0.28, margin ≥ 0.0 | all | 0.894 | 0.915 | 0.797 | 0.852 | 0.294 |
