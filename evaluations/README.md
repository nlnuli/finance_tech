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
