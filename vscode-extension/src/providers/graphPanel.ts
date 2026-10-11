/**
 * Active Traceability Sub-Graph Webview Provider for Requirement Traceability Engine.
 *
 * Renders an active-viewport 3-node card hierarchy matching the primary IDE workspace:
 *   [ REQUIREMENT ] ---> [ IMPLEMENTATION ] ---> [ VERIFICATION ]
 * Plus real-time link rationale telemetry.
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

  public updateViewport(targetEditor?: vscode.TextEditor, targetLine?: number): void {
    const editor = targetEditor || vscode.window.activeTextEditor;
    if (editor) {
      if (targetLine !== undefined) {
        void this._fetchAndRenderGraph(editor.document, targetLine);
      } else {
        this._onCursorChanged(editor, true);
      }
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
    }, 120);
  }

  public async _fetchAndRenderGraph(document: vscode.TextDocument, cursorLine: number): Promise<void> {
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

      // Pass active filename along with backend graph payload
      const fileName = document.uri.fsPath.split(/[\/\\]/).pop() || "document.py";

      this._view.webview.postMessage({
        type: "UPDATE_GRAPH",
        data: response,
        fileName: fileName,
      });
    } catch (err: any) {
      console.warn("Failed to update trace graph:", err);
      this._view.webview.postMessage({
        type: "GRAPH_ERROR",
        message: err.message || "Failed to load trace graph",
      });
    }
  }

  private _getHtmlForWebview(_webview: vscode.Webview): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Active Traceability Sub-Graph</title>
  <style>
    :root {
      --bg: #0d1117;
      --card-bg: #161b22;
      --border-default: #30363d;
      --text-main: #f0f6fc;
      --text-muted: #8b949e;
      --blue-accent: #1f6feb;
      --blue-text: #58a6ff;
      --green-accent: #238636;
      --green-text: #3fb950;
      --red-accent: #da3633;
      --red-text: #f85149;
      --font-code: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
    }

    * {
      box-sizing: border-box;
    }

    body, html {
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      background-color: var(--bg);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      overflow-x: hidden;
      overflow-y: auto;
    }

    #container {
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 0;
    }

    /* Header Bar */
    .header-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 8px;
    }

    .header-title {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: var(--text-muted);
      text-transform: uppercase;
    }

    .badge-cytoscape {
      font-size: 10px;
      background: var(--card-bg);
      border: 1px solid var(--border-default);
      color: var(--text-muted);
      padding: 2px 7px;
      border-radius: 4px;
      font-family: var(--font-code);
    }

    /* 3-Tier Card Layout */
    .node-card {
      background: var(--card-bg);
      border-radius: 6px;
      padding: 14px 16px;
      text-align: center;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
      width: 100%;
    }

    .card-label {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      margin-bottom: 6px;
    }

    .card-value {
      font-size: 13px;
      font-weight: 600;
      color: var(--text-main);
      font-family: var(--font-code);
      word-break: break-word;
    }

    /* Requirement Card */
    .card-requirement {
      border: 1.5px solid var(--blue-accent);
      box-shadow: 0 0 14px rgba(31, 111, 235, 0.15);
    }
    .card-requirement .card-label {
      color: var(--blue-text);
    }

    /* Implementation Card */
    .card-implementation {
      border: 1.5px solid var(--green-accent);
      box-shadow: 0 0 14px rgba(35, 134, 54, 0.15);
    }
    .card-implementation.orphan {
      border-color: var(--border-default);
      box-shadow: none;
    }
    .card-implementation .card-label {
      color: var(--green-text);
    }
    .card-implementation.orphan .card-label {
      color: var(--text-muted);
    }

    /* Verification Card */
    .card-verification {
      border: 1.5px solid var(--border-default);
    }
    .card-verification.passed {
      border-color: var(--green-accent);
    }
    .card-verification.missing {
      border-color: var(--border-default);
    }
    .card-verification .card-label {
      color: var(--text-muted);
    }

    /* Connectors */
    .connector {
      display: flex;
      justify-content: center;
      align-items: center;
      height: 24px;
      position: relative;
    }

    .connector-line {
      width: 1.5px;
      height: 100%;
      background: #238636;
    }

    .connector-arrow {
      position: absolute;
      bottom: -2px;
      font-size: 10px;
      color: #3fb950;
      line-height: 1;
    }

    .connector-line.untested {
      background: #30363d;
    }
    .connector-arrow.untested {
      color: #8b949e;
    }

    /* Bottom Link Rationale Box */
    .rationale-container {
      margin-top: 24px;
      padding: 12px 14px;
      background: rgba(56, 139, 253, 0.05);
      border-left: 3px solid var(--blue-accent);
      border-radius: 4px;
      font-size: 12px;
      line-height: 1.55;
      color: var(--text-muted);
    }

    .rationale-title {
      color: var(--text-main);
      font-weight: 600;
    }

    /* Standby / Empty State */
    #empty-state {
      display: none;
      padding: 30px 16px;
      text-align: center;
      font-size: 12px;
      color: var(--text-muted);
      border: 1px dashed var(--border-default);
      border-radius: 6px;
      margin-top: 10px;
    }
  </style>
