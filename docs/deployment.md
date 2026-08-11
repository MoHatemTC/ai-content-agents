# Deployment Guide

How to configure and run Content Agents — the review platform in particular —
outside a developer's checkout. Written for whoever deploys or demos it next.

---

## 1. Requirements

- **Python 3.10+** (developed and tested on 3.14)
- No system packages. Every dependency is pure Python or ships wheels; the PDF
  exporter uses `fpdf2` specifically to avoid a system PDF toolchain.
- Roughly 500 MB of disk for the virtual environment, mostly `chromadb`.
- Network access **only** for the LiteLLM gateway, and for a one-time ~80 MB
  embedding-model download unless you set `RETRIEVAL_EMBEDDER=hashing`.

```bash
python -m venv .venv
.venv\Scripts\activate         # Windows
source .venv/bin/activate      # macOS / Linux

pip install -r requirements.txt
```

---

## 2. Configuration

All configuration is environment variables, read from a `.env` file at the project
root. Copy the template and fill it in:

```bash
copy .env.example .env         # Windows
cp .env.example .env           # macOS / Linux
```

| Variable | Default | What it does |
|---|---|---|
| `LITELLM_BASE_URL` | — | Gateway base URL. **Required.** Any OpenAI-compatible endpoint works — the Sprints LiteLLM gateway or OpenRouter (`https://openrouter.ai/api/v1`) have both been run against. |
| `LITELLM_API_KEY` | — | Gateway key. **Required.** |
| `DEFAULT_MODEL` | `kimi-k2.5` | Model name to request from the gateway. |
| `RETRIEVAL_EMBEDDER` | `onnx` | Which embedder indexes and queries documents. `onnx` is semantic and downloads ~80 MB once; `hashing` is offline and deterministic. Not interchangeable on an existing index — switching means re-ingesting, and opening an index built by the other one is refused. |
| `PLATFORM_DB_PATH` | `ingestion.db` | SQLite file holding documents, chunks, runs, outputs, reviews and events. |

**`.env` is the first line of `.gitignore` and must stay that way.** `*.db` is
ignored too, so the database never lands in a commit. Never put a real key in
`.env.example`.

To discover which models a gateway actually serves:

```python
from openai import OpenAI

client = OpenAI(api_key=..., base_url=...)
print([m.id for m in client.models.list().data])
```

---

## 3. Running

```bash
# The review, history, export and metrics UI
streamlit run src/validation/ui.py

# The combined study-assistant app (other lanes)
streamlit run src/app.py

# Batch generation over the demo dataset, then the quality report
python -m src.validation.automation                 # live
python -m src.validation.automation --offline       # no API calls
python -m src.validation.automation --limit 1 --agents mentor
```

`streamlit run` binds `localhost:8501` by default. For a shared demo:

```bash
streamlit run src/validation/ui.py \
  --server.address 0.0.0.0 --server.port 8501 --server.headless true
```

The UI and the CLI share state through `PLATFORM_DB_PATH`, so a batch run shows up
in the Review queue immediately. Point both at the same file.

---

## 4. Data and state

Everything lives in one SQLite file:

| Table | Owner | Contents |
|---|---|---|
| `documents`, `chunks` | ingestion lane | uploaded material |
| `agent_runs` | this lane | one row per agent invocation, including failures |
| `generated_outputs` | this lane | one row per artifact, with its verdict and status |
| `reviews` | this lane | append-only human audit trail |
| `system_events` | this lane | operational log |

Tables are created on first use with `CREATE TABLE IF NOT EXISTS`, so there is no
migration step and either store may initialise the file first.

**The Chroma retrieval index is in-memory and dies with the process.** Re-ingest
documents after a restart, or set `RetrievalConfig.persist_directory` to make it
durable — that is open work in the retrieval lane. The SQLite data does survive
restarts.

Back up by copying the `.db` file while the app is stopped.

---

## 5. Health checks

```bash
# Everything green? Live tests skip without a key rather than failing.
python -m pytest tests/ -q

# Is the gateway actually reachable?
RUN_LIVE_TESTS=true python -m pytest tests/test_question_bank_live.py -v

# Does the pipeline work end to end with no network at all?
python -m src.validation.automation --offline --limit 1
```

That last command is the most useful single check: if it prints a batch report,
ingestion, retrieval, orchestration, validation, persistence and evaluation are all
working.

---

## 6. Troubleshooting

**`500 ... AzureException APIConnectionError ... Received Model Group=<model>`**
The gateway authenticated you but cannot reach its own backend. This is upstream,
not configuration — `client.models.list()` will still succeed while every
completion fails. Confirm with a direct `curl`, then contact whoever runs the
gateway. The platform records these as failed `agent_runs`, so they show up in
History rather than crashing a batch.

**`TypeError: 'NoneType' object is not subscriptable` from an agent.**
The gateway returned **HTTP 200 carrying an error payload** — OpenRouter does this
when the backing provider is saturated:

```json
{"choices": null,
 "error": {"message": "Upstream error from Nvidia: ResourceExhausted:
            Worker local total request limit reached (32/32)", "code": 502}}
```

Because the status is a success the SDK does not raise, and `_call_llm`'s
`response.choices[0]` dereferences `None`. The orchestrator translates this into
`UpstreamResponseError` and retries it, since it is transient — retrying the same
prompt normally succeeds within a few attempts. Persisting across many retries
means the provider is genuinely out of capacity: switch model, or wait.

**Reasoning models and JSON output.** Some models (e.g. Nemotron) emit their
chain-of-thought into `message.content`. The agent prompts demand bare JSON, so
such a model can produce prose that fails the schema check — which the platform
records as a flagged output rather than a crash. If schema pass rate is
unexpectedly low, look at `payload["raw_output"]` on a failed output before
blaming the prompt.

**`Cannot reach the LLM gateway: LITELLM_API_KEY and LITELLM_BASE_URL are not
both set`**
There is no offline mode to fall back to; set both. The app degrades rather
than crashing — upload, the library and the review queue keep working, and the
generation pages say what is missing.

**Live tests skip.** Expected without `LITELLM_API_KEY`. They skip rather than
falling back to mocks on purpose — a green integration test that never called a
model would be misleading.

**Retrieval finds nothing after changing `RETRIEVAL_EMBEDDER`.** Vectors from
one embedder are not comparable to another's. Opening an index built by the
other embedder raises `IndexEmbedderMismatchError` naming both and telling you
to re-ingest; nothing is rebuilt automatically, because embedding a large
document costs minutes.

**Two Chroma indexes see each other's chunks.** `EphemeralClient` is shared per
process; give each index a distinct `collection_name`.

**`ExportBlockedError` on export.** Working as designed — the output has not been
approved. Approve it on the Review page first.

---

## 7. Security notes

- Secrets live only in `.env`. Nothing reads a key from code or from the database.
- There is **no authentication** on the Streamlit UI: anyone who can reach the port
  can approve content. Do not bind it to a public address without putting an
  authenticating proxy in front.
- The reviewer name is self-declared and recorded verbatim; it is an audit label,
  not an identity claim.
- Uploaded material and generated content are stored unencrypted in SQLite. Treat
  the `.db` file as sensitive as the material that went into it.
