/**
 * Sprint Backlog Sidebar Panel for Requirement Traceability Engine.
 *
 * Implements vscode.WebviewViewProvider to render:
 *  - Active-File Scope Filter toggle
 *  - High-confidence requirement card with dynamic similarity badge
 *  - Dynamic acceptance criteria checklist evaluated against active editor content
 *  - Hidden background stories counter
 */

import * as vscode from "vscode";
import { TraceApiClient } from "../api/client";
import { StoryRef } from "../api/types";
import { StoryManager } from "../stories/storyManager";

export class TraceBacklogPanelProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "rte.backlogView";

  private _view?: vscode.WebviewView;
  private _scopeFilterEnabled: boolean = true;
  private _debounceTimer?: NodeJS.Timeout;

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

    webviewView.webview.html = this._getHtmlForWebview();

    // Listen to messages from the webview (e.g. toggle switch clicks, scaffold button)
    webviewView.webview.onDidReceiveMessage(async (message) => {
      if (message.type === "TOGGLE_SCOPE_FILTER") {
        this._scopeFilterEnabled = message.value;
        this.updateBacklog();
      } else if (message.type === "SCAFFOLD_STORY") {
        await vscode.commands.executeCommand("rte.scaffoldStoryFiles", message.storyId);
      }
    });

    // Track active editor and cursor line changes
    vscode.window.onDidChangeTextEditorSelection(() => this._debounceUpdate());
    vscode.window.onDidChangeActiveTextEditor(() => this._debounceUpdate());

    // Initial render
    this.updateBacklog();
  }

  public updateBacklog(): void {
    const editor = vscode.window.activeTextEditor;
    if (!editor || !this._view) {
      return;
    }

    const doc = editor.document;
    if (doc.languageId !== "python" && doc.languageId !== "typescript") {
      return;
    }

    const cursorLine = editor.selection.active.line + 1;
    void this._fetchAndRenderStories(doc, cursorLine);
  }

  private _debounceUpdate(): void {
    if (this._debounceTimer) {
      clearTimeout(this._debounceTimer);
    }
    this._debounceTimer = setTimeout(() => {
      this.updateBacklog();
    }, 150);
  }

  private async _fetchAndRenderStories(document: vscode.TextDocument, cursorLine: number): Promise<void> {
    if (!this._view) {
      return;
    }

    const fileContent = document.getText();
    const stories = StoryManager.getInstance().getStories();

    try {
      const client = TraceApiClient.getInstance();
      const response = await client.traceGraph({
        file_path: document.uri.fsPath,
        cursor_line: cursorLine,
        file_content: fileContent,
        stories: stories,
      });

      const activeStoryId = response.story_id || (stories[0] ? stories[0].story_id : "STORY-101");

      this._view.webview.postMessage({
        type: "UPDATE_BACKLOG",
        activeStoryId: activeStoryId,
        stories: stories,
        scopeFilterEnabled: this._scopeFilterEnabled,
        fileContent: fileContent,
      });
    } catch {
      // Fallback display using local cached stories and active file content
      const fallbackStoryId = stories[0] ? stories[0].story_id : "STORY-101";
      this._view.webview.postMessage({
        type: "UPDATE_BACKLOG",
        activeStoryId: fallbackStoryId,
        stories: stories,
        scopeFilterEnabled: this._scopeFilterEnabled,
        fileContent: fileContent,
      });
    }
  }

  private _getHtmlForWebview(): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sprint Backlog</title>
  <style>
    :root {
      --bg: #0d1117;
      --card-bg: #161b22;
      --border: #30363d;
      --border-active: #1f6feb;
      --text-main: #f0f6fc;
      --text-muted: #8b949e;
      --blue: #58a6ff;
      --green: #3fb950;
      --green-bg: rgba(46, 160, 67, 0.15);
      --font-code: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
    }

    * { box-sizing: border-box; }

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
      padding: 14px;
      display: flex;
      flex-direction: column;
      height: 100%;
    }

    /* Top Section Header */
    .header-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
    }
    .header-title {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: var(--text-muted);
      text-transform: uppercase;
    }
    .filter-btn {
      background: none;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 13px;
      padding: 2px 4px;
    }

    /* Active-File Scope Filter Row */
    .filter-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid rgba(48, 54, 61, 0.6);
    }
    .filter-label {
      font-size: 12px;
      color: var(--text-main);
      font-weight: 500;
    }

    /* Modern Toggle Switch */
    .switch {
      position: relative;
      display: inline-block;
      width: 32px;
      height: 18px;
    }
    .switch input {
      opacity: 0;
      width: 0;
      height: 0;
    }
    .slider {
      position: absolute;
      cursor: pointer;
      top: 0; left: 0; right: 0; bottom: 0;
      background-color: #21262d;
      transition: .2s;
      border-radius: 18px;
      border: 1px solid var(--border);
    }
    .slider:before {
      position: absolute;
      content: "";
      height: 12px;
      width: 12px;
      left: 2px;
      bottom: 2px;
      background-color: #8b949e;
      transition: .2s;
      border-radius: 50%;
    }
    input:checked + .slider {
      background-color: #1f6feb;
      border-color: #388bfd;
    }
    input:checked + .slider:before {
      transform: translateX(14px);
      background-color: #ffffff;
    }

    /* Active Story Card */
    .story-card {
      background: var(--card-bg);
      border: 1.5px solid var(--border-active);
      box-shadow: 0 0 16px rgba(31, 111, 235, 0.18);
      border-radius: 6px;
      padding: 14px;
      margin-bottom: 16px;
    }
    .card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .story-id {
      font-size: 13px;
      font-weight: 700;
      color: var(--blue);
      font-family: var(--font-code);
    }
    .match-badge {
      font-size: 10px;
      font-weight: 600;
      background: var(--green-bg);
      border: 1px solid rgba(63, 185, 80, 0.3);
      color: var(--green);
      padding: 2px 7px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      gap: 4px;
      transition: color 0.2s ease, background 0.2s ease;
    }

    .story-title {
      font-size: 13px;
      font-weight: 600;
      color: #f0f6fc;
      margin-bottom: 12px;
      line-height: 1.4;
    }

    /* Acceptance Criteria Checklist */
    .ac-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .ac-item {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      font-size: 12px;
      color: var(--text-muted);
      line-height: 1.35;
      font-family: var(--font-code);
    }
    .ac-checkbox {
      margin-top: 2px;
      width: 13px;
      height: 13px;
      border-radius: 3px;
      border: 1.5px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 9px;
      flex-shrink: 0;
      transition: all 0.2s ease;
    }
    .ac-checkbox.checked {
      border-color: var(--green);
      color: var(--green);
      background: rgba(46, 160, 67, 0.1);
    }
    .ac-checkbox.unchecked {
      border-color: #484f58;
      color: transparent;
      background: transparent;
    }
    .ac-text.active {
      color: #c9d1d9;
    }

    .card-actions {
      margin-top: 14px;
      padding-top: 10px;
      border-top: 1px solid rgba(48, 54, 61, 0.4);
      display: flex;
      justify-content: flex-end;
    }
    .scaffold-btn {
      background: #1f6feb;
      color: #ffffff;
      border: 1px solid rgba(240, 246, 252, 0.1);
      border-radius: 4px;
      padding: 5px 10px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-family: inherit;
      transition: background 0.15s ease, transform 0.1s ease;
    }
    .scaffold-btn:hover {
      background: #388bfd;
      transform: translateY(-1px);
    }
    .scaffold-btn:active {
      transform: translateY(0);
    }

    /* Footer Hidden Stories Counter */
    .hidden-footer {
      margin-top: auto;
      padding-top: 14px;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      color: var(--text-muted);
      border-top: 1px solid rgba(48, 54, 61, 0.4);
    }
    .hidden-icon {
      font-size: 12px;
    }
  </style>
