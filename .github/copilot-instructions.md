## Purpose
Provide concise, repository-specific guidance so an AI coding agent can be productive immediately.

## Big picture
- Backend: Django project in `carbonlens/` with the `api` app handling REST endpoints and LLM orchestration.
- Frontend: the React Vite app under `carbon-lens-insights/` is the primary public UI.
- Data: OWID CO2 CSV at `data/owid-co2-data.csv` (downloadable via `scripts/download_owid_data.py`).
- LLMs: provider abstraction in `api/llm_provider.py`; Gemini is the active provider (see `api/gemini_client.py`). OpenAI integration is present but mostly disabled/commented (`api/openai_service.py`).

## Key integration points (read before edits)
- `api/llm_provider.py`: enforces async API and returns dict-shaped results. Any change to LLM calls must preserve async/await guarantees here.
- `api/gemini_client.py`: provider implementation using `google.generativeai`. Returns structured dicts; follow its error/return conventions.
- `api/openai_service.py`: large, commented OpenAI logic used as reference for prompts and sanitization; do not re-enable without checking `carbonlens/llm_settings.py` and environment variables.
- `api/execution_layer.py`: deterministic, pandas-driven execution. All data aggregation and column-mapping logic lives here — keep LLMs out of this layer.
- `carbonlens/llm_settings.py` and `carbonlens/settings.py`: where provider selection and API keys are configured. Changes here affect runtime provider selection and may raise errors if keys are missing.

## Developer workflows & commands
- Setup (local, recommended):
  - `python3 -m venv venv && source venv/bin/activate`
  - `pip install -r requirements.txt`
  - `cp .env.example .env` and populate API keys (optional: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `NEWS_API_KEY`).
  - `python scripts/download_owid_data.py`
  - `python manage.py migrate`
- Run services locally:
  - Django API: `python manage.py runserver` (port 8000)
  - use `carbon-lens-insights/`)
  - React frontend (dev): `cd carbon-lens-insights && npm install && npm run dev`
- Docker: `docker-compose up --build` (see README quickstart for recommended flow).
- Tests: `python manage.py test` (unit tests live under `api/` — run focused tests when possible).

## Project-specific conventions & patterns
- Layered design: separate concerns into small layers: intent extraction, validation, deterministic execution, LLM orchestration. Follow existing file layout in `api/` (e.g., `intent_extraction_layer.py`, `validation_layer.py`, `execution_layer.py`).
- LLM responses: code expects provider returns to be dicts with `success` and `response` keys; preserve that shape.
- Async rule: All Gemini/OpenAI calls are handled asynchronously in provider wrappers — do not call async functions from synchronous code without proper awaiting and bridging.
- Deterministic execution: `ExecutionLayer` must remain free of LLM-side effects — its logic relies on OWID column name patterns (see `_get_column_name`).
- Prompting conventions: prompts are built inside service modules (see `openai_service.py` for examples). If adding prompts, mirror their strict sanitization rules (e.g., JSON-only or plain strings when expected).

## When editing LLM/provider code — checklist
1. Update `carbonlens/llm_settings.py` for new provider defaults and environment variables.
2. Add a provider client in `api/` (follow `gemini_client.py` pattern). Keep initialization lazy and safe for Django startup.
3. Wire provider into `api/llm_provider.py` and ensure `generate()` returns a dict with `success` and `response`.
4. Keep provider calls async; add sync wrappers only when strictly necessary.
5. Add unit tests under `api/` that assert return-shape and error handling.

## Debugging tips
- Health endpoint: `GET /api/health/` to confirm backend and data load.
- Check `data/owid-co2-data.csv` path (configured by `OWID_DATA_PATH` in `carbonlens/settings.py`).
- If LLM features fail, inspect `GEMINI_API_KEY` / `OPENAI_API_KEY` presence and logs — `gemini` is preferred in code.


## Files to read first for context
- `README.md` (project overview and quickstart)
- `carbonlens/settings.py`, `carbonlens/llm_settings.py` (config)
- `api/llm_provider.py`, `api/gemini_client.py`, `api/openai_service.py`
- `api/execution_layer.py`, `api/schema.py` (data model + execution rules)
- `carbon-lens-insights/src/` (front-end usage patterns)

## Quick examples (follow these patterns)
- Provider call (observe async/dict pattern): see `api/llm_provider.py` and `api/gemini_client.py`.
- Deterministic queries: `ExecutionLayer.execute(intent)` returns `ExecutionResult` with `value`, `unit`, `applied_filters` — mirror this shape in any consumer code.

If anything here is unclear or you'd like me to expand a section (examples, test templates, or commit-ready PR text), tell me which part to iterate on.
