# Opponent Analysis API

## Purpose

`opponent-analysis` is a persisted multi-agent prediction workflow for courtroom attack-and-defense rehearsal.

It accepts:

- `case_facts`
- `top_k`
- optional `document_ids`

It returns:

- a persisted run record
- structured event history
- a structured summary for the board UI

All output must be rendered as prediction-oriented content such as "可能", "预测", and "建议".

## Endpoints

### `POST /api/v1/opponent-analyses`

Create a new opponent analysis run and queue background execution.

Request body:

```json
{
  "case_facts": "案情摘要",
  "top_k": 5,
  "document_ids": ["doc-1", "doc-2"]
}
```

Notes:

- `case_facts` cannot be blank after trimming
- `document_ids` must already exist and be vector-indexed
- empty `document_ids` means use all indexed documents

### `GET /api/v1/opponent-analyses`

List saved runs ordered by most recently updated first.

### `GET /api/v1/opponent-analyses/{run_id}`

Return:

- `run`
- `events`
- `summary`

### `GET /api/v1/opponent-analyses/{run_id}/stream?after_seq=0`

Server-sent event stream for live updates and replay resume.

Stream payloads:

- `snapshot`
- `event`
- `done`

`after_seq` allows continuation from the last received event sequence.

### `DELETE /api/v1/opponent-analyses/{run_id}`

Delete the run and its persisted event history.

## Workflow Phases

Current runtime uses a shared `context_brief` plus an isolated multi-agent dialogue loop.

- Each agent has its own inbox and private memory.
- Agents can choose one or more recipients on each turn.
- Initial turns usually cover `party_projection`, `counsel_projection`, `bench_review`, and `strategy_response`.
- Follow-up turns are persisted under `revision`.
- The run ends with `finalize`.

## Event Model

Each event includes at least:

- `seq`
- `phase`
- `round`
- `from_agent`
- `to_agent`
- `event_type`
- `title`
- `content`
- `structured_payload`
- `citations`
- `status`
- `created_at`

Supported `event_type` values:

- `stage`
- `agent_message`
- `agent_revision`
- `evidence`
- `summary`
- `error`

## Summary Shape

The board should consume only the structured summary:

- `opponent_position`
- `lawyer_predictions`
- `party_predictions`
- `response_plan`
- `evidence_index`
- `risk_level`

## Implementation Map

Backend files:

- `backend/src/app/api/routes/opponent_analyses.py`
- `backend/src/app/models/opponent_analysis.py`
- `backend/src/app/schemas/opponent_analysis.py`
- `backend/src/app/services/opponent_analysis/`

Frontend files:

- `frontend/app/pages/opponent-analysis.vue`
- `frontend/stores/opponentAnalysis.ts`

## Verification

Targeted backend tests:

```bash
uv run --directory backend pytest tests/test_opponent_analysis_api.py
```

Frontend checks:

```bash
pnpm --dir frontend exec nuxi typecheck
pnpm --dir frontend run build
```
