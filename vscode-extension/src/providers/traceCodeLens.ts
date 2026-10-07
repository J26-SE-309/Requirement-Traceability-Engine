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

  const targetLine = Math.max(0, fn.start_line - 1);
  const range = new vscode.Range(targetLine, 0, targetLine, 0);

  const simStr = fn.similarity > 0 ? fn.similarity.toFixed(2) : "0.00";
  const storyId = fn.matched_story_id || "Unlinked";

  let title = "";
  if (fn.status === "VERIFIED" || fn.status === "MISSING_TEST") {
    const engineLabel = fn.source === "tag" ? "Tag Directive" : "SBERT Embeddings";
    title = `🔗 CodeLens: Traced to ${storyId} via ${engineLabel} (Cosine Sim: ${simStr})   [View Rationale]`;
  } else if (fn.status === "CANDIDATE") {
    title = `🔍 CodeLens: Candidate ${storyId} (Cosine Sim: ${simStr})   [View Rationale]`;
  } else {
    title = `⚠️ CodeLens: Unlinked Function (Best match: ${storyId} at ${simStr})   [Link Story]`;
  }

  const lens = new vscode.CodeLens(range, {
    title: title,
    command: "rte.showStoryDetails",
    arguments: [fn],
    tooltip: fn.rationale || "Click to inspect requirement link rationale",
  });

  codeLenses.push(lens);
}

    return codeLenses;
  }





public getFunctionAtLine(uriKey: string, line0Indexed: number): FunctionTraceStatus | undefined {
    const cached = this.cache.get(uriKey);
    if (!cached) {
      return undefined;
    }
    const line1Indexed = line0Indexed + 1;
    return cached.functions.find(
      (f) => line1Indexed >= f.start_line && line1Indexed <= f.end_line
    );
  }


}
