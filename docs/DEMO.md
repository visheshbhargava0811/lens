# Interview demo checklist

Lens runs on your Mac for the demo. Nothing is hosted. The data (articles, stories, summaries, preferences) lives in Docker volumes and survives stopping Docker.

## Between demos

```bash
make demo-stop        # stops everything; data is kept
```

- Never run `docker compose down -v`: `-v` deletes the data.
- Docker Desktop is set to start at login. Turn that off (Settings → General → "Start Docker Desktop when you sign in") while you're not demoing, or the workers start again quietly.

## 3–4 days before

```bash
make demo-start       # database, search, cache, news fetcher, pipeline
make demo-status      # run any time: freshness and counts
```

- Keep Docker open and the Mac **plugged in and awake**: System Settings → Battery → Options → "Prevent automatic sleeping on power adapter when the display is off".
- **Articles** arrive every 15 minutes. Feeds only list the last day or two, so the gap while Lens was off isn't filled. Start early enough for a full front page.
- **AI summaries** are the slow part: the free Groq quota covers about 10–15 story analyses a day. Three or four days gives a few dozen stories with verified summaries and framing.
- **Healthy looks like:** "Newest article fetched" within the last 30 minutes, a few thousand articles in 24 hours, and "AI summaries, 24 h" going up day by day.
- **If the newest article stops moving:**
  1. Run `make ingest-logs`.
  2. A "Can't locate revision" error means the worker image is older than the database. Run `make ingest-up pipeline-up`.

## Interview day

**An hour before:**

1. Run `make demo-status` and check that the data is fresh.
2. Run `make demo-serve` for the API and the website (Ctrl+C stops both), then open http://localhost:3000.
3. Click through once to warm up. The first Ask takes a few extra seconds while the embedding model loads.
4. Check the Google sign-in (the Account menu should appear).
5. Don't use Ask much beforehand, to save the free quota for the demo.
6. Keep the README open in a tab as a backup (the GIFs show every feature): https://github.com/visheshbhargava0811/lens

**Suggested five-minute walkthrough:**

| Step | Show | Say |
|---|---|---|
| 1 | Home feed | "One story, many outlets. The bar shows who covered it, with confidence and a methodology link." |
| 2 | A story with a summary | "Every sentence is cited. Click a number to see the source. A separate model checks every sentence before it's published." |
| 3 | Scroll to "Where they differ" and "How headlines frame it" | "Framing across outlets and languages: Hindi and English coverage often lead with different angles." |
| 4 | Blindspot → By language | "Stories big in Hindi papers but barely in English ones, and the reverse." |
| 5 | Ask: "What did outlets report about <a current story>?" | "Retrieval is balanced across outlets. Unverifiable sentences are removed and listed. With weak coverage it abstains instead of guessing." |
| 6 | Ask a loaded question, e.g. "Why did X ruin the economy?" | "It takes the premise out of the question before searching." |
| 7 | Local, then the Account menu, then हिं | "Location stays on the device. Sign-in stores no email. The whole site works in Hindi." |

**Talking points if asked:**

- Evals gate CI: adversarial 1.00, benign false-block 0.00, citation presence 1.00.
- Guardrails are named and traced (`docs/07`).
- There's a kill switch for incidents.
- Everything runs on free tiers.

## After

```bash
make demo-stop
```
