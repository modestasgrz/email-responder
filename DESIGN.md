# AI Email Responder — Design Document

## Overview

Classifies Gmail inbox emails, drafts contextual replies for actionable ones, compiles a tech/business & music news digest from newsletters, and sends it via Telegram. Runs once daily as a Cloud Run Job.

**Portfolio claim:** "Reduced email response time from 4 hours to 15 minutes"

---

## Stack

| Component | Choice |
|---|---|
| Language | Python 3.12, strict mypy |
| Email | Gmail API (`google-api-python-client`) |
| LLM | Gemini 3 Flash (`google-genai`) |
| Messaging | Telegram Bot API (raw `httpx`) |
| Config | `pydantic-settings` + `.env` |
| Logging | `loguru` |
| Linting | `ruff` |
| Type checking | `mypy` (strict) |
| Testing | `pytest` |
| Deployment | GCP Cloud Run Jobs + Cloud Scheduler |
| Secrets | GCP Secret Manager |

---

## Pipeline

```
Run (triggered by Cloud Scheduler, once daily):

1. Fetch all unread Gmail messages
2. For each email → Classify (Gemini):
   ├─ spam         → mark read, label "AI/Spam", skip
   ├─ newsletter   → mark read, label "AI/Newsletter", extract news items → hold in memory
   ├─ support      → draft reply (Gemini) → save Gmail Draft → label "AI/Support" → mark read
   ├─ sales        → draft reply (Gemini) → save Gmail Draft → label "AI/Sales" → mark read
   └─ personal     → draft reply (Gemini) → save Gmail Draft → label "AI/Personal" → mark read
3. After all emails processed:
   └─ Compile held newsletter items → Gemini summarizes → Send digest via Telegram
4. Exit
```

---

## Project Structure

```
email-responder/
├── main.py                          # Entry point (one-shot execution)
├── src/
│   ├── __init__.py
│   ├── config.py                    # Settings from .env via pydantic-settings
│   ├── gmail/
│   │   ├── __init__.py
│   │   ├── client.py                # Gmail API auth, fetch, label ops, mark read
│   │   ├── models.py                # Email data models (Pydantic)
│   │   └── drafts.py                # Draft creation logic (MIME, threading)
│   ├── classifier/
│   │   ├── __init__.py
│   │   ├── classifier.py            # Gemini classification call
│   │   └── models.py                # Category enum, ClassificationResult model
│   ├── drafter/
│   │   ├── __init__.py
│   │   └── drafter.py               # Gemini draft generation call
│   ├── digest/
│   │   ├── __init__.py
│   │   ├── collector.py             # Accumulates newsletter items during batch
│   │   ├── summarizer.py            # Gemini call to compile digest from collected items
│   │   └── models.py                # NewsItem, DigestEntry models
│   ├── telegram/
│   │   ├── __init__.py
│   │   └── sender.py                # Telegram Bot API — send formatted message
│   └── pipeline.py                  # Orchestrator: fetch → classify → draft/collect → digest → send
├── tests/
│   ├── conftest.py                  # Shared fixtures
│   ├── gmail/
│   │   ├── __init__.py
│   │   ├── test_client.py
│   │   ├── test_models.py
│   │   └── test_drafts.py
│   ├── classifier/
│   │   ├── __init__.py
│   │   ├── test_classifier.py
│   │   └── test_models.py
│   ├── drafter/
│   │   ├── __init__.py
│   │   └── test_drafter.py
│   ├── digest/
│   │   ├── __init__.py
│   │   ├── test_collector.py
│   │   ├── test_summarizer.py
│   │   └── test_models.py
│   ├── telegram/
│   │   ├── __init__.py
│   │   └── test_sender.py
│   └── test_pipeline.py
├── pyproject.toml
├── Makefile
├── .env.example
├── Dockerfile                       # Production container image
└── DESIGN.md                        # This file
```

---

## Component Details

### - [ ] 1. `src/config.py` — Settings

Loads all configuration from `.env` via `pydantic-settings.BaseSettings`.

Fields:
- `gmail_credentials_path: str` — path to OAuth `credentials.json`
- `gmail_token_path: str` — path to `token.json` (auto-generated)
- `gemini_api_key: SecretStr` — Gemini API key
- `gemini_model: str` — model name (default: `gemini-2.0-flash`)
- `telegram_bot_token: SecretStr` — Telegram bot token from @BotFather
- `telegram_chat_id: str` — your personal Telegram chat ID
- `log_level: str` — loguru log level (default: `INFO`)

