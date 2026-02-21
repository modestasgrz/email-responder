# Email Responder

An AI-powered Gmail inbox manager that runs daily as a scheduled GCP Cloud Run Job. It classifies every unread email, drafts replies for ones that need them, compiles a newsletter digest, and sends a full pipeline report to Telegram — all without touching your inbox manually.

> **Platform note:** Developed and tested on Apple Silicon (macOS). Other platforms are untested — Makefile deployment commands (particularly the Docker `--platform` flag) may need adjusting for your system.

---

## How it works

```
Fetch unread emails from Gmail
  → Classify each email (Gemini) → one of: support / sales / spam / newsletter / invoice / personal / unknown
      spam         → label AI/Spam,        mark read,   skip
      newsletter   → label AI/Newsletter,  mark read,   collect for digest
      invoice      → label AI/Invoice,     leave unread (action required)
      unknown      → label AI/Unknown,     leave unread (manual review)
      support \
      sales    |   → label,                mark read,   draft reply (Gemini) if needs_reply
      personal /
  → Compile newsletter digest (one Gemini call for all collected newsletters)
  → Send digest + pipeline report to Telegram
```

![Pipeline report message](screenshots/pipeline-report.png)
![Telegram digest message](screenshots/telegram-digest.png)

---

## Prerequisites

Install these before anything else:

| Tool | Install |
|---|---|
| **Python 3.12+** | https://www.python.org/downloads/ |
| **uv** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Docker Desktop** | https://www.docker.com/products/docker-desktop — must be running during deploys |
| **gcloud CLI** | https://cloud.google.com/sdk/docs/install |

After installing gcloud, authenticate:
```bash
gcloud auth login
gcloud auth application-default login
```

Both open a browser — log in with your Google account.

---

## First-time setup

### Step 1 — Gemini API key

1. Go to https://aistudio.google.com
2. Click **Get API key** → **Create API key**
3. Copy and save the key

---

### Step 2 — Telegram bot + chat ID

**Create a bot:**
1. Open Telegram, search for `@BotFather`
2. Send `/newbot`, follow the prompts (name + username ending in `bot`)
3. Copy the bot token it gives you — looks like `7312456789:AAF...`

**Get your chat ID:**
1. Send your new bot any message (e.g. `hi`)
2. Open in a browser: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. Find `"chat":{"id":123456789}` — that number is your chat ID

---

### Step 3 — GCP project

1. Go to https://console.cloud.google.com
2. Project dropdown → **New Project** → name it → **Create**
3. Left sidebar → **Billing** → link a billing account (required even on free tier)
4. Copy your **Project ID** from the dashboard (e.g. `email-responder-123456`)

Point gcloud at it:
```bash
gcloud config set project YOUR_PROJECT_ID
```

---

### Step 4 — Enable GCP APIs

```bash
gcloud services enable \
  gmail.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com
```

Takes ~1 minute.

---

### Step 5 — Gmail OAuth credentials

This allows the app to access your Gmail inbox.

1. GCP Console → **APIs & Services** → **OAuth consent screen**
2. User type: **External** → **Create**
3. Fill in app name, support email, developer email (all can be your Gmail) → **Save and Continue** through all steps
4. On the **Test users** step → **Add Users** → add your Gmail address
5. **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
6. Application type: **Desktop app** → **Create**
7. **Download JSON** → rename to `credentials.json` → place in the project root

---

### Step 6 — Configure environment

```bash
cp .env.example .env
```

Fill in `.env`:

```
GEMINI_API_KEY=AIza...          # From step 1
TELEGRAM_BOT_TOKEN=7312...      # From step 2
TELEGRAM_CHAT_ID=123456789      # From step 2
```

Leave `GMAIL_CREDENTIALS_PATH`, `GMAIL_TOKEN_PATH`, `LOG_LEVEL` at their defaults.

---

### Step 7 — Generate token.json

Install dependencies and run the login script — this triggers the Gmail OAuth browser flow without touching your inbox:

```bash
uv sync
uv run python login.py
```

