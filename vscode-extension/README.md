# Synapse Traceability (VS Code extension)

The in-editor part of the Requirement Traceability Engine. The heavy work (parsing, local embeddings, linking)
runs in the Python engine in [`../backend`](../backend) and [`../ml-engine`](../ml-engine); the extension watches
the workspace and shows the results inside VS Code.

## Planned features (from the proposal)

- Trigger incremental matching when a file is saved.
- Pre-commit verification: flag unmapped stories, orphaned code and missing tests before a commit.
- Contextual filtering: show only the stories related to the active editor file (Cytoscape.js graph in a webview).
- Human-readable link rationales.

## Develop

```powershell
npm install
npm run compile      # or: npm run watch
```

Open this folder in VS Code and press **F5** (*Run Extension*). In the new window, run
**Synapse: Show Traceability Engine Status** from the Command Palette to check it can reach the engine at
`synapseTraceability.engineUrl` (default `http://localhost:8003`).