**Why pydantic-settings:** Type-safe config with validation at startup. Crashes early if a required var is missing.

**Discarded alternatives:**
- `python-dotenv` alone — no validation, no types, errors surface at runtime
- `dynaconf` — overkill (multi-env, vaults)
- Hardcoded constants — can't change without code change

---

### - [ ] 2. `src/gmail/client.py` — Gmail Client

Handles OAuth2 authentication and all Gmail API interactions.

Responsibilities:
- Authenticate via OAuth2 (interactive first run, auto-refresh after)
- Fetch unread emails (`users.messages.list` + `users.messages.get`)
- Mark emails as read (`users.messages.modify` — remove UNREAD label)
- Add labels to emails (`users.messages.modify`)
- Create labels if they don't exist (`users.labels.create`)

Auth flow: First run opens browser for Google consent, stores refresh token in `token.json`. Subsequent runs use refresh token silently. In Cloud Run, token is read from/written to Secret Manager.

**Discarded alternatives:**
- `simplegmail` — less maintained, hides API details
- IMAP/SMTP — no label support, no draft support
- `Nylas` — SaaS dependency, emails flow through third-party

---

### - [ ] 3. `src/gmail/models.py` — Email Models

Pydantic models representing email data.

```
Email:
  - message_id: str       # Gmail message ID
  - thread_id: str        # Gmail thread ID (for threaded draft replies)
  - sender: str           # From address
  - subject: str          # Subject line
  - body: str             # Plain text body (extracted from payload)
  - received_at: datetime # Internal date
```

**Why Pydantic:** Consistent with stack, runtime validation at construction.

**Discarded alternatives:**
- `dataclasses` — no runtime validation
- Raw dicts — no type safety
- `TypedDict` — static only

---

### - [ ] 4. `src/gmail/drafts.py` — Draft Creator

Creates Gmail Draft replies threaded to the original email.

Uses `users.drafts.create` with:
- `threadId` — threads draft under original conversation
- `In-Reply-To` and `References` headers — proper email threading
- `To` set to original sender

**Why separate from client.py:** Draft creation involves MIME encoding and header construction — different responsibility than raw API calls.

---

### - [ ] 5. `src/classifier/models.py` — Classification Models

```
EmailCategory (str, Enum):
  - SUPPORT
  - SALES
  - SPAM
  - NEWSLETTER
  - PERSONAL

EmailPriority (str, Enum):
  - HIGH
  - MEDIUM
  - LOW

ClassificationResult (BaseModel):
  - category: EmailCategory
  - priority: EmailPriority
  - summary: str           # One-line summary
  - needs_reply: bool      # Whether this email warrants a draft
  - reasoning: str         # Short explanation (for logging)
```

`needs_reply`: `True` for support/sales/personal, `False` for spam/newsletter. Gemini decides — e.g., a no-reply personal email gets `False`.

---

### - [ ] 6. `src/classifier/classifier.py` — Email Classifier

Single responsibility: `Email` → `ClassificationResult`.

System prompt defines 5 categories with examples. User message contains email (sender, subject, body). Gemini returns structured JSON matching `ClassificationResult`.

**Why Gemini structured output:** Guarantees schema match. No manual parsing or retries.

**Discarded alternatives:**
- Traditional ML (sklearn/spaCy) — needs training data, can't produce summaries
- Rule-based (regex) — brittle
- LangChain — unnecessary abstraction for a single LLM call
- `instructor` — less necessary with Gemini's native structured output

---

### - [ ] 7. `src/drafter/drafter.py` — Reply Drafter

Single responsibility: `Email` + `ClassificationResult` → draft reply `str`.

System prompt sets tone. Includes classification summary for context. Response is plain-text reply body.

Tone by category:
- **support** — helpful, solution-oriented
- **sales** — professional, not committal
- **personal** — warm, casual

**Discarded alternatives:**
- RAG with knowledge base — not needed for V1
- Template-based — can't adapt to content

---

### - [ ] 8. `src/digest/collector.py` — Newsletter Collector

Accumulates newsletter items during the batch run. Just an in-memory `list[NewsItem]` — no persistence needed since the entire run is one-shot.

For each newsletter email classified by the classifier:
1. Determine sub-category (from classifier metadata)
2. If tech/business → append to `tech_business` list
3. If music (SoundCloud, Bandcamp, etc.) → append to `music` list
4. If neither → append to `other` list

**Why in-memory:** One-shot execution means no need for a database. The list lives for the duration of the run.

**Discarded alternatives:**
- SQLite — persistence not needed for a single run
- Redis — external dependency for temporary data
- File-based — unnecessary I/O

---

### - [ ] 9. `src/digest/summarizer.py` — Digest Compiler

Takes collected newsletter items, sends them to Gemini, returns a formatted digest.

Each digest entry contains:
- **What:** One-liner of the news/tool/announcement
- **Why it matters:** One-liner of the problem it solves or introduces
- **User sentiment:** One-liner of community feedback temperature (if available)
- **Source:** Link to original source

Output format: structured text ready for Telegram (HTML-formatted).

Three sections in the digest:
1. **Tech & Business** — primary section
2. **Music** — SoundCloud, Bandcamp, and similar music industry/release news
3. **Other** — everything else

**Discarded alternatives:**
- Per-email summarization (no aggregation) — user wants a single compiled list
- Jinja2 templates — overkill, f-strings with HTML tags are sufficient

---

### - [ ] 10. `src/digest/models.py` — Digest Models

```
NewsItem (BaseModel):
  - headline: str          # What is happening
  - problem_or_impact: str # What problem it solves or introduces
  - user_sentiment: str    # Temperature of user feedback (if any)
  - source_url: str        # Original source URL
  - source_name: str       # Newsletter/publication name

NewsletterCategory (str, Enum):
  - TECH_BUSINESS
  - MUSIC
  - OTHER

DigestSection (BaseModel):
  - category: NewsletterCategory  # "Tech & Business", "Music", or "Other"
  - items: list[NewsItem]
```

---

### - [ ] 11. `src/telegram/sender.py` — Telegram Sender

Sends the formatted digest to your Telegram chat.

Implementation: raw `httpx.post()` to `https://api.telegram.org/bot<TOKEN>/sendMessage`.
- `chat_id` from config
- `parse_mode=HTML` for formatting (bold, italic, links)
- `disable_web_page_preview=True` to keep the message clean

Handles Telegram's 4096-char message limit by splitting into multiple messages if needed.

**Why raw httpx:** One HTTP call. No library needed for send-only.

**Discarded alternatives:**
- `python-telegram-bot` — full async framework, overkill for sending one message
- `aiogram` — async, overkill
- `requests` — legacy, no type stubs, `httpx` is the modern replacement
- WhatsApp (Meta Cloud API) — requires Business account, phone verification, costs money
- Slack webhooks — user doesn't live in Slack
- Discord — user doesn't live in Discord

---

### - [ ] 12. `src/pipeline.py` — Orchestrator

Coordinates the full one-shot flow. Stateless — receives dependencies via constructor injection.

```python
Pipeline.__init__(gmail_client, classifier, drafter, collector, summarizer, telegram_sender, config)
Pipeline.run() -> PipelineResult
```

Flow:
1. `gmail_client.fetch_unread()` → list of `Email`
2. For each email:
   a. `classifier.classify(email)` → `ClassificationResult`
   b. Route based on category:
      - spam → mark read, label
      - newsletter → `collector.add(email, classification)`, mark read, label
      - support/sales/personal → `drafter.draft()` → `gmail_client.create_draft()`, mark read, label
3. After all emails: `summarizer.compile(collector.items)` → digest text
4. `telegram_sender.send(digest)` (skip if no newsletter items)
5. Return `PipelineResult` (counts, errors, success)

**Why a separate pipeline module:** Keeps orchestration out of components. Each component testable in isolation.

**Discarded alternatives:**
- LangGraph state machine — overkill for linear flow
- Event-driven — overengineered for sequential processing
- Single function — harder to test, harder to extend

---

### - [ ] 13. `main.py` — Entry Point

Responsibilities:
- Load config
- Initialize Gmail client (triggers OAuth on first run)
- Initialize classifier, drafter, collector, summarizer, telegram sender
- Construct pipeline
- `pipeline.run()`
- Log summary and exit

One-shot execution. No polling loop. Cloud Scheduler handles scheduling.

**Why manual DI in main.py:** All wiring in one place. No framework needed. Every component receives deps via constructor — fully testable.

**Discarded alternatives:**
- `dependency-injector` — framework overhead for ~7 components
- Module-level singletons — hard to test
- Click/Typer CLI — no CLI args needed, everything in .env

---

## - [ ] Testing Strategy

All tests mock external services (Gmail API, Gemini API, Telegram API). No real API calls in tests.