A browser window opens → log in with Gmail → click **Allow**. Once done, `token.json` appears in the project root and you're ready to deploy.

---

### Step 8 — Upload secrets to GCP

```bash
make secrets-create   # uploads .env values + credentials.json + token.json to Secret Manager
make secrets-iam      # grants Cloud Run permission to read those secrets
```

One-time only.

---

### Step 9 — Create Artifact Registry repo

```bash
make gcp-setup
```

Creates a Docker image registry in your GCP project and configures Docker authentication.

---

### Step 10 — Deploy

```bash
make deploy
```

Builds the Docker image, pushes to Artifact Registry, deploys as a Cloud Run Job with all secrets wired up. Takes 2–4 minutes.

---

### Step 11 — Test run

```bash
make run
```

Triggers the job immediately and waits for it to finish. A Telegram message should arrive with the pipeline report.

To inspect logs: GCP Console → **Cloud Run** → **Jobs** → `email-responder` → **Executions** → click an execution → **Logs** tab.

---

### Step 12 — Schedule daily runs

```bash
gcloud scheduler jobs create http email-responder-daily \
  --location=us-central1 \
  --schedule="0 8 * * *" \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/YOUR_PROJECT_ID/jobs/email-responder:run" \
  --oauth-service-account-email="$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')-compute@developer.gserviceaccount.com" \
  --message-body="{}"
```

Replace `YOUR_PROJECT_ID` twice. The schedule `0 8 * * *` runs every day at 8am UTC — adjust to your timezone using standard cron syntax.

Then grant Cloud Scheduler permission to trigger the job:
```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:$(gcloud projects describe YOUR_PROJECT_ID --format='value(projectNumber)')-compute@developer.gserviceaccount.com" \
  --role="roles/run.invoker"
```

---

## Re-deployment

After any code change:
```bash
make deploy
```

That's it — rebuilds the image and redeploys.

---

## Local development

```bash
uv sync --extra dev   # install dev dependencies
make check            # ruff lint + mypy type check
make fix              # ruff autofix
make test             # full test suite
```

Run a single test:
```bash
uv run pytest tests/path/to/test_file.py::test_name -s
```

---

## Configuration reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | Yes | — | Google AI Studio API key |
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | — | Your personal Telegram chat ID |
| `GMAIL_CREDENTIALS_PATH` | No | `credentials.json` | Path to OAuth credentials file |
| `GMAIL_TOKEN_PATH` | No | `token.json` | Path to OAuth token file |
| `GEMINI_MODEL` | No | `gemini-3-flash-preview` | Gemini model used for all LLM calls |
| `LOG_LEVEL` | No | `INFO` | Loguru log level (`DEBUG`, `INFO`, `ERROR`) |

---

## Troubleshooting

**Telegram messages not arriving**
- Check logs for `Telegram API error` — the full response body is logged before the exception
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are correct and have no trailing whitespace in Secret Manager
- Send your bot a message first — bots can't initiate conversations until you do

**Gemini 503 UNAVAILABLE**
- Transient overload — the app retries automatically up to 4 times with exponential backoff (4s → 60s cap)
- If all retries fail, the email stays unread and will be retried on the next scheduled run

**Gmail token expired**
If you revoked access or the token stops working:
1. Delete local `token.json`
2. Run `uv run python login.py` locally — completes the OAuth flow and regenerates it
3. Upload the new token:
```bash
gcloud secrets versions add gmail-token --data-file=token.json
```

**Docker platform issues (non-Apple Silicon)**
The Makefile uses `--platform linux/amd64` in the build command. If you're on a different architecture, you may need to adjust or remove this flag in the `Makefile`.

**Viewing logs**
GCP Console → Cloud Run → Jobs → `<YOUR PICKED GCP PROJECT NAME (e.g. email-responder)>` → Executions → click any execution → Logs tab.

Or via CLI:
```bash
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=<YOUR PICKED GCP PROJECT NAME (e.g. email-responder)>" \
  --limit=50 --format="value(textPayload)"
```