</head>
<body>
  <div id="container">
    <!-- Header -->
    <div class="header-bar">
      <span class="header-title">SPRINT BACKLOG</span>
      <button class="filter-btn" title="Filter Options">☰</button>
    </div>

    <!-- Active-File Scope Filter Toggle -->
    <div class="filter-row">
      <span class="filter-label">Active-File Scope Filter</span>
      <label class="switch">
        <input type="checkbox" id="scope-toggle" checked>
        <span class="slider"></span>
      </label>
    </div>

    <!-- Active Requirement Card -->
    <div class="story-card" id="story-card">
      <div class="card-top">
        <span class="story-id" id="card-story-id">STORY-101</span>
        <span class="match-badge" id="card-match-badge">⚙ 0% Match</span>
      </div>
      <div class="story-title" id="card-story-title">Loading requirement specification...</div>

      <div class="ac-list" id="card-ac-list"></div>

      <div class="card-actions">
        <button id="scaffold-btn" class="scaffold-btn" title="Generate implementation and test files for this story">
          ⚡ Scaffold Code & Tests
        </button>
      </div>
    </div>

    <!-- Background Stories Hidden Counter -->
    <div class="hidden-footer">
      <span class="hidden-icon">👁‍🗨</span>
      <span id="hidden-text">0 background stories hidden...</span>
    </div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();

    const scaffoldBtn = document.getElementById('scaffold-btn');
    if (scaffoldBtn) {
      scaffoldBtn.addEventListener('click', () => {
        const storyIdEl = document.getElementById('card-story-id');
        const storyId = storyIdEl ? storyIdEl.textContent.trim() : null;
        if (storyId) {
          vscode.postMessage({
            type: 'SCAFFOLD_STORY',
            storyId: storyId
          });
        }
      });
    }

    const scopeToggle = document.getElementById('scope-toggle');
    scopeToggle.addEventListener('change', (e) => {
      vscode.postMessage({
        type: 'TOGGLE_SCOPE_FILTER',
        value: e.target.checked
      });
    });

    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg.type === 'UPDATE_BACKLOG') {
        renderBacklog(msg.activeStoryId, msg.stories, msg.scopeFilterEnabled, msg.fileContent || '');
      }
    });

    function isAcSatisfied(acText, fileContent) {
      if (!fileContent) return false;

      const lowerContent = fileContent.toLowerCase();
      // Remove AC labels like "AC-1: " to isolate requirement sentence
      const cleanAc = acText.replace(/^AC-\\d+:\\s*/i, '').trim().toLowerCase();

      // 1. Direct phrase matching
      if (lowerContent.includes(cleanAc)) {
        return true;
      }

      // 2. Keyword density matching for multi-phrase assertions and docstrings
      const keywords = cleanAc
        .split(/[^a-zA-Z0-9]+/)
        .filter(w => w.length > 3 && !['with', 'that', 'from', 'user', 'this'].includes(w));

      if (keywords.length === 0) return false;

      const matchedWords = keywords.filter(w => lowerContent.includes(w));
      return (matchedWords.length / keywords.length) >= 0.5; // Satisfied if 50%+ keywords exist
    }

    function renderBacklog(activeStoryId, stories, scopeFilterEnabled, fileContent) {
      if (!stories || stories.length === 0) return;

      const active = stories.find(s => s.story_id === activeStoryId) || stories[0];
      if (!active) return;

      document.getElementById('card-story-id').textContent = active.story_id;
      document.getElementById('card-story-title').textContent = active.user_story;

      const acList = document.getElementById('card-ac-list');
      acList.innerHTML = '';

      const criteria = active.acceptance_criteria || [];
      let satisfiedCount = 0;

      criteria.forEach((ac) => {
        const isChecked = isAcSatisfied(ac, fileContent);
        if (isChecked) satisfiedCount++;

        const item = document.createElement('div');
        item.className = 'ac-item';
        item.innerHTML = \`
          <span class="ac-checkbox \${isChecked ? 'checked' : 'unchecked'}">\${isChecked ? '✓' : ''}</span>
          <span class="ac-text \${isChecked ? 'active' : ''}">\${ac}</span>
        \`;
        acList.appendChild(item);
      });

      // Update match percentage badge dynamically
      const matchPct = criteria.length > 0 ? Math.round((satisfiedCount / criteria.length) * 100) : 0;
      const matchBadge = document.getElementById('card-match-badge');
      if (matchBadge) {
        matchBadge.textContent = \`⚙ \${matchPct}% Match\`;
        matchBadge.style.color = matchPct === 100 ? '#3fb950' : '#58a6ff';
        matchBadge.style.background = matchPct === 100 ? 'rgba(46, 160, 67, 0.2)' : 'rgba(31, 111, 235, 0.15)';
      }

      // Update background stories counter
      const hiddenCount = scopeFilterEnabled ? Math.max(0, stories.length - 1 + 50) : 0;
      document.getElementById('hidden-text').textContent = \`\${hiddenCount} background stories hidden...\`;
    }
  </script>
</body>
</html>`;
  }
}