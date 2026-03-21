# Argus

**AI safety & evaluation research daily digest — delivered to your inbox every morning.**

Argus monitors arXiv, Semantic Scholar, HuggingFace Papers, Reddit, and researcher blogs for the latest work on AI safety, alignment, evaluations, interpretability, and governance. It filters for relevance with Claude Haiku, generates a structured digest with Claude Sonnet, and delivers it via email + a committed Markdown file.

---

## Quickstart (5 minutes)

1. **Fork this repo** on GitHub
2. Go to **Settings → Secrets and variables → Actions** and add your secrets (see table below)
3. Go to **Actions → Daily Digest → Run workflow** to trigger your first digest
4. Check the `digests/` folder for your output

That's it. GitHub Actions runs the pipeline every day at 7am UTC automatically.

---

## Required Secrets

| Secret | Required | Where to get it |
|--------|----------|-----------------|
| `ANTHROPIC_API_KEY` | **Yes** | [console.anthropic.com](https://console.anthropic.com) |
| `RESEND_API_KEY` | Email | [resend.com](https://resend.com) (free tier: 3000/mo) |
| `DIGEST_EMAIL_TO` | Email | Comma-separated list of recipient addresses |
| `REDDIT_CLIENT_ID` | Reddit | [reddit.com/prefs/apps](https://reddit.com/prefs/apps) |
| `REDDIT_CLIENT_SECRET` | Reddit | Same app page |
| `SLACK_WEBHOOK_URL` | Slack | Slack app incoming webhook |

**Minimum viable setup:** only `ANTHROPIC_API_KEY`. The digest is committed to the `digests/` folder even without email.

---

## Estimated Cost

| Without Twitter | ~$1–2/month |
|---|---|
| Claude Haiku filtering | ~$0.003/day |
| Claude Sonnet summarization | ~$0.05/day |
| Email (Resend free tier) | Free |

---

## Changing the Schedule

Edit `.github/workflows/daily_digest.yml`:

```yaml
- cron: "0 7 * * *"   # 7am UTC (default)
# - cron: "0 13 * * *"  # 8am EST
# - cron: "0 17 * * *"  # 9am PST
```

---

## Local Development

```bash
git clone https://github.com/your-username/argus
cd argus
cp .env.example .env   # fill in your API keys
pip install -e ".[all]"

make fetch     # test fetchers only
make digest    # run full pipeline locally (no git push, no email)
make test      # run test suite
```

---

## Adding a Source

1. Create `argus/fetchers/my_source_fetcher.py` extending `BaseFetcher`
2. Implement `async def fetch(self) -> list[RawItem]`
3. Add it to `_fetch_all()` in `argus/runner.py`

---

## Customizing the Digest

- **Filter threshold**: change `filter.threshold` in `config/sentinel.yaml`
- **RSS feeds**: add/remove entries in `config/rss_feeds.yaml`
- **Digest template**: edit `templates/digest.md.jinja2`
- **Summarizer prompt**: edit `SYSTEM_PROMPT` in `argus/pipeline/summarizer.py`

---
