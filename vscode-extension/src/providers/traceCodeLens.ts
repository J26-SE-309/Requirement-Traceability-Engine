/**
 * Resilient Inline CodeLens Provider for Requirement Traceability Engine.
 *
 * Prevents UI flickers, awaits initial indexing, and keeps current lenses
 * visible while background AST delta analysis runs.
 */

import * as vscode from "vscode";
import { TraceApiClient } from "../api/client";
import { FunctionTraceStatus } from "../api/types";
import { StoryManager } from "../stories/storyManager";

export class TraceCodeLensProvider implements vscode.CodeLensProvider {
  private _onDidChangeCodeLenses: vscode.EventEmitter<void> = new vscode.EventEmitter<void>();
  public readonly onDidChangeCodeLenses: vscode.Event<void> = this._onDidChangeCodeLenses.event;

  private cache: Map<string, FunctionTraceStatus[]> = new Map();
  private isAnalyzing: Set<string> = new Set();
  private debounceTimer: NodeJS.Timeout | null = null;

  constructor() {
    vscode.workspace.onDidChangeTextDocument((e) => {
      if (e.document.languageId === "python" || e.document.languageId === "typescript") {
        this.debounceRefresh(e.document);
      }
    });

    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (doc.languageId === "python" || doc.languageId === "typescript") {
        void this.fetchTrace(doc, true);
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
      void this.fetchTrace(document, false);
    }, 300);
  }

  /**
   * Fetches latest trace analysis from the local FastAPI backend.
   */
  public async fetchTrace(document: vscode.TextDocument, isSaveEvent: boolean = false): Promise<FunctionTraceStatus[]> {
    const config = vscode.workspace.getConfiguration("rte");
    if (!config.get<boolean>("enableCodeLens", true)) {
      return [];
    }

    const uriKey = document.uri.toString();
    if (this.isAnalyzing.has(uriKey)) {
      return this.cache.get(uriKey) || [];
    }

    this.isAnalyzing.add(uriKey);
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

      if (response && Array.isArray(response.functions)) {
        if (deltaOnly && this.cache.has(uriKey)) {
          const prev = this.cache.get(uriKey) || [];
          const updatedNames = new Set(response.functions.map((f) => f.name));
          const merged = prev.filter((f) => !updatedNames.has(f.name)).concat(response.functions);
          merged.sort((a, b) => a.start_line - b.start_line);
          this.cache.set(uriKey, merged);
        } else {
          response.functions.sort((a, b) => a.start_line - b.start_line);
          this.cache.set(uriKey, response.functions);
        }

        this._onDidChangeCodeLenses.fire();
        return this.cache.get(uriKey) || [];
      }
    } catch (err) {
      console.error("[RTE CodeLens] Error connecting to trace backend:", err);
    } finally {
      this.isAnalyzing.delete(uriKey);
    }

    return this.cache.get(uriKey) || [];
  }

  public async provideCodeLenses(
    document: vscode.TextDocument,
    token: vscode.CancellationToken
  ): Promise<vscode.CodeLens[]> {
    const config = vscode.workspace.getConfiguration("rte");
    if (!config.get<boolean>("enableCodeLens", true)) {
      return [];
    }

    const uriKey = document.uri.toString();
    let functions = this.cache.get(uriKey);

    // Initial load: await fetch if cache is empty
    if (!functions) {
      functions = await this.fetchTrace(document, false);
    }

    if (!functions || functions.length === 0) {
      return [];
    }

    const codeLenses: vscode.CodeLens[] = [];
    const maxLine = Math.max(0, document.lineCount - 1);

    for (const fn of functions) {
      if (token.isCancellationRequested) {
        return [];
      }

      // Convert 1-indexed AST start_line to 0-indexed editor line
      const rawTargetLine = Math.max(0, fn.start_line - 1);
      const targetLine = Math.min(rawTargetLine, maxLine);
      const range = new vscode.Range(targetLine, 0, targetLine, 0);

      const simStr = fn.similarity > 0 ? fn.similarity.toFixed(2) : "0.00";
      const storyId = fn.matched_story_id || "Unlinked";
      const engineLabel = fn.source === "tag" ? "Tag Directive" : "SBERT Embeddings";

      let title = "";
      if (fn.status === "VERIFIED") {
        title = `🔗 CodeLens: Traced to ${storyId} via ${engineLabel} (Cosine Sim: ${simStr})   [View Rationale]`;
      } else if (fn.status === "MISSING_TEST") {
        title = `⚠️ CodeLens: Traced to ${storyId} | Test: ❌ Missing Assertion (Cosine Sim: ${simStr})   [View Rationale]`;
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
    const functions = this.cache.get(uriKey);
    if (!functions) {
      return undefined;
    }
    const line1Indexed = line0Indexed + 1;
    return functions.find((f) => line1Indexed >= f.start_line && line1Indexed <= f.end_line);
  }
}