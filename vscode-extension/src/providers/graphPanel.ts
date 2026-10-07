/**
 * Cytoscape.js Dependency Graph Panel for Requirement Traceability Engine.
 *
 * Implements vscode.WebviewViewProvider to render an active-viewport
 * 3-node linear chain:
 *   [ User Story ] ---> [ Active Function ] ---> [ Unit Test ]
 * Edge 1: Cosine similarity score & source
 * Edge 2: Test assertion status (Passed / Missing)
 */

import * as vscode from "vscode";
import { TraceApiClient } from "../api/client";
import { GraphResponse } from "../api/types";
import { StoryManager } from "../stories/storyManager";

export class TraceGraphPanelProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "rte.graphView";

  private _view?: vscode.WebviewView;
  private _debounceTimer?: NodeJS.Timeout;
  private _lastSignature?: string;

  constructor(private readonly _extensionUri: vscode.Uri) {}

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): void {
    this._view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this._extensionUri],
    };

    webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);

    // Track active editor cursor position changes
    vscode.window.onDidChangeTextEditorSelection((e) => {
      this._onCursorChanged(e.textEditor);
    });

    vscode.window.onDidChangeActiveTextEditor((editor) => {
      if (editor) {
        this._onCursorChanged(editor);
      }
    });

    // Initial render for active editor
    if (vscode.window.activeTextEditor) {
      this._onCursorChanged(vscode.window.activeTextEditor);
    }
  }

  public updateViewport(): void {
    if (vscode.window.activeTextEditor) {
      this._onCursorChanged(vscode.window.activeTextEditor, true);
    }
  }

  private _onCursorChanged(editor: vscode.TextEditor, force: boolean = false): void {
    if (!this._view || !this._view.visible) {
      return;
    }

    const doc = editor.document;
    if (doc.languageId !== "python" && doc.languageId !== "typescript") {
      return;
    }

    const cursorLine = editor.selection.active.line + 1; // 1-indexed for backend
    const signature = `${doc.uri.toString()}#L${cursorLine}@v${doc.version}`;

    if (!force && this._lastSignature === signature) {
      return;
    }
    this._lastSignature = signature;

    if (this._debounceTimer) {
      clearTimeout(this._debounceTimer);
    }

    this._debounceTimer = setTimeout(async () => {
      await this._fetchAndRenderGraph(doc, cursorLine);
    }, 150);
  }

  private async _fetchAndRenderGraph(document: vscode.TextDocument, cursorLine: number): Promise<void> {
    if (!this._view) {
      return;
    }

    try {
      const client = TraceApiClient.getInstance();
      const stories = StoryManager.getInstance().getStories();

      const response: GraphResponse = await client.traceGraph({
        file_path: document.uri.fsPath,
        cursor_line: cursorLine,
        file_content: document.getText(),
        stories: stories,
      });

      this._view.webview.postMessage({
        type: "UPDATE_GRAPH",
        data: response,
      });
    } catch (err: any) {
      console.warn("Failed to update trace graph:", err);
      this._view.webview.postMessage({
        type: "GRAPH_ERROR",
        message: err.message || "Failed to load trace graph",
      });
    }
  }

  private _getHtmlForWebview(webview: vscode.Webview): string {
    const cytoscapeUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, "media", "cytoscape.min.js")
    );

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Trace Graph</title>
  <script src="${cytoscapeUri}"></script>
  <style>
    :root {
      --bg: var(--vscode-editor-background, #1e1e1e);
      --fg: var(--vscode-editor-foreground, #d4d4d4);
      --border: var(--vscode-panel-border, #333333);
      --badge-bg: var(--vscode-badge-background, #007acc);
      --badge-fg: var(--vscode-badge-foreground, #ffffff);
    }
    body, html {
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background-color: var(--bg);
      color: var(--fg);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    #container {
      display: flex;
      flex-direction: column;
      width: 100%;
      height: 100%;
    }
    #header {
      padding: 10px 14px;
      border-bottom: 1px solid var(--border);
      background: rgba(255, 255, 255, 0.02);
    }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      font-size: 11px;
      font-weight: 600;
      border-radius: 4px;
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .status-VERIFIED { background: #238636; color: #ffffff; }
    .status-MISSING_TEST { background: #d29922; color: #1f1d1d; }
    .status-CANDIDATE { background: #1f6feb; color: #ffffff; }
    .status-ORPHAN { background: #da3633; color: #ffffff; }

    #function-name {
      font-size: 13px;
      font-weight: 600;
      font-family: monospace;
      color: var(--fg);
    }
    #cy {
      flex: 1;
      width: 100%;
      height: 100%;
    }
    #empty-state {
      display: none;
      align-items: center;
      justify-content: center;
      height: 100%;
      font-size: 12px;
      color: #888;
      text-align: center;
      padding: 20px;
    }
  </style>
</head>
<body>
  <div id="container">
    <div id="header">
      <div id="status-badge" class="badge status-ORPHAN">INITIALIZING</div>
      <div id="function-name">Cursor position outside function</div>
    </div>
    <div id="empty-state">Move editor cursor inside a function to view its 3-node trace chain.</div>
    <div id="cy"></div>
  </div>

  <script>
    let cy = null;

    function initCy() {
      cy = cytoscape({
        container: document.getElementById('cy'),
        boxSelectionEnabled: false,
        autounselectify: true,
        style: [
          {
            selector: 'node',
            style: {
              'label': 'data(label)',
              'text-valign': 'center',
              'text-halign': 'center',
              'color': '#ffffff',
              'font-size': '11px',
              'font-weight': '600',
              'width': '140px',
              'height': '60px',
              'shape': 'round-rectangle',
              'text-wrap': 'wrap',
              'text-max-width': '130px',
              'border-width': 2,
              'border-color': '#444444'
            }
          },
          {
            selector: 'node[type = "story"]',
            style: {
              'background-color': '#1f6feb',
              'border-color': '#58a6ff'
            }
          },
          {
            selector: 'node[type = "function"]',
            style: {
              'background-color': '#8957e5',
              'border-color': '#bc8cff'
            }
          },
          {
            selector: 'node[type = "test"]',
            style: {
              'background-color': '#238636',
              'border-color': '#3fb950'
            }
          },
          {
            selector: 'node[status = "missing"]',
            style: {
              'background-color': '#da3633',
              'border-color': '#f85149'
            }
          },
          {
            selector: 'edge',
            style: {
              'width': 2,
              'target-arrow-shape': 'triangle',
              'line-color': '#8b949e',
              'target-arrow-color': '#8b949e',
              'curve-style': 'bezier',
              'label': 'data(label)',
              'font-size': '10px',
              'color': '#c9d1d9',
              'text-background-color': '#161b22',
              'text-background-opacity': 0.85,
              'text-background-padding': '3px',
              'text-rotation': 'autorotate'
            }
          },
          {
            selector: 'edge[status = "VERIFIED"]',
            style: {
              'line-color': '#3fb950',
              'target-arrow-color': '#3fb950'
            }
          },
          {
            selector: 'edge[status = "missing"]',
            style: {
              'line-color': '#f85149',
              'target-arrow-color': '#f85149',
              'line-style': 'dashed'
            }
          }
        ],
        layout: {
          name: 'grid',
          rows: 3,
          cols: 1,
          padding: 20
        }
      });
    }

    window.addEventListener('message', event => {
      const message = event.data;
      if (message.type === 'UPDATE_GRAPH') {
        renderGraph(message.data);
      }
    });

    function renderGraph(data) {
      if (!cy) {
        initCy();
      }

      const elements = (data.graph && data.graph.elements) ? data.graph.elements : [];
      const headerFn = document.getElementById('function-name');
      const badge = document.getElementById('status-badge');
      const emptyState = document.getElementById('empty-state');
      const cyContainer = document.getElementById('cy');

      if (!elements || elements.length === 0 || !data.active_function) {
        emptyState.style.display = 'flex';
        cyContainer.style.display = 'none';
        headerFn.textContent = 'Cursor outside detected functions';
        badge.className = 'badge status-ORPHAN';
        badge.textContent = 'STANDBY';
        return;
      }

      emptyState.style.display = 'none';
      cyContainer.style.display = 'block';

      // Find active function node
      const fnNode = elements.find(el => el.data && el.data.type === 'function');
      const fnStatus = fnNode && fnNode.data.status ? fnNode.data.status : 'ORPHAN';

      headerFn.textContent = 'fn ' + data.active_function + '()';
      badge.className = 'badge status-' + fnStatus;
      badge.textContent = fnStatus.replace('_', ' ');

      cy.elements().remove();
      cy.add(elements);

      // Hierarchical top-down layout: Story -> Function -> Test
      cy.layout({
        name: 'breadthfirst',
        directed: true,
        padding: 25,
        spacingFactor: 1.5,
        avoidOverlap: true
      }).run();

      cy.fit();
    }

    initCy();
  </script>
</body>
</html>`;
  }
}
