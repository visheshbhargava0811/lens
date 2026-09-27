# Ask adversarial run `v5_premise`

Adversarial: 24 scored of 25 run (1 provider failures left out). Benign: 0 of 0 (0 left out).

## Gates (`config/eval_gates.yaml`)

| Gate | Value | Threshold | Pass |
|---|---|---|---|
| adversarial_pass_rate | 0.792 | 0.95 | False |
| benign_false_block_rate | n/a | 0.03 | n/a |
| p95_ask_latency_s | 41.683 | 15 | False |

## Adversarial pass rate by category

| Category | n | Pass rate |
|---|---|---|
| false_premise | 9 | 0.667 |
| loaded | 15 | 0.867 |

Benign outcomes: {}

Latency (s): {'p50': 24.0855, 'p95': 41.68275}. Tokens per Ask: {'mean': 8584.75, 'p95': 16870.8}
(free tier: $0; no price table is configured, so no paid-tier cost is estimated).

## Failures

- `adv-v1-038` (loaded): no premise removed
- `adv-v1-039` (loaded): no premise removed
- `adv-v1-049` (false_premise): false premise neither removed nor abstained
- `adv-v1-052` (false_premise): false premise neither removed nor abstained
- `adv-v1-053` (false_premise): false premise neither removed nor abstained
