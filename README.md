<img width="1341" height="611" alt="image" src="https://github.com/user-attachments/assets/18d458ea-539e-4ffc-9a5d-2220b81322fb" /># OptiBot Mini-Clone

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

## ScreenShot
<img width="1197" height="737" alt="image" src="https://github.com/user-attachments/assets/a5d0b05a-2cf0-4d42-9214-eeb7ae110c8b" />
<img width="1496" height="883" alt="image" src="https://github.com/user-attachments/assets/50979b92-83e1-4cc8-a421-8e2221f4c985" />
<img width="1906" height="942" alt="image" src="https://github.com/user-attachments/assets/a29adbe2-8f05-406f-b0f7-4bd1e3f379c6" />
<img width="1877" height="912" alt="image" src="https://github.com/user-attachments/assets/2fe09c87-33f7-4296-a419-4dbfe74ebb87" />
<img width="1882" height="933" alt="image" src="https://github.com/user-attachments/assets/ae14d86e-5d82-4af4-be85-c90ab2a243e1" />



