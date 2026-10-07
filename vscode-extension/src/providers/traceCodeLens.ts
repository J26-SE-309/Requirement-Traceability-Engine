/**
 * Inline CodeLens Provider for Requirement Traceability Engine.
 *
 * Places inline decorations directly above detected function definitions,
 * visualizing tripartite verification state:
 * - VERIFIED (>= 0.80 + test assertion)
 * - MISSING_TEST (>= 0.80 without test assertion)
 * - CANDIDATE (0.65 - 0.79)
 * - ORPHAN (< 0.65)
 */

import * as vscode from "vscode";
import { TraceApiClient } from "../api/client";
import { FunctionTraceStatus } from "../api/types";
import { StoryManager } from "../stories/storyManager";

export class TraceCodeLensProvider implements vscode.CodeLensProvider {
  private _onDidChangeCodeLenses: vscode.EventEmitter<void> = new vscode.EventEmitter<void>();
  public readonly onDidChangeCodeLenses: vscode.Event<void> = this._onDidChangeCodeLenses.event;

  private cache: Map<string, { version: number; functions: FunctionTraceStatus[] }> = new Map();
  private pendingRequests: Set<string> = new Set();
  private debounceTimer: NodeJS.Timeout | null = null;

  constructor() {
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (e.document.languageId === "python" || e.document.languageId === "typescript") {
        this.debounceRefresh(e.document);
      }
    });

    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (doc.languageId === "python" || doc.languageId === "typescript") {
        this.refreshDocument(doc, true);
      }
    });
  }

  public refresh(): void {
    this.cache.clear();
    this._onDidChangeCodeLenses.fire();
  }

  private debounceRefresh(document: vscode.TextDocument): void {
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }
    this.debounceTimer = setTimeout(() => {
      this.refreshDocument(document, false);
    }, 300);
  }

  public async refreshDocument(document: vscode.TextDocument, isSaveEvent: boolean = false): Promise<void> {
    const config = vscode.workspace.getConfiguration("rte");
    if (!config.get<boolean>("enableCodeLens", true)) {
      return;
    }

    const uriKey = document.uri.toString();
    if (this.pendingRequests.has(uriKey)) {
      return;
    }

    this.pendingRequests.add(uriKey);
    try {
      const client = TraceApiClient.getInstance();
      const stories = StoryManager.getInstance().getStories();
      const deltaOnly = isSaveEvent && config.get<boolean>("autoDeltaOnSave", true);

      const response = await client.traceFile({
        file_path: document.uri.fsPath,
        file_content: document.getText(),
        stories: stories,
        delta_only: deltaOnly,
      });

      if (response && response.functions) {
        if (deltaOnly && this.cache.has(uriKey)) {
          // Merge delta functions into existing cached functions
          const prev = this.cache.get(uriKey)!.functions;
          const updatedNames = new Set(response.functions.map((f) => f.name));
          const merged = prev.filter((f) => !updatedNames.has(f.name)).concat(response.functions);
          this.cache.set(uriKey, { version: document.version, functions: merged });
        } else {
          this.cache.set(uriKey, { version: document.version, functions: response.functions });
        }
        this._onDidChangeCodeLenses.fire();
      }
    } catch (err) {
      console.warn("RTE CodeLens background trace failed:", err);
    } finally {
      this.pendingRequests.delete(uriKey);
    }
  }

  public provideCodeLenses(
    document: vscode.TextDocument,
    token: vscode.CancellationToken
  ): vscode.CodeLens[] | Thenable<vscode.CodeLens[]> {
    const config = vscode.workspace.getConfiguration("rte");
    if (!config.get<boolean>("enableCodeLens", true)) {
      return [];
    }

    const uriKey = document.uri.toString();
    const cached = this.cache.get(uriKey);

    if (!cached) {
      // Trigger async analysis if not cached
      void this.refreshDocument(document, false);
      return [];
    }

    const codeLenses: vscode.CodeLens[] = [];

    for (const fn of cached.functions) {
      if (token.isCancellationRequested) {
        return [];
      }

      // Convert 1-indexed start_line to 0-indexed VS Code Line
      const targetLine = Math.max(0, fn.start_line - 1);
      const range = new vscode.Range(targetLine, 0, targetLine, 0);

      const simPct = Math.round(fn.similarity * 100);
      const storyId = fn.matched_story_id || "Unspecified";

      let title: string;
      if (fn.status === "VERIFIED") {
        title = `🔗 Traced to: ${storyId} (${simPct}%) | Test: ✅ Passed`;
      } else if (fn.status === "MISSING_TEST") {
        title = `⚠️ Traced to: ${storyId} | Test: ❌ Missing Test Assertion`;
      } else if (fn.status === "CANDIDATE") {
        title = `🔍 Candidate: ${storyId} (${simPct}%) | Needs Review`;
      } else {
        // ORPHAN
        title = `⚠️ Unlinked Function (Best match: ${storyId} at ${simPct}%)`;
      }

      const lens = new vscode.CodeLens(range, {
        title: title,
        command: "rte.showStoryDetails",
        arguments: [fn],
        tooltip: `${fn.rationale}\nClick to view acceptance criteria and rationale.`,
      });

      codeLenses.push(lens);
    }

    return codeLenses;
  }
}
