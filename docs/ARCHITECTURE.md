# ThreadWise: architecture note

## What it is
A Streamlit app where a tailoring business signs up, loads order data, and gets SQL analysis, a late-order prediction model, and AI-written advice from the Snwolley agent.

## Components
```
 Screens (Streamlit)     app/main.py, app/analysis.py
        |
 Services (Python)       auth, workspace, usecases, SQL runner, ML pipeline, Snwolley client
     |                       |
 SQLite + views         Snwolley API (external service; receives numbers only)
```
| Part | Where | Job |
|---|---|---|
| UI | `app/main.py`, `app/analysis.py` | Login, sidebar pages, charts, report download |
| Accounts | `data/threadwise.db` | Users and their workspace |
| Workspace data | `data/workspaces/<id>.db` | One SQLite file per business; tables plus the `orders_clean` view |
| SQL layer | `sql/*.sql` | Cleaning, data-quality checks, KPIs, analysis, model features |
| Use cases | `use_cases/*.json` | Defines each business problem; selecting one changes the SQL and KPIs shown |
| ML pipeline | `ml/pipeline.py` | Generic: trains on whatever one feature query returns |
| AI layer | `ai/context.py`, `insights.py`, `snwolley.py` | Builds safe context, prompts the agent, checks the answer |
| Reporting | Report page, `docs/`, `notebooks/` | Dashboard, Markdown export, analysis notebook |

## Data flow
1. User signs up; a workspace database is created.
2. Synthetic data is generated (seeded, reproducible).
3. SQL cleans the data and produces KPIs and findings.
4. `features_late.sql` builds one row per order; the pipeline trains, tests on the most recent orders, and scores open orders.
5. `context.py` condenses results into a small facts summary; the agent turns it into advice.
6. The Report page shows KPIs, charts, risky orders and the AI summary.

## Security
- API key is read from `.env` (git-ignored); `.env.example` holds placeholders only. The key never reaches the browser.
- Passwords are stored as salted hashes. Login errors do not reveal whether an email exists.
- Customer names and phones are never read when building AI context. Only aggregates and open-order attributes are sent.
- AI controls: prompt rules (use only supplied facts, quote exactly, say when unsure); after each reply, any figure not present in the facts is flagged to the user; questions are length-capped; replies are cached.
- SQL runs from files in the repository, never from user text.
- Workspaces are separate database files, so one business cannot query another's data.

## Reliability
- Validation on signup and login; clear messages instead of stack traces for AI failures (missing key, 401, 429, timeout).
- The Snwolley client enforces the 5-requests-per-minute limit with a throttle and retries on HTTP 429 using the Retry-After value.
- Modules log through Python's `logging`; configuration is separate from code.
- The model retrains automatically when the workspace database changes.

## Scaling
| Need | Step |
|---|---|
| More data or users | SQLite to PostgreSQL, one schema per workspace |
| Retraining without blocking the UI | Scheduled job (cron/Airflow); the app loads the saved model |
| Orders arriving continuously | Publish order events to Kafka, load into the database, score new orders on arrival |
| Operational dashboards | Grafana over model and data-quality metrics |
| Search and log analysis | Elasticsearch for order search and application logs |
| Other systems | Expose scoring and insights through an API |

## Monitoring
- **Data drift:** population stability index per feature, recent orders vs training data (demonstrated in the notebook). Over 0.25 means investigate or retrain.
- **Performance:** log every prediction; compute ROC-AUC and top-20% capture as real delivery outcomes arrive.
- **AI quality:** track how often the unsupported-figure check fires.
- **Operations:** API error rates, 429 counts, retraining duration.

## Trade-offs
SQLite and Streamlit were chosen for speed of delivery and a self-contained demo. They do not scale to many concurrent users. The ML pipeline is generic, but only the late-delivery problem has a feature query so far.