# ML engine: Requirement Traceability Engine

Research code for this component: preparing datasets, training and evaluating models.
The API in [`../backend`](../backend) loads the trained models to serve results to the platform.

## Planned work (from the proposal)

- **Task 1 – Multi-source ingestion and parsing:** split user stories, acceptance-criteria Markdown and polyglot source code into indexable text and function blocks.
- **Task 2 – Local embeddings and semantic mapping:** quantised (INT8) SBERT, cosine similarity against code blocks and explicit `# Trace: Story-102` tags.
- **Task 3 – Workspace observer and pre-commit gate:** watch file saves, delta-match changed files, flag unmapped stories and missing tests before commit.
- **Task 4 – Contextual filtering:** show only the stories related to the active editor file (VS Code extension, Cytoscape.js).

## Layout

```
ml-engine/
├── src/trace_ml/   # reusable code: data loading, features, models, evaluation
├── notebooks/        # exploration only; move anything reusable into src/
└── tests/
```

## Data and models

Never commit datasets or trained models. Keep them in `AgilePlatform/Datasets/traceability/`, next to the
repositories; `trace_ml.config.DATA_DIR` points there (override it with the `TRACE_DATA_DIR` environment variable).

## Adding libraries

Add what you need (for example `transformers`, `sentence-transformers`, `torch`) to `dependencies` in
`ml-engine/pyproject.toml`, then reinstall from the repository root:

```powershell
.venv\Scripts\python -m pip install -e "ml-engine[dev]"
```
