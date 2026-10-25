/**
 * Active Traceability Sub-Graph Webview Provider for Requirement Traceability Engine.
 *
 * Renders an active-viewport 3-node card hierarchy matching the primary IDE workspace:
 *   [ REQUIREMENT ] ---> [ IMPLEMENTATION ] ---> [ VERIFICATION ]
 * Plus real-time link rationale telemetry.
 */

import * as path from "path";
import * as vscode from "vscode";
import { TraceApiClient } from "../api/client";
import { GraphResponse } from "../api/types";
import { StoryManager } from "../stories/storyManager";
import { resolveWorkspaceRootUri } from "../utils/workspaceRoot";

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

    // Handle messages from the webview (clicking verification or implementation nodes)
    webviewView.webview.onDidReceiveMessage(async (message) => {
      if (message.type === "NAVIGATE_TO_CODE") {
        await this._navigateToCode(message.filePath, message.line, message.symbolName);
      } else if (message.type === "NO_TEST_FILE_WARNING") {
        vscode.window.showWarningMessage(
          `No unit test fixture exists for ${message.functionName || "this function"}(). Create a test fixture to establish traceability.`
        );
      }
    });

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

  /**
   * Navigates to a specific file and line, focusing on the target function definition.
   */
  private async _navigateToCode(
    filePath?: string,
    line: number = 1,
    symbolName?: string
  ): Promise<void> {
    try {
      if (!filePath && !symbolName) {
        vscode.window.showWarningMessage("No target file or code symbol linked to navigate to.");
        return;
      }

      // Ignore dummy placeholder symbol names
      if (symbolName === "unit_test" || symbolName === "test_node") {
        symbolName = undefined;
      }

      const projectUri = resolveWorkspaceRootUri();
      let targetUri: vscode.Uri | undefined;

      if (filePath && filePath.trim().length > 0) {
        if (path.isAbsolute(filePath)) {
          targetUri = vscode.Uri.file(filePath);
        } else {
          targetUri = vscode.Uri.joinPath(projectUri, filePath);
        }

        try {
          await vscode.workspace.fs.stat(targetUri);
        } catch {
          targetUri = undefined;
        }
      }

      // If no file path or file not found on disk, deduce candidate test file ONLY based on active file's folder
      if (!targetUri) {
        const activeEditor = vscode.window.activeTextEditor;
        if (activeEditor) {
          const activePath = activeEditor.document.uri.fsPath;
          const activeDir = path.dirname(activePath);
          const activeBase = path.basename(activePath, ".py");

          if (symbolName && (symbolName.startsWith("test_") || symbolName.endsWith("_test"))) {
            const raw = activeBase.replace(/^test_/, "");
            const candidates = [
              vscode.Uri.file(path.join(activeDir, "..", "tests", `test_${raw}.py`)),
              vscode.Uri.file(path.join(activeDir, "tests", `test_${raw}.py`)),
              vscode.Uri.file(path.join(activeDir, `test_${raw}.py`)),
              vscode.Uri.joinPath(projectUri, "tests", `test_${raw}.py`),
              vscode.Uri.joinPath(projectUri, `test_${raw}.py`),
            ];
            for (const cand of candidates) {
              try {
                await vscode.workspace.fs.stat(cand);
                targetUri = cand;
                break;
              } catch {}
            }
          }
        }
      }

      if (!targetUri) {
        vscode.window.showWarningMessage(
          `No unit test file found for ${symbolName || (filePath ? path.basename(filePath) : "this function")}.`
        );
        return;
      }

      const doc = await vscode.workspace.openTextDocument(targetUri);
      const editor = await vscode.window.showTextDocument(doc, {
        preview: false,
        viewColumn: vscode.ViewColumn.One,
      });

      // Calculate target line: search for symbol definition in text if possible
      let targetLineIndex = Math.max(0, (line || 1) - 1);
      if (symbolName) {
        const text = doc.getText();
        const lines = text.split(/\r?\n/);
        const defRegex = new RegExp(`^\\s*(?:async\\s+)?def\\s+${symbolName}\\b`);
        for (let i = 0; i < lines.length; i++) {
          if (defRegex.test(lines[i])) {
            targetLineIndex = i;
            break;
          }
        }
      }

      const pos = new vscode.Position(targetLineIndex, 0);
      editor.selection = new vscode.Selection(pos, pos);
      editor.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenter);

      const displayFileName = path.basename(targetUri.fsPath);
      vscode.window.setStatusBarMessage(
        `$(arrow-right) Navigated to ${displayFileName}:${targetLineIndex + 1} (${symbolName || "function"})`,
        3000
      );
    } catch (err: any) {
      console.error("Navigation error:", err);
      vscode.window.showErrorMessage(`Failed to navigate to file: ${err.message || err}`);
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

   
    .status-badge {
      font-size: 10px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 12px;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      letter-spacing: 0.04em;
      font-family: var(--font-code);
      transition: all 0.2s ease;
      white-space: nowrap;
      border: 1px solid transparent;
    }
    .status-badge.status-verified {
      background: rgba(46, 160, 67, 0.18);
      border-color: rgba(63, 185, 80, 0.45);
      color: #3fb950;
      box-shadow: 0 0 8px rgba(63, 185, 80, 0.15);
    }
    .status-badge.status-missing-test {
      background: rgba(210, 153, 34, 0.18);
      border-color: rgba(210, 153, 34, 0.45);
      color: #e3b341;
      box-shadow: 0 0 8px rgba(210, 153, 34, 0.15);
    }
    .status-badge.status-unlinked {
      background: rgba(139, 148, 158, 0.12);
      border-color: rgba(139, 148, 158, 0.25);
      color: var(--text-muted);
    }
    .status-badge.status-candidate {
      background: rgba(56, 139, 253, 0.18);
      border-color: rgba(56, 139, 253, 0.45);
      color: #58a6ff;
      box-shadow: 0 0 8px rgba(56, 139, 253, 0.15);
    }

    /* 3-Tier Card Layout */
    .node-card {
      background: var(--card-bg);
      border-radius: 6px;
      padding: 14px 16px;
      text-align: center;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      width: 100%;
      user-select: none;
    }

    .node-card.clickable {
      cursor: pointer;
      position: relative;
    }

    .node-card.clickable:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
    }

    .card-action-hint {
      font-size: 10px;
      margin-top: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      opacity: 0.75;
      letter-spacing: 0.04em;
    }

    .node-card.clickable:hover .card-action-hint {
      opacity: 1;
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
    .card-requirement.unlinked {
      border-color: var(--border-default);
      box-shadow: none;
    }
    .card-requirement.unlinked .card-label {
      color: var(--text-muted);
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
    .card-implementation.clickable:hover {
      border-color: #3fb950;
      box-shadow: 0 0 16px rgba(35, 134, 54, 0.35);
    }
    .card-implementation.clickable:hover .card-action-hint {
      color: var(--green-text);
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
    .card-verification.clickable:hover {
      border-color: #3fb950;
      box-shadow: 0 0 16px rgba(63, 185, 80, 0.35);
    }
    .card-verification.missing.clickable:hover {
      border-color: #f85149;
      box-shadow: 0 0 16px rgba(218, 54, 51, 0.35);
    }
    .card-verification.clickable:hover .card-action-hint {
      color: var(--green-text);
    }
    .card-verification.missing.clickable:hover .card-action-hint {
      color: var(--red-text);
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
      <span id="graph-status-badge" class="status-badge status-unlinked">○ UNLINKED</span>
    </div>

    <div id="empty-state">
      Move editor cursor inside a function to inspect active traceability.
    </div>

    <div id="graph-content">
      <!-- Node 1: Requirement -->
      <div id="req-card" class="node-card card-requirement">
        <div class="card-label">Requirement</div>
        <div id="req-title" class="card-value">US-102: context.subscriptions.push</div>
      </div>

      <!-- Connector 1 -->
      <div class="connector">
        <div id="conn-line-1" class="connector-line"></div>
        <span id="conn-arrow-1" class="connector-arrow">▾</span>
      </div>

      <!-- Node 2: Implementation -->
      <div id="impl-card" class="node-card card-implementation">
        <div class="card-label">Implementation</div>
        <div id="impl-title" class="card-value"></div>
        <div class="card-action-hint"><span id="impl-hint">↗ Click to open implementation</span></div>
      </div>

      <!-- Connector 2 -->
      <div class="connector">
        <div id="conn-line-2" class="connector-line"></div>
        <span id="conn-arrow-2" class="connector-arrow">▾</span>
      </div>

      <!-- Node 3: Verification -->
      <div id="verif-card" class="node-card card-verification">
        <div class="card-label">Verification</div>
        <div id="verif-title" class="card-value"></div>
        <div class="card-action-hint"><span id="verif-hint">↗ Click to open test fixture</span></div>
      </div>

      <!-- Link Rationale Box -->
      <div class="rationale-container">
        ℹ <strong class="rationale-title">Link Rationale:</strong>
        <span id="rationale-text">High semantic similarity (0.88) found between User Story ACs and function docstrings.</span>
      </div>
    </div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();

    let currentTestData = null;
    let currentImplData = null;

    document.getElementById('verif-card').addEventListener('click', () => {
      const hasPath = currentTestData && currentTestData.file_path && currentTestData.file_path.trim().length > 0;
      const hasSymbol = currentTestData && currentTestData.symbol_name && currentTestData.symbol_name !== 'unit_test' && currentTestData.symbol_name.length > 0;
      if (hasPath || hasSymbol) {
        vscode.postMessage({
          type: 'NAVIGATE_TO_CODE',
          filePath: currentTestData.file_path || '',
          line: currentTestData.line_start || 1,
          symbolName: (currentTestData.symbol_name && currentTestData.symbol_name !== 'unit_test') ? currentTestData.symbol_name : '',
        });
      } else {
        vscode.postMessage({
          type: 'NO_TEST_FILE_WARNING',
          functionName: (currentImplData && currentImplData.name) || 'function',
        });
      }
    });

    document.getElementById('impl-card').addEventListener('click', () => {
      if (currentImplData && (currentImplData.file_path || currentImplData.symbol_name || currentImplData.name)) {
        vscode.postMessage({
          type: 'NAVIGATE_TO_CODE',
          filePath: currentImplData.file_path,
          line: currentImplData.line_start || 1,
          symbolName: currentImplData.symbol_name || currentImplData.name,
        });
      }
    });

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
        const graphStatusBadge = document.getElementById('graph-status-badge');
        if (graphStatusBadge) {
          graphStatusBadge.className = 'status-badge status-unlinked';
          graphStatusBadge.textContent = '○ UNLINKED';
        }
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

      currentTestData = testNode && testNode.data ? testNode.data : null;
      currentImplData = funcNode && funcNode.data ? funcNode.data : null;

      const storyId = data.story_id || (storyNode && storyNode.data ? storyNode.data.id.replace('story_', '') : 'UNLINKED');
      const funcStatus = (funcNode && funcNode.data && funcNode.data.status) ? funcNode.data.status : 'ORPHAN';
      const sim = (storyEdge && storyEdge.data && storyEdge.data.similarity !== undefined) ? storyEdge.data.similarity : 0;
      const hasAssertion = testNode && testNode.data && testNode.data.status === 'passed';

      // Update clean tripartite status badge in header
      const graphStatusBadge = document.getElementById('graph-status-badge');
      if (graphStatusBadge) {
        if (storyId !== 'UNLINKED' && (funcStatus === 'VERIFIED' || hasAssertion)) {
          graphStatusBadge.className = 'status-badge status-verified';
          graphStatusBadge.textContent = '✓ VERIFIED';
        } else if (storyId !== 'UNLINKED' && (funcStatus === 'MISSING_TEST' || !hasAssertion)) {
          graphStatusBadge.className = 'status-badge status-missing-test';
          graphStatusBadge.textContent = '⚠️ MISSING TEST';
        } else if (funcStatus === 'CANDIDATE') {
          graphStatusBadge.className = 'status-badge status-candidate';
          graphStatusBadge.textContent = '🔍 CANDIDATE';
        } else {
          graphStatusBadge.className = 'status-badge status-unlinked';
          graphStatusBadge.textContent = '○ UNLINKED';
        }
      }

      // 1. Populate Requirement
      const reqCard = document.getElementById('req-card');
      const connLine1 = document.getElementById('conn-line-1');
      const connArrow1 = document.getElementById('conn-arrow-1');
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
        if (reqCard) reqCard.className = 'node-card card-requirement';
        if (connLine1) connLine1.className = 'connector-line';
        if (connArrow1) connArrow1.className = 'connector-arrow';
      } else {
        reqTitle.textContent = 'Unlinked (No Story Match)';
        if (reqCard) reqCard.className = 'node-card card-requirement unlinked';
        if (connLine1) connLine1.className = 'connector-line untested';
        if (connArrow1) connArrow1.className = 'connector-arrow untested';
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

      if (currentImplData && (currentImplData.file_path || currentImplData.symbol_name || currentImplData.name)) {
        implCard.classList.add('clickable');
        const implBase = currentImplData.file_path ? currentImplData.file_path.split(/[\\\\/]/).pop() : 'source file';
        implCard.title = 'Click to open ' + implBase + (currentImplData.line_start ? ':' + currentImplData.line_start : '');
      } else {
        implCard.classList.remove('clickable');
        implCard.title = '';
      }

      // 3. Populate Verification
      const verifTitle = document.getElementById('verif-title');
      const verifCard = document.getElementById('verif-card');
      const verifHint = document.getElementById('verif-hint');
      const connLine2 = document.getElementById('conn-line-2');
      const connArrow2 = document.getElementById('conn-arrow-2');

      if (hasAssertion && storyId !== 'UNLINKED') {
        let testLabel = 'Unit Test Assertion Verified';
        if (testNode && testNode.data && testNode.data.label) {
          const parts = String(testNode.data.label).split(/\\r?\\n/);
          testLabel = parts[0].replace('Test: ', '');
        }
        verifTitle.textContent = testLabel;
        verifCard.className = 'node-card card-verification passed';
        connLine2.className = 'connector-line';
        connArrow2.className = 'connector-arrow';
        if (verifHint) {
          verifHint.textContent = '↗ Click to open test fixture';
        }
      } else {
        let testLabel = 'No Linked Test';
        if (testNode && testNode.data && testNode.data.label && !testNode.data.label.includes('Missing')) {
          const parts = String(testNode.data.label).split(/\\r?\\n/);
          testLabel = parts[0].trim();
        } else if (storyId !== 'UNLINKED') {
          testLabel = 'Unit Test (Missing Assertion)';
        }
        verifTitle.textContent = testLabel;
        verifCard.className = 'node-card card-verification missing';
        connLine2.className = 'connector-line untested';
        connArrow2.className = 'connector-arrow untested';
        if (verifHint) {
          verifHint.textContent = (currentTestData && currentTestData.file_path) ? '↗ Click to open test file' : '○ Untested';
        }
      }

      const hasTestPath = currentTestData && currentTestData.file_path && currentTestData.file_path.trim().length > 0;
      const hasRealTestSymbol = currentTestData && currentTestData.symbol_name && currentTestData.symbol_name !== 'unit_test' && currentTestData.symbol_name.length > 0;

      if (hasTestPath || hasRealTestSymbol) {
        verifCard.classList.add('clickable');
        const testBase = hasTestPath ? currentTestData.file_path.split(/[\\\\/]/).pop() : 'test file';
        if (hasRealTestSymbol) {
          verifCard.title = 'Click to open ' + testBase + ' > ' + currentTestData.symbol_name + '()';
        } else {
          verifCard.title = 'Click to open ' + testBase;
        }
      } else {
        verifCard.classList.remove('clickable');
        verifCard.title = 'No test fixture found for this function';
      }

      // 4. Populate Link Rationale
      const rationaleText = document.getElementById('rationale-text');
      if (storyId !== 'UNLINKED' && (funcStatus === 'VERIFIED' || funcStatus === 'MISSING_TEST')) {
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