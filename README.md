# OptiBot Mini-Clone

Python 3.12 pipeline that scrapes OptiSigns Help Center articles through the Zendesk API, converts them to Markdown, detects changed articles by SHA256, and uploads deltas to an OpenAI vector store-backed assistant when an API key is provided.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.sample .env
```

Set `OPENAI_API_KEY` in `.env` for upload. `API_KEY` is only a fallback alias for the Docker take-home command; leave it blank if `OPENAI_API_KEY` is set. Leave `OPENAI_ASSISTANT_ID` blank on the first successful upload; the app creates the assistant and prints/logs the generated `asst_...` ID. Use `OPENAI_ASSISTANT_MODEL=gpt-4o-mini` for the Assistants API path.

## Run Locally

```bash
python run.py --log-json
python run.py --ask "How do I add a YouTube video?"
```

The sync writes Markdown to `data/markdown/`, updates `data/state.json`, and logs `added`, `updated`, `skipped`, `deleted`, uploaded file count, and estimated chunks. Docker path:

```bash
docker build -t main.py .
docker run -e API_KEY=... main.py
```

## Daily Job Logs

Railway cron is configured in `railway.json` for `0 3 * * *`. Local run artifacts are in [`data/logs/`](data/logs/); 

Chunking strategy: 900 tokens with 120 token overlap, chosen to keep support steps together while preserving context across chunks. Delta detection hashes normalized Markdown and uploads only `added` or `updated` files.



