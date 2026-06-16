# Evaluations

This folder contains evaluation utilities that are separate from the backend
runtime dependencies.

## BFCL ReAct Agent Subset

Install evaluation-only dependencies:

```bash
cd /Users/yewen/finance_helpers/finance_tech
.venv/bin/pip install -r evaluations/requirements.txt
```

Run the default BFCL subset:

```bash
.venv/bin/python -m evaluations.bfcl_agent_eval.cli run \
  --config evaluations/configs/bfcl_subset.json \
  --output-dir evaluations/results/react_agent_bfcl_subset
```

Run a smaller subset while iterating:

```bash
.venv/bin/python -m evaluations.bfcl_agent_eval.cli run \
  --categories simple_python,irrelevance \
  --limit 10
```

Generated reports are written to `evaluations/results/`, which is intentionally
ignored by git.

## Ragas RAG Evaluation

Install evaluation-only dependencies:

```bash
cd /Users/yewen/finance_helpers/finance_tech
.venv/bin/pip install -r evaluations/requirements.txt
```

Generate reusable cases from uploaded files:

```bash
.venv/bin/python -m evaluations.ragas_rag_eval.cli generate \
  --source-paths backend/uploads \
  --case-count 30 \
  --output evaluations/datasets/ragas_generated_cases.jsonl
```

Generate cases in small batches when the LLM endpoint is unstable:

```bash
.venv/bin/python -m evaluations.ragas_rag_eval.cli generate \
  --source-paths /Users/yewen/Desktop/file \
  --batch-size 5 \
  --cases-per-batch 2 \
  --target-case-count 30 \
  --output evaluations/datasets/ragas_generated_cases.jsonl
```

Run the RAG evaluation:

```bash
.venv/bin/python -m evaluations.ragas_rag_eval.cli run \
  --cases evaluations/datasets/ragas_generated_cases.jsonl \
  --output-dir evaluations/results/ragas_rag_eval
```

The report includes Ragas metrics for generation quality and factual grounding,
plus custom metrics for Qdrant retrieval hit rate, actual `rag_search` usage,
empty retrievals, timeouts, failures, and latency.