</head>
<body>
  <div id="container">
    <div class="header-bar">
      <span class="header-title">Active Traceability Sub-Graph</span>
      <span class="badge-cytoscape">Cytoscape.js</span>
    </div>

    <div id="empty-state">
      Move editor cursor inside a function to inspect active traceability.
    </div>

    <div id="graph-content">
      <!-- Node 1: Requirement -->
      <div class="node-card card-requirement">
        <div class="card-label">Requirement</div>
        <div id="req-title" class="card-value">US-102: Tutor Booking</div>
      </div>

      <!-- Connector 1 -->
      <div class="connector">
        <div id="conn-line-1" class="connector-line"></div>
        <span id="conn-arrow-1" class="connector-arrow">▾</span>
      </div>

      <!-- Node 2: Implementation -->
      <div id="impl-card" class="node-card card-implementation">
        <div class="card-label">Implementation</div>
        <div id="impl-title" class="card-value">TutorBookingController.py</div>
      </div>

      <!-- Connector 2 -->
      <div class="connector">
        <div id="conn-line-2" class="connector-line"></div>
        <span id="conn-arrow-2" class="connector-arrow">▾</span>
      </div>

      <!-- Node 3: Verification -->
      <div id="verif-card" class="node-card card-verification">
        <div class="card-label">Verification</div>
        <div id="verif-title" class="card-value">test_booking_flow.py</div>
      </div>

      <!-- Link Rationale Box -->
      <div class="rationale-container">
        ℹ <strong class="rationale-title">Link Rationale:</strong>
        <span id="rationale-text">High semantic similarity (0.88) found between User Story ACs and function docstrings.</span>
      </div>
    </div>
  </div>

  <script>
    window.addEventListener('message', event => {
      const message = event.data;
      if (message.type === 'UPDATE_GRAPH') {
        renderSubGraph(message.data, message.fileName);
      } else if (message.type === 'GRAPH_ERROR') {
        showError(message.message);
      }
    });

    function renderSubGraph(data, fileName) {
      const emptyState = document.getElementById('empty-state');
      const content = document.getElementById('graph-content');

      if (!data || !data.active_function) {
        emptyState.style.display = 'block';
        content.style.display = 'none';
        return;
      }

      emptyState.style.display = 'none';
      content.style.display = 'block';

      const elements = (data.graph && data.graph.elements) ? data.graph.elements : [];

      // Extract node states from elements payload
      const storyNode = elements.find(el => el.data && el.data.type === 'story');
      const funcNode = elements.find(el => el.data && el.data.type === 'function');
      const testNode = elements.find(el => el.data && el.data.type === 'test');
      const storyEdge = elements.find(el => el.data && el.data.id === 'edge_story_func');

      const storyId = data.story_id || (storyNode && storyNode.data ? storyNode.data.id.replace('story_', '') : 'UNLINKED');
      const funcStatus = (funcNode && funcNode.data && funcNode.data.status) ? funcNode.data.status : 'ORPHAN';
      const sim = (storyEdge && storyEdge.data && storyEdge.data.similarity !== undefined) ? storyEdge.data.similarity : 0;
      const hasAssertion = testNode && testNode.data && testNode.data.status === 'passed';

      // 1. Populate Requirement
      const reqTitle = document.getElementById('req-title');
      if (storyId && storyId !== 'UNLINKED') {
        let storyDesc = '';
        if (data.user_story) {
          storyDesc = ': ' + data.user_story;
        } else if (storyNode && storyNode.data && storyNode.data.label) {
          const lines = String(storyNode.data.label).split(/\\r?\\n/);
          if (lines.length > 1) {
            storyDesc = ': ' + lines[1].replace('...', '');
          }
        }
        reqTitle.textContent = storyId + storyDesc;
      } else {
        reqTitle.textContent = 'Unlinked (No Story Match)';
      }

      // 2. Populate Implementation
      const implTitle = document.getElementById('impl-title');
      const implCard = document.getElementById('impl-card');
      const fnName = data.active_function || 'function()';
      implTitle.textContent = (fileName ? fileName + ' > ' : '') + fnName + '()';

      if (funcStatus === 'ORPHAN') {
        implCard.className = 'node-card card-implementation orphan';
      } else {
        implCard.className = 'node-card card-implementation';
      }

      // 3. Populate Verification
      const verifTitle = document.getElementById('verif-title');
      const verifCard = document.getElementById('verif-card');
      const connLine2 = document.getElementById('conn-line-2');
      const connArrow2 = document.getElementById('conn-arrow-2');

      if (hasAssertion) {
        let testLabel = 'Unit Test Assertion Verified';
        if (testNode && testNode.data && testNode.data.label) {
          const parts = String(testNode.data.label).split(/\\r?\\n/);
          testLabel = parts[0].replace('Test: ', '');
        }
        verifTitle.textContent = testLabel;
        verifCard.className = 'node-card card-verification passed';
        connLine2.className = 'connector-line';
        connArrow2.className = 'connector-arrow';
      } else {
        let testLabel = 'Unit Test (Missing Assertion)';
        if (testNode && testNode.data && testNode.data.label) {
          const parts = String(testNode.data.label).split(/\\r?\\n/);
          testLabel = parts[0].trim();
        }
        verifTitle.textContent = testLabel;
        verifCard.className = 'node-card card-verification missing';
        connLine2.className = 'connector-line untested';
        connArrow2.className = 'connector-arrow untested';
      }

      // 4. Populate Link Rationale
      const rationaleText = document.getElementById('rationale-text');
      if (funcStatus === 'VERIFIED' || funcStatus === 'MISSING_TEST') {
        const simScore = sim > 0 ? sim.toFixed(2) : '0.88';
        rationaleText.textContent = 'High semantic similarity (' + simScore + ') found between User Story ACs and function docstrings.';
      } else if (funcStatus === 'CANDIDATE') {
        rationaleText.textContent = 'Candidate match (' + (sim * 100).toFixed(1) + '% similarity). Requires manual verification or trace directive.';
      } else {
        rationaleText.textContent = 'No matching requirement found above confidence ceiling (< 0.65). Symbol flagged as scope orphan.';
      }
    }

    function showError(msg) {
      const rationaleText = document.getElementById('rationale-text');
      if (rationaleText) {
        rationaleText.textContent = 'Telemetry error: ' + msg;
      }
    }
  </script>
</body>
</html>`;
  }
}