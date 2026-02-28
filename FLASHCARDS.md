# Flashcards Feature Overview

## What it does
Summarizes recent parsed papers per arXiv category (cs.AI, cs.LG, cs.CV, cs.CL, cs.RO, cs.SY) into small “flashcards” (headline, insight, why-it-matters) and serves them via API/Streamlit.

## Data source
- Uses `papers` table (parsed PDFs) filtered by category and `pdf_processed=True`, ordered by `published_date`.

## Pipeline
1) Request arrives at `GET /api/v1/flashcards/?category=...&limit=...&refresh=...`.
2) Repository checks cached flashcards in Postgres (`flashcards` table) that are fresh (`expires_at > now`).
3) If missing/stale or `refresh=true`:
   - Fetch recent papers for that category.
   - For top candidates, call NVIDIA NIM LLM (OpenAI-compatible) to summarize into flashcards.
   - Store 5 cards (default) with TTL (24h) in `flashcards` table.
4) Return DTOs to client; Streamlit page renders them in a two-column grid.

## Storage
- Table: `flashcards` (created by `alembic/versions/0003_add_flashcards_table.py`).
- Key fields: `category`, `arxiv_id`, `headline`, `insight`, `why_it_matters`, `summary_json`, `generated_at`, `expires_at`.
- Unique constraint: `(category, arxiv_id)`.
- TTL: 24 hours; expired rows can be cleaned with `DELETE FROM flashcards WHERE expires_at < now()`.

## Services & components
- `src/services/flashcards.py`: Orchestrates retrieval, regeneration, cleaning text, and JSON-safe storage.
- `src/repositories/flashcards.py`: DB access, fresh lookup, upsert with ON CONFLICT, expired cleanup.
- `src/routers/flashcards.py`: API endpoints (`GET /flashcards`, `DELETE /flashcards/expired`).
- `src/services/nvidia/client.py`: `summarize_for_flashcard` helper used under the hood.
- `frontend/pages/flashcards.py`: Streamlit UI for browsing/refreshing cards.

## How to run
1) Build and start:
   ```bash
   docker compose build api frontend
   docker compose up -d
   ```
   The API entrypoint runs `alembic upgrade head`, creating the flashcards table.
2) Open Streamlit: http://localhost:8501 → Flashcards page (category selector, optional refresh).
3) API example: `curl "http://localhost:8000/api/v1/flashcards/?category=cs.AI&limit=5&refresh=true"`.

## Troubleshooting
- 500 with JSONB insert: ensure `summary_json` is datetime-free (fixed in `src/services/flashcards.py`); if old bad rows exist, clear them:
  ```bash
  docker compose exec postgres bash -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DELETE FROM flashcards;"'
  ```
- If table missing: `docker compose exec api alembic upgrade head`.
- Rate limits: NIM calls are throttled (rpm cushion); TTL caching avoids repeated calls.

## Customization knobs
- TTL: change `DEFAULT_TTL_HOURS` in `src/services/flashcards.py`.
- Cards per request: `limit` query param (1–10).
- Categories: controlled in `frontend/config.py` and API input.
