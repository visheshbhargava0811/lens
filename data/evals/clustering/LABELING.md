# Labeling clustering stories

The clustering eval needs people to decide which articles report the **same event**. You correct a draft grouping in a spreadsheet. You don't have to start from scratch.

## What you get

`to_label_<date>.csv` opens in Google Sheets, Excel or Numbers. Rows are sorted by draft group, so articles the machine thinks belong together sit next to each other.

| Column | What it is | Edit? |
|---|---|---|
| `draft_group` | The machine's guess | No |
| `story` | Your answer. Prefilled with the draft group | **Yes** |
| `hard_negative_group` | Marks stories on the same topic but a different event. Prefilled as a hint | Yes |
| `notes` | Optional, e.g. `hard` for tricky rows | Yes |
| language, source, time, title, snippet | The article | No |

## The one rule

**Same event, not same topic.**
- "Heavy rain floods Mumbai on 21 Sept" and "मुंबई में भारी बारिश, सड़कें जलमग्न" are the same event.
- "Floods in Assam" and "Floods in Kerala" are the same topic but different events.
- An explainer or opinion piece about an event belongs with that event.
- Updates to the same event over hours or days stay in one story: first report, death toll revised, arrests made.

## How to edit `story`

- **Rows agree with their group:** leave them.
- **A row belongs to a different event:** give it a new label. Any text works, e.g. `mumbai-rain`.
- **Two draft groups are the same event:** give them the same label.
- **A single-article row (`s…`) is part of an event in the sheet:** use that event's label. Otherwise leave it.
- **A row isn't news** (horoscope, ad, quiz): write `drop`.
- **`hard_negative_group`:** if two different events share a topic (two separate floods, two separate court cases), give both stories the same value, e.g. `hn-floods`. Otherwise clear the hint.

Hindi, Marathi and English rows about the same event must get the **same** label. Cross-lingual grouping is what this eval measures.

## How much we need (docs/04)

- **At least 100 stories.** 150 are prefilled, so some can be dropped.
- **At least 30 cross-lingual stories:** the same event in English and Hindi or Marathi.
- **At least 20 hard-negative stories** in hard-negative groups.
- **At least 10 developing stories** that span 6 or more hours with 3 or more articles. These are detected automatically.

Expect about 2 to 3 hours for 150 stories. A second person labeling a 20% sample lets us measure agreement.

## Hand it back

Save as CSV (UTF-8) in this folder, then run:

```bash
make cluster-label-import FILE=data/evals/clustering/to_label_<date>.csv ANNOTATOR=<your-name> NAME=v1
```

This checks the file and writes `gold_v1.jsonl`, which `make eval` picks up.