| Test file | What it tests |
|---|---|
| `tests/gmail/test_client.py` | Auth flow, fetch parsing, label ops — mock `googleapiclient` |
| `tests/gmail/test_models.py` | Email model validation, edge cases |
| `tests/gmail/test_drafts.py` | MIME message construction, threading headers |
| `tests/classifier/test_classifier.py` | Gemini call + response parsing — mock `google-genai` |
| `tests/classifier/test_models.py` | Enum values, ClassificationResult validation |
| `tests/drafter/test_drafter.py` | Gemini call + prompt construction — mock `google-genai` |
| `tests/digest/test_collector.py` | Item accumulation, tech/biz vs other routing |
| `tests/digest/test_summarizer.py` | Gemini digest compilation — mock `google-genai` |
| `tests/digest/test_models.py` | NewsItem, DigestSection validation |
| `tests/telegram/test_sender.py` | HTTP call construction, message splitting — mock `httpx` |
| `tests/test_pipeline.py` | Full flow with mocked components, error handling, edge cases |

Fixtures in `conftest.py`:
- `sample_email` — realistic Email instance
- `sample_classification` — ClassificationResult for each category
- `sample_news_items` — list of NewsItem instances
- Mock factories for Gmail, Gemini, Telegram

---

## Labels Strategy

Auto-created Gmail labels:
- `AI/Support`
- `AI/Sales`
- `AI/Spam`
- `AI/Newsletter`
- `AI/Personal`

Labels created on first use if missing. Cached in-memory after creation.

---

## Error Handling

- **Config errors** — crash at startup with clear message (pydantic validation)
- **Auth errors** — crash with instructions to re-run OAuth flow
- **Single email failure** — log error, skip email, continue batch (stays unread → retried next run)
- **Gemini API error** — log, skip email, continue
- **Telegram send failure** — log error, don't crash (emails were still processed)
- **Gmail API quota** — log, fail gracefully

Principle: **never lose an email**. If processing fails, the email stays unread and gets retried next run.

---

## - [ ] Deployment

### Architecture

```
Cloud Scheduler (cron: daily) → triggers → Cloud Run Job → runs pipeline → exits
                                                ↓
                                         Secret Manager
                                    (API keys, OAuth token)
```

### GCP Free Tier Breakdown

| Component | Free Allowance | Our Usage |
|---|---|---|
| Cloud Run Jobs | 180k vCPU-sec/mo | ~60-300s × 1/day ≈ 1.8-9k/mo |
| Cloud Scheduler | 3 jobs free | 1 job |
| Secret Manager | 6 active versions | 3-4 secrets |
| Artifact Registry | 500MB | <200MB image |
| Cloud Build | 120 min/day | Build on deploy only |

**Monthly cost: $0** (excluding Gemini API calls)

### Deployment Commands

```bash
# Build and push image, then deploy the job
gcloud run jobs deploy email-responder --source . --region us-central1

# Create daily schedule (8 AM UTC)
gcloud scheduler jobs create http email-responder-daily \
  --schedule="0 8 * * *" \
  --uri="https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/..." \
  --http-method=POST
```

### OAuth Token in Cloud Run

Problem: Cloud Run filesystem is ephemeral — `token.json` doesn't persist between runs.

Solution:
1. First-time OAuth done locally (opens browser for consent)
2. Upload `token.json` content to Secret Manager
3. On Cloud Run startup: read token from Secret Manager
4. If token refreshed during run: write updated token back to Secret Manager

### Discarded Deployment Alternatives

- **Compute Engine f1-micro** — always-on VM for a 1x/day job is wasteful
- **Cloud Functions** — 9-min timeout limit could be tight with many emails
- **App Engine** — designed for web apps, not batch jobs
- **GitHub Actions cron** — poor secret persistence, OAuth token management is hacky

---

## Dependencies (pyproject.toml)

```
# Core
google-api-python-client    # Gmail API
google-auth-oauthlib        # OAuth2 flow for Gmail
google-auth-httplib2        # HTTP transport for auth
google-genai                # Gemini SDK
pydantic>=2.0               # Data models
pydantic-settings>=2.0      # Config from .env
loguru                      # Logging
httpx                    # Telegram Bot API calls

# Dev
ruff                        # Linting + formatting
mypy                        # Type checking
pytest                      # Testing
pytest-mock                 # Mocking utilities
```

---

## .env.example

```
GEMINI_API_KEY=your-gemini-api-key
GMAIL_CREDENTIALS_PATH=credentials.json
GMAIL_TOKEN_PATH=token.json
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
TELEGRAM_CHAT_ID=your-telegram-chat-id
LOG_LEVEL=INFO
```
