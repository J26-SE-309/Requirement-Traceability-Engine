/**
 * Sprint Backlog Sidebar Panel for Requirement Traceability Engine.
 *
 * Implements vscode.WebviewViewProvider to render:
 *  - Active-File Scope Filter toggle
 *  - Real-time search/filter input across all sprint backlog stories
 *  - High-confidence active requirement card with backend AI-evaluated AC checklist
 *  - Comprehensive list of all sprint backlog stories with per-story scaffolding
 *  - Full project-wide coverage evaluation so scaffolded/implemented stories remain marked
 */

import * as vscode from "vscode";
import { TraceApiClient } from "../api/client";
import { ACStatusItem, StoryRef } from "../api/types";
import { StoryManager } from "../stories/storyManager";
import { resolveWorkspaceRootUri } from "../utils/workspaceRoot";

export class TraceBacklogPanelProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "rte.backlogView";

  private _view?: vscode.WebviewView;
  private _scopeFilterEnabled: boolean = true;
  private _debounceTimer?: NodeJS.Timeout;

  constructor(private readonly _extensionUri: vscode.Uri) {}

  public async resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ): Promise<void> {
    this._view = webviewView;

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this._extensionUri],
    };

    webviewView.webview.html = this._getHtmlForWebview();

    // Listen to messages from the webview (e.g. toggle switch clicks, scaffold button, or refresh)
    webviewView.webview.onDidReceiveMessage(async (message) => {
      if (message.type === "TOGGLE_SCOPE_FILTER") {
        this._scopeFilterEnabled = message.value;
        this.updateBacklog();
      } else if (message.type === "SCAFFOLD_STORY") {
        await vscode.commands.executeCommand("rte.scaffoldStoryFiles", message.storyId);
      } else if (message.type === "REFRESH_BACKLOG") {
        await StoryManager.getInstance().reloadStories();
        this.updateBacklog();
      }
    });

    // Track active editor and cursor line changes
    vscode.window.onDidChangeTextEditorSelection(() => this._debounceUpdate());
    vscode.window.onDidChangeActiveTextEditor(() => this._debounceUpdate());

    // Initial load and render
    await StoryManager.getInstance().reloadStories();
    this.updateBacklog();
  }

  public updateBacklog(): void {
    if (!this._view) {
      return;
    }

    const stories = StoryManager.getInstance().getStories();
    const editor = vscode.window.activeTextEditor;
    const projectUri = resolveWorkspaceRootUri();
    const client = TraceApiClient.getInstance();

    if (!editor || (editor.document.languageId !== "python" && editor.document.languageId !== "typescript")) {
      void client
        .getCoverage({
          workspace_path: projectUri.fsPath,
          stories: stories,
        })
        .then((coverageRes) => {
          const coverageMap = this._buildCoverageMap(coverageRes);
          this._view?.webview.postMessage({
            type: "UPDATE_BACKLOG",
            activeStoryId: stories[0]?.story_id || "STORY-101",
            stories: stories,
            scopeFilterEnabled: this._scopeFilterEnabled,
            fileContent: "",
            activeAcStatuses: [],
            coverageMap: coverageMap,
          });
        })
        .catch(() => {
          this._view?.webview.postMessage({
            type: "UPDATE_BACKLOG",
            activeStoryId: stories[0]?.story_id || "STORY-101",
            stories: stories,
            scopeFilterEnabled: this._scopeFilterEnabled,
            fileContent: "",
            activeAcStatuses: [],
            coverageMap: {},
          });
        });
      return;
    }

    const cursorLine = editor.selection.active.line + 1;
    void this._fetchAndRenderStories(editor.document, cursorLine);
  }

  private _debounceUpdate(): void {
    if (this._debounceTimer) {
      clearTimeout(this._debounceTimer);
    }
    this._debounceTimer = setTimeout(() => {
      this.updateBacklog();
    }, 150);
  }

  private _buildCoverageMap(coverageRes: unknown): Record<string, { coveragePct: number; acStatuses: ACStatusItem[]; linkedFiles: string[]; hasTests: boolean }> {
    const map: Record<string, { coveragePct: number; acStatuses: ACStatusItem[]; linkedFiles: string[]; hasTests: boolean }> = {};
    const res = coverageRes as { items?: Array<{ story_id: string; coverage_pct: number; ac_statuses?: ACStatusItem[]; linked_artifacts?: Array<{ path?: string }>; has_linked_tests?: boolean }> } | null;
    if (res && Array.isArray(res.items)) {
      for (const it of res.items) {
        const files: string[] = [];
        if (Array.isArray(it.linked_artifacts)) {
          for (const a of it.linked_artifacts) {
            if (a.path) {
              const parts = a.path.replace(/\\/g, "/").split("/");
              files.push(parts.slice(-2).join("/"));
            }
          }
        }
        map[it.story_id] = {
          coveragePct: it.coverage_pct ?? 0,
          acStatuses: it.ac_statuses || [],
          linkedFiles: Array.from(new Set(files)),
          hasTests: Boolean(it.has_linked_tests),
        };
      }
    }
    return map;
  }

  private async _fetchAndRenderStories(document: vscode.TextDocument, cursorLine: number): Promise<void> {
    if (!this._view) {
      return;
    }

    const fileContent = document.getText();
    const stories = StoryManager.getInstance().getStories();
    const projectUri = resolveWorkspaceRootUri();

    try {
      const client = TraceApiClient.getInstance();
      const [graphResponse, coverageResponse] = await Promise.all([
        client.traceGraph({
          file_path: document.uri.fsPath,
          cursor_line: cursorLine,
          file_content: fileContent,
          stories: stories,
        }),
        client
          .getCoverage({
            workspace_path: projectUri.fsPath,
            stories: stories,
          })
          .catch(() => null),
      ]);

      const activeStoryId = graphResponse.story_id || (stories[0] ? stories[0].story_id : "STORY-101");
      const coverageMap = this._buildCoverageMap(coverageResponse);

      this._view.webview.postMessage({
        type: "UPDATE_BACKLOG",
        activeStoryId: activeStoryId,
        stories: stories,
        scopeFilterEnabled: this._scopeFilterEnabled,
        fileContent: fileContent,
        activeAcStatuses: (graphResponse.ac_statuses as ACStatusItem[]) || [],
        coverageMap: coverageMap,
      });
    } catch {
      const fallbackStoryId = stories[0] ? stories[0].story_id : "STORY-101";
      this._view.webview.postMessage({
        type: "UPDATE_BACKLOG",
        activeStoryId: fallbackStoryId,
        stories: stories,
        scopeFilterEnabled: this._scopeFilterEnabled,
        fileContent: fileContent,
        activeAcStatuses: [],
        coverageMap: {},
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
      --card-active-bg: #171e2e;
      --border: #30363d;
      --border-active: #1f6feb;
      --text-main: #f0f6fc;
      --text-muted: #8b949e;
      --blue: #58a6ff;
      --green: #3fb950;
      --green-bg: rgba(46, 160, 67, 0.15);
      --blue-bg: rgba(31, 111, 235, 0.15);
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
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-height: 100%;
    }

    /* Top Section Header */
    .header-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .header-title-wrap {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .header-title {
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      color: var(--text-muted);
      text-transform: uppercase;
    }
    .count-badge {
      font-size: 10px;
      font-weight: 600;
      background: var(--blue-bg);
      color: var(--blue);
      border: 1px solid rgba(88, 166, 255, 0.3);
      padding: 1px 6px;
      border-radius: 10px;
    }

    /* Search Input */
    .search-row {
      display: flex;
      width: 100%;
    }
    .search-input {
      width: 100%;
      background: #090d13;
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 6px 10px;
      color: var(--text-main);
      font-size: 12px;
      outline: none;
      transition: border-color 0.15s ease;
    }
    .search-input:focus {
      border-color: var(--blue);
    }
    .search-input::placeholder {
      color: var(--text-muted);
    }

    /* Active-File Scope Filter Row */
    .filter-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 10px;
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

    /* Section Subtitle */
    .section-label {
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.06em;
      color: var(--text-muted);
      text-transform: uppercase;
      margin-top: 4px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    /* Story Card */
    .story-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      margin-bottom: 10px;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    .story-card.active-card {
      background: var(--card-active-bg);
      border: 1.5px solid var(--border-active);
      box-shadow: 0 0 16px rgba(31, 111, 235, 0.22);
    }

    .card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 6px;
    }
    .id-cluster {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .story-id {
      font-size: 12px;
      font-weight: 700;
      color: var(--blue);
      font-family: var(--font-code);
    }
    .active-badge {
      font-size: 9px;
      font-weight: 700;
      color: #58a6ff;
      background: rgba(88, 166, 255, 0.12);
      border: 1px solid rgba(88, 166, 255, 0.3);
      padding: 1px 5px;
      border-radius: 4px;
      letter-spacing: 0.04em;
    }

    /* 3 Tripartite Status Badges */
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
    }
    .status-badge.status-verified {
      background: rgba(46, 160, 67, 0.18);
      border: 1px solid rgba(63, 185, 80, 0.45);
      color: #3fb950;
      box-shadow: 0 0 8px rgba(63, 185, 80, 0.15);
    }
    .status-badge.status-verified:hover {
      background: rgba(46, 160, 67, 0.28);
      border-color: rgba(63, 185, 80, 0.7);
    }
    .status-badge.status-missing-test {
      background: rgba(210, 153, 34, 0.18);
      border: 1px solid rgba(210, 153, 34, 0.45);
      color: #e3b341;
      box-shadow: 0 0 8px rgba(210, 153, 34, 0.15);
    }
    .status-badge.status-missing-test:hover {
      background: rgba(210, 153, 34, 0.28);
      border-color: rgba(210, 153, 34, 0.7);
    }
    .status-badge.status-unlinked {
      background: rgba(139, 148, 158, 0.12);
      border: 1px solid rgba(139, 148, 158, 0.25);
      color: var(--text-muted);
    }
    .status-badge.status-unlinked:hover {
      background: rgba(139, 148, 158, 0.20);
      color: #c9d1d9;
    }

    /* Status Filter Bar */
    .status-filter-bar {
      display: flex;
      gap: 5px;
      margin-bottom: 12px;
      overflow-x: auto;
      padding-bottom: 2px;
    }
    .status-filter-btn {
      background: #161b22;
      border: 1px solid #30363d;
      color: var(--text-muted);
      border-radius: 6px;
      padding: 4px 8px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 5px;
      transition: all 0.15s ease;
      white-space: nowrap;
    }
    .status-filter-btn:hover {
      border-color: #58a6ff;
      color: #f0f6fc;
      background: #1f242c;
    }
    .status-filter-btn.active {
      background: rgba(88, 166, 255, 0.15);
      border-color: #58a6ff;
      color: #58a6ff;
    }
    .status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      display: inline-block;
    }
    .dot-verified {
      background: #3fb950;
      box-shadow: 0 0 5px #3fb950;
    }
    .dot-missing {
      background: #e3b341;
      box-shadow: 0 0 5px #e3b341;
    }
    .dot-unlinked {
      background: #8b949e;
    }
    .filter-count {
      font-size: 10px;
      padding: 1px 5px;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.08);
      font-family: var(--font-code);
    }

    .linked-files {
      font-size: 10px;
      color: #7ee787;
      font-family: var(--font-code);
      margin-bottom: 6px;
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .story-title {
      font-size: 12px;
      font-weight: 500;
      color: #e6edf3;
      margin-bottom: 10px;
      line-height: 1.4;
    }

    /* Acceptance Criteria Checklist */
    .ac-toggle-header {
      font-size: 10px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin-bottom: 6px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .ac-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .ac-item {
      display: flex;
      align-items: flex-start;
      gap: 7px;
      font-size: 11px;
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
      background: rgba(46, 160, 67, 0.12);
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
      margin-top: 10px;
      padding-top: 8px;
      border-top: 1px solid rgba(48, 54, 61, 0.4);
      display: flex;
      justify-content: flex-end;
    }
    .scaffold-btn {
      background: #1f6feb;
      color: #ffffff;
      border: 1px solid rgba(240, 246, 252, 0.1);
      border-radius: 4px;
      padding: 4px 9px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 4px;
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

    /* Footer */
    .footer-bar {
      margin-top: auto;
      padding-top: 12px;
      font-size: 11px;
      color: var(--text-muted);
      border-top: 1px solid rgba(48, 54, 61, 0.4);
      text-align: center;
    }
  </style>
</head>
<body>
  <div id="container">
    <!-- Header -->
    <div class="header-bar">
      <div class="header-title-wrap">
        <span class="header-title">SPRINT BACKLOG</span>
        <span class="count-badge" id="sprint-count-badge">0 Stories</span>
      </div>
    </div>

    <!-- Search input -->
    <div class="search-row">
      <input type="text" id="search-input" class="search-input" placeholder="Filter backlog stories...">
    </div>

    <!-- Active-File Scope Filter Toggle -->
    <div class="filter-row">
      <span class="filter-label">Active-File Scope Filter</span>
      <label class="switch">
        <input type="checkbox" id="scope-toggle" checked>
        <span class="slider"></span>
      </label>
    </div>

    <!-- Tripartite Status Filter Tabs -->
    <div class="status-filter-bar">
      <button class="status-filter-btn active" data-status="ALL">
        All <span class="filter-count" id="count-all">0</span>
      </button>
      <button class="status-filter-btn" data-status="VERIFIED">
        <span class="status-dot dot-verified"></span> Verified <span class="filter-count" id="count-verified">0</span>
      </button>
      <button class="status-filter-btn" data-status="MISSING_TEST">
        <span class="status-dot dot-missing"></span> Missing Test <span class="filter-count" id="count-missing">0</span>
      </button>
      <button class="status-filter-btn" data-status="UNLINKED">
        <span class="status-dot dot-unlinked"></span> Unlinked <span class="filter-count" id="count-unlinked">0</span>
      </button>
    </div>

    <!-- Stories Render Target -->
    <div id="stories-wrapper">
      <div id="active-section-container"></div>
      <div id="all-stories-container"></div>
    </div>

    <!-- Footer Summary -->
    <div class="footer-bar">
      <span id="footer-text">Sprint backlog synchronized with RTE INT8 engine</span>
    </div>
  </div>

  <script>
    const vscode = acquireVsCodeApi();

    let currentStories = [];
    let currentActiveStoryId = null;
    let currentScopeFilter = true;
    let currentStatusFilter = 'ALL';
    let currentFileContent = '';
    let currentActiveAcStatuses = [];
    let currentCoverageMap = {};
    let currentSearchTerm = '';

    const scopeToggle = document.getElementById('scope-toggle');
    scopeToggle.addEventListener('change', (e) => {
      currentScopeFilter = e.target.checked;
      vscode.postMessage({
        type: 'TOGGLE_SCOPE_FILTER',
        value: currentScopeFilter
      });
      renderAll();
    });

    const searchInput = document.getElementById('search-input');
    searchInput.addEventListener('input', (e) => {
      currentSearchTerm = (e.target.value || '').trim().toLowerCase();
      renderAll();
    });

    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg.type === 'UPDATE_BACKLOG') {
        currentStories = msg.stories || [];
        currentActiveStoryId = msg.activeStoryId;
        currentScopeFilter = msg.scopeFilterEnabled ?? true;
        currentFileContent = msg.fileContent || '';
        currentActiveAcStatuses = msg.activeAcStatuses || [];
        currentCoverageMap = msg.coverageMap || {};

        scopeToggle.checked = currentScopeFilter;
        document.getElementById('sprint-count-badge').textContent = \`\${currentStories.length} Stories\`;

        renderAll();
      }
    });

    function isAcSatisfiedFallback(acText, fileContent) {
      if (!fileContent) return false;
      const lowerContent = fileContent.toLowerCase();
      const cleanAc = acText.replace(/^AC-\\d+:\\s*/i, '').trim().toLowerCase();

      if (lowerContent.includes(cleanAc)) return true;

      const keywords = cleanAc
        .split(/[^a-zA-Z0-9]+/)
        .filter(w => w.length > 3 && !['with', 'that', 'from', 'user', 'this', 'into'].includes(w));
      if (keywords.length === 0) return false;

      const matchedWords = keywords.filter(w => lowerContent.includes(w));
      return (matchedWords.length / keywords.length) >= 0.5;
    }

    function createStoryCard(story, isActive) {
      const criteria = story.acceptance_criteria || [];
      const cov = currentCoverageMap[story.story_id];
      let satisfiedCount = 0;

      const acItemsHtml = criteria.map((ac, idx) => {
        let isChecked = false;
        const cleanAc = ac.replace(/^AC-\\d+:\\s*/i, '').trim().toLowerCase();

        // 1. If this card is currently open in active editor, use active real-time AST AC status
        if (isActive && currentActiveAcStatuses && currentActiveAcStatuses.length > 0) {
          const match = currentActiveAcStatuses.find(st => {
            if (!st || !st.criterion) return false;
            const itemCrit = st.criterion.replace(/^AC-\\d+:\\s*/i, '').trim().toLowerCase();
            return itemCrit === cleanAc || itemCrit.includes(cleanAc) || cleanAc.includes(itemCrit);
          });
          if (match) {
            isChecked = Boolean(match.satisfied);
          }
        }

        // 2. Project-wide workspace coverage check (preserves checks for scaffolded stories!)
        if (!isChecked && cov && cov.acStatuses && cov.acStatuses.length > 0) {
          const covMatch = cov.acStatuses.find(st => {
            if (!st || !st.criterion) return false;
            const itemCrit = st.criterion.replace(/^AC-\\d+:\\s*/i, '').trim().toLowerCase();
            return itemCrit === cleanAc || itemCrit.includes(cleanAc) || cleanAc.includes(itemCrit);
          });
          if (covMatch) {
            isChecked = Boolean(covMatch.satisfied);
          }
        }

        // 3. Fallback only if active editor matches
        if (!isChecked && isActive) {
          isChecked = isAcSatisfiedFallback(ac, currentFileContent);
        }

        if (isChecked) satisfiedCount++;

        return \`
          <div class="ac-item">
            <span class="ac-checkbox \${isChecked ? 'checked' : 'unchecked'}">\${isChecked ? '✓' : ''}</span>
            <span class="ac-text \${isChecked ? 'active' : ''}">AC-\${idx + 1}: \${ac}</span>
          </div>
        \`;
      }).join('');

      // 3 Tripartite Status Resolution (VERIFIED, MISSING TEST, UNLINKED)
      const hasLinkedFiles = Boolean(cov && cov.linkedFiles && cov.linkedFiles.length > 0);
      const hasCoverage = Boolean(cov && cov.coveragePct > 0);
      const isImplemented = hasLinkedFiles || hasCoverage || (satisfiedCount > 0) || isActive;
      const hasTests = Boolean(cov && cov.hasTests);
      const matchPct = criteria.length > 0 ? Math.round((satisfiedCount / criteria.length) * 100) : (cov ? Math.round((cov.coveragePct || 0) * 100) : 0);

      let badgeHtml = '';
      if (isImplemented && hasTests) {
        const pctLabel = (cov && cov.coveragePct >= 1.0) ? '100%' : \`\${matchPct}%\`;
        badgeHtml = \`<span class="status-badge status-verified">✓ VERIFIED (\${pctLabel})</span>\`;
      } else if (isImplemented && !hasTests) {
        badgeHtml = '<span class="status-badge status-missing-test">⚠️ MISSING TEST</span>';
      } else {
        badgeHtml = '<span class="status-badge status-unlinked">○ UNLINKED</span>';
      }

      let linkedHtml = '';
      if (cov && cov.linkedFiles && cov.linkedFiles.length > 0) {
        linkedHtml = \`<div class="linked-files">📁 \${cov.linkedFiles.join(', ')}</div>\`;
      }

      const card = document.createElement('div');
      card.className = \`story-card \${isActive ? 'active-card' : ''}\`;
      card.id = \`card-\${story.story_id}\`;
      card.innerHTML = \`
        <div class="card-top">
          <div class="id-cluster">
            <span class="story-id">\${story.story_id}</span>
            \${isActive ? '<span class="active-badge">● ACTIVE IN FILE</span>' : ''}
          </div>
          \${badgeHtml}
        </div>
        \${linkedHtml}
        <div class="story-title">\${story.user_story}</div>
        <div class="ac-toggle-header">
          <span>ACCEPTANCE CRITERIA (\${satisfiedCount}/\${criteria.length})</span>
        </div>
        <div class="ac-list">
          \${acItemsHtml}
        </div>
        <div class="card-actions">
          <button class="scaffold-btn" data-story-id="\${story.story_id}" title="Generate clean Python functions and test suites">
            ⚡ Scaffold Code & Tests
          </button>
        </div>
      \`;

      const scaffoldBtn = card.querySelector('.scaffold-btn');
      if (scaffoldBtn) {
        scaffoldBtn.addEventListener('click', () => {
          vscode.postMessage({
            type: 'SCAFFOLD_STORY',
            storyId: story.story_id
          });
        });
      }

      return card;
    }

    // Attach click listeners to status filter buttons
    document.querySelectorAll('.status-filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.status-filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentStatusFilter = btn.dataset.status;
        renderAll();
      });
    });

    function renderAll() {
      const activeContainer = document.getElementById('active-section-container');
      const allContainer = document.getElementById('all-stories-container');
      activeContainer.innerHTML = '';
      allContainer.innerHTML = '';

      if (!currentStories || currentStories.length === 0) {
        allContainer.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; text-align: center; padding: 20px;">No stories found in sprint backlog.</div>';
        return;
      }

      // Calculate status counts across all stories
      let countVerified = 0;
      let countMissing = 0;
      let countUnlinked = 0;

      currentStories.forEach(s => {
        const cov = currentCoverageMap[s.story_id];
        const hasLinkedFiles = Boolean(cov && cov.linkedFiles && cov.linkedFiles.length > 0);
        const hasCoverage = Boolean(cov && cov.coveragePct > 0);
        const isImpl = hasLinkedFiles || hasCoverage || (s.story_id === currentActiveStoryId);
        const hasT = Boolean(cov && cov.hasTests);
        if (isImpl && hasT) {
          countVerified++;
        } else if (isImpl && !hasT) {
          countMissing++;
        } else {
          countUnlinked++;
        }
      });

      const countAllEl = document.getElementById('count-all');
      if (countAllEl) countAllEl.textContent = currentStories.length;
      const countVerEl = document.getElementById('count-verified');
      if (countVerEl) countVerEl.textContent = countVerified;
      const countMisEl = document.getElementById('count-missing');
      if (countMisEl) countMisEl.textContent = countMissing;
      const countUnlEl = document.getElementById('count-unlinked');
      if (countUnlEl) countUnlEl.textContent = countUnlinked;

      let filtered = currentStories;
      if (currentSearchTerm) {
        filtered = filtered.filter(s => {
          const matchId = s.story_id.toLowerCase().includes(currentSearchTerm);
          const matchStory = s.user_story.toLowerCase().includes(currentSearchTerm);
          const matchAcs = (s.acceptance_criteria || []).some(a => a.toLowerCase().includes(currentSearchTerm));
          return matchId || matchStory || matchAcs;
        });
      }

      if (currentStatusFilter !== 'ALL') {
        filtered = filtered.filter(s => {
          const cov = currentCoverageMap[s.story_id];
          const hasLinkedFiles = Boolean(cov && cov.linkedFiles && cov.linkedFiles.length > 0);
          const hasCoverage = Boolean(cov && cov.coveragePct > 0);
          const isImpl = hasLinkedFiles || hasCoverage || (s.story_id === currentActiveStoryId);
          const hasT = Boolean(cov && cov.hasTests);
          const st = (isImpl && hasT) ? 'VERIFIED' : ((isImpl && !hasT) ? 'MISSING_TEST' : 'UNLINKED');
          return st === currentStatusFilter;
        });
      }

      const activeStory = currentStories.find(s => s.story_id === currentActiveStoryId) || currentStories[0];

      if (currentScopeFilter && activeStory && (!currentSearchTerm || filtered.includes(activeStory)) && (currentStatusFilter === 'ALL' || filtered.includes(activeStory))) {
        // Section 1: Active Requirement Focus
        const activeLabel = document.createElement('div');
        activeLabel.className = 'section-label';
        activeLabel.innerHTML = '<span>ACTIVE REQUIREMENT</span>';
        activeContainer.appendChild(activeLabel);
        activeContainer.appendChild(createStoryCard(activeStory, true));

        // Section 2: Other Sprint Stories
        const otherStories = filtered.filter(s => s.story_id !== activeStory.story_id);
        if (otherStories.length > 0) {
          const otherLabel = document.createElement('div');
          otherLabel.className = 'section-label';
          otherLabel.style.marginTop = '14px';
          otherLabel.innerHTML = \`<span>ALL SPRINT STORIES (\${otherStories.length})</span>\`;
          allContainer.appendChild(otherLabel);

          otherStories.forEach(s => {
            allContainer.appendChild(createStoryCard(s, false));
          });
        }
      } else {
        // Uniform list of all filtered stories
        const listLabel = document.createElement('div');
        listLabel.className = 'section-label';
        listLabel.innerHTML = \`<span>ALL SPRINT STORIES (\${filtered.length})</span>\`;
        allContainer.appendChild(listLabel);

        filtered.forEach(s => {
          const isActive = s.story_id === currentActiveStoryId;
          allContainer.appendChild(createStoryCard(s, isActive));
        });
      }

      document.getElementById('footer-text').textContent = \`Displaying \${filtered.length} of \${currentStories.length} backlog stories\`;
    }
  </script>
</body>
</html>`;
  }
}