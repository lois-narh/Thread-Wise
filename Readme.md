# ThreadWise

Analytics for tailoring businesses. It does more than count orders: it predicts which open orders will be late, shows what is causing the delays, and uses the Snwolley AI agent to turn those numbers into plain-English advice.

This project was inspired by a recent project i worked on (MeasureAI)[https://github.com/Ruwy123/Measure-AI]

## What it does
1. A business signs up and gets its own workspace.
2. Synthetic order data is generated (or a real shop's data could be loaded).
3. SQL cleans the data, checks its quality and answers business questions.
4. A model predicts which in-progress orders will miss their promised date, and why.
5. The Snwolley agent writes summaries and recommendations from those real numbers.
6. A report page shows KPIs, charts, risky orders and the AI summary, and can be downloaded.

## Quick start
Requires Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/Scripts/activate        
pip install -r requirements.txt
cp .env.example .env                
streamlit run app/main.py
```

In the app: create an account, click **Generate synthetic data**, then use the sidebar pages.



## Using the app
| Page | What it shows |
|---|---|
| Overview, Orders, Pending, Finances | Record-keeping and KPIs from SQL |
| Insights | Pick a business problem; SQL findings and data-quality checks |
| ML model | Model results vs a baseline, what drives late orders, open orders ranked by risk |
| AI insights | Ask Snwolley for a summary, three actions, or your own question |
| Report | Dashboard with an AI executive summary; download as Markdown |

## How it works
**Data.** One SQLite database per workspace (`data/workspaces/<id>.db`); accounts are in `data/threadwise.db`. Tables: customers, tailors, orders. The generator is `scripts/generate_data.py`; the same seed gives the same data. It includes missing values, duplicates, inconsistent spellings and impossible dates on purpose.

**SQL.** The `orders_clean` view removes duplicates, standardises text and drops impossible records. `sql/quality.sql` reports the problems found. `sql/features_late.sql` builds the model table using CTEs, a correlated subquery (how many orders each tailor already had open when an order was placed) and a window function (customer's previous orders).

**Machine learning** (`ml/pipeline.py`). Target: the order is delivered after its promised date. Features are known at order time (workload, deposit share, complexity, rush, fabric source, occasion, month, tailor skill and others). Three models are compared on the most recent 20% of orders: a baseline that guesses the overall late rate, logistic regression and gradient boosting. The best is retrained on all delivered orders and scores the open ones. Importance comes from permutation importance; the reasons shown per order come from swapping each feature for a typical value and measuring the drop in risk.

**AI** (`ai/`). `context.py` builds a small facts summary: aggregates, model results and open-order details, never customer names or phones. `insights.py` wraps it in rules (use only these facts, quote exactly, say when unsure) and sends it through `snwolley.py`. After each reply, any number not found in the facts is flagged in the app. Replies are cached, and the client respects the API's 5-requests-per-minute limit with a throttle and retry on HTTP 429. The API key is read from the environment only.

**Changing the business problem.** Problems are defined in `use_cases/*.json`. The ML pipeline is generic: it trains on whatever one SQL query returns (id, date, split, target, features). A new classification problem needs a new feature query, not new Python.

## Architecture
```
 Screens (Streamlit pages)      login, workspace, overview, ML model, AI insights, report
          
 Services (Python modules)      auth, SQL runner, ML pipeline, Snwolley client
                      
 SQLite + views      Snwolley API (external; receives numbers only)
```

## Scaling and monitoring
- **Larger data:** move SQLite to Postgres, run retraining as a scheduled job instead of on page load.
- **Streaming orders:** publish order events to Kafka, load them into the database, and score new orders as they arrive.
- **Monitoring:** compare each feature's current distribution to the training data (population stability index) to catch drift; log every prediction and track AUC once real outcomes arrive; retrain when either alarms. Grafana can chart these, and logs can go to Elasticsearch.

## Security
Passwords are stored as salted hashes. API keys come from `.env` and are not in the repository. Customer names and phones are never sent to the AI. Errors shown to users are generic; details go to the logs.

## Assumptions and limitations
- All data is synthetic. Its late-order patterns were planted by the generator, so the model finding them proves the pipeline works, not that real shops will look the same.
- The test period (most recent orders) contains no December, so the December effect is learned but not validated.
- The schema has no payments table, so "cash collected" is not tracked. The report uses value of delivered orders and deposits held on open orders instead.
- The ML pipeline currently covers late delivery only. Demand forecasting is defined as a use case with SQL analysis but has no model yet.
- Snwolley's response format is not documented; the client accepts the common shapes.
- No automated tests, no password reset, and login attempts are not rate-limited.

## With more time
Add a payments table, per-tailor capacity, probability calibration, a demand-forecast model, PDF export, automated tests, and a CSV upload for real shop data.