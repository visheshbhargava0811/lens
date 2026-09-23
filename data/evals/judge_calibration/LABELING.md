# Labeling: is the sentence supported by its evidence?

This set measures whether the automatic judge agrees with a person (Cohen's kappa, docs/08). Your labels are the ground truth, so judge only from what is on the row.

File: `to_label_<date>.csv`. Open it in **Google Sheets** (File → Import → Upload) so Hindi and Marathi text survive. Excel and Numbers can garble it.

## What you edit

| Column | What to do |
|---|---|
| `supported` | **yes**, **no**, or leave blank to skip |
| `notes` | Optional: why, or `hard` for a close call |
| everything else | Leave as is |

## The one question

**Does the evidence on this row state (or directly imply) everything the sentence says?**

- Read the `sentence`, then the `evidence` (numbered articles: headline, then the feed summary if there is one).
- **yes**: every fact, number, name, date and "who said what" in the sentence is in the evidence. Different wording or language is fine: a Hindi article can support an English sentence.
- **no**: anything in the sentence is missing, different, or stronger than the evidence. One unsupported detail is enough for **no**.

## Rules of thumb

- **Use only the evidence on the row.** Do not use what you know about the news. If the sentence is true in real life but the evidence does not say it, the answer is **no**.
- **Attribution counts.** "SBI advised customers to use digital channels" is **no** if the evidence says *a bank* or *another outlet* advised it, not SBI.
- **Generalizations.** "All articles say X" is **no** unless every numbered article on the row says X.
- **Numbers.** "10 seats in UP" is **no** if the evidence only says "12 seats across three states".
- **Softening is fine; hardening is not.** Evidence "police said three were arrested" supports "three people were arrested, police said" (**yes**) but not "three people committed the crime" (**no**).
- **Close call?** Pick your best answer and write `hard` in `notes`. Skip only if you really cannot tell.

## Examples

| Sentence | Evidence says | Label |
|---|---|---|
| The Court asked the EC to add safeguards, including other ways for voters to respond. | "…asks EC to adopt additional safeguards" + "suggests allowing voters to respond through WhatsApp, email" | yes |
| The strike will close banks for five days. | "three-day strike from September 28 to 30" (only one article mentions the weekend) | no, unless an article on the row says five days |
| India beat Sri Lanka by 147 runs. | "India thrash Sri Lanka by 147 runs" | yes |

## How many

All 200 if you can. 100 is the minimum that gives a stable kappa, and it helps to include Hindi and Marathi rows. Expect about 1 minute per row.

## Hand it back

Download as CSV (UTF-8), save it in this folder, then run:

```
make judge-label-import FILE=data/evals/judge_calibration/<your file>.csv ANNOTATOR=vishesh NAME=v1
make eval-analysis NAME=calibration_v1
```

The second command re-runs the judge on each labeled sentence and reports agreement overall and per language (target kappa ≥ 0.6).
