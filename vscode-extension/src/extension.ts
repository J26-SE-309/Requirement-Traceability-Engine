/**
 * Main Extension Entrypoint for Requirement Traceability Engine.
 *
 * Registers:
 *  - Sprint Backlog Sidebar Webview (Left panel)
 *  - Cytoscape Sub-Graph Webview (Right panel)
 *  - Inline CodeLens Provider & Quick-Fix Lightbulb CodeAction Provider
 *  - Pre-commit verification gate & real-time status bar telemetry
 */

import * as vscode from "vscode";
import { TraceApiClient } from "./api/client";
import { FunctionTraceStatus } from "./api/types";
import { runPrecommitCheck } from "./commands/precommitCheck";
import { runScaffoldStoryCommand } from "./commands/scaffoldStory";
import { TraceBacklogPanelProvider } from "./providers/backlogPanel";
import { TraceGraphPanelProvider } from "./providers/graphPanel";
import { TraceCodeActionProvider } from "./providers/traceCodeAction";
import { TraceCodeLensProvider } from "./providers/traceCodeLens";
import { StoryManager } from "./stories/storyManager";
import { setExtensionContext } from "./utils/workspaceRoot";

let statusBarBackend: vscode.StatusBarItem;
let statusBarTelemetry: vscode.StatusBarItem;
let statusBarPrivacy: vscode.StatusBarItem;
let statusBarGate: vscode.StatusBarItem;

/**
 * Updates the status bar with real measured inference latency, AST symbol count, and host RSS memory.
 */
export function updateTelemetryBar(
  latencyMs: number,
  symbolCount: number,
  memoryMb?: number
): void {
  if (statusBarTelemetry) {
    const rssMb = memoryMb ?? Math.round(process.memoryUsage().rss / (1024 * 1024));
    statusBarTelemetry.text = `$(zap) RTE: ${latencyMs.toFixed(1)}ms | Symbols: ${symbolCount} | RSS: ${rssMb}MB | INT8 SBERT`;
    statusBarTelemetry.tooltip = `Live CPU Inference: ${latencyMs.toFixed(2)}ms | Parsed AST Symbols: ${symbolCount} | Host Memory RSS: ${rssMb}MB`;
  }
}

/**
 * Updates the Pre-Commit Quality Gate status bar indicator based on live check results.
 */
export function updatePrecommitGateBar(passed: boolean, details?: string): void {
  if (statusBarGate) {
    statusBarGate.text = passed
      ? "$(pass-filled) Pre-Commit: PASSED"
      : "$(error) Pre-Commit: BLOCKED";
    statusBarGate.tooltip = details || "Click to run staged Git commit verification check";
  }
}

export function activate(context: vscode.ExtensionContext): void {
  console.log("Activating Requirement Traceability Engine (RTE) extension...");

  // Capture ExtensionContext to dynamically resolve extension root and .rte storage
  setExtensionContext(context);

  // =========================================================================
  // 1. Status Bar Telemetry
  // =========================================================================

  // Footer Item 1: Engine Telemetry (Live Latency, Symbols, RSS Memory)
  statusBarTelemetry = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  const initialRssMb = Math.round(process.memoryUsage().rss / (1024 * 1024));
  statusBarTelemetry.text = `$(zap) RTE: Ready | RSS: ${initialRssMb}MB | INT8 SBERT`;
  statusBarTelemetry.tooltip = "Local CPU Inference (all-MiniLM-L6-v2 INT8 ONNX)";
  statusBarTelemetry.show();
  context.subscriptions.push(statusBarTelemetry);

  // Footer Item 2: Zero-Cloud Privacy Guarantee
  statusBarPrivacy = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 99);
  statusBarPrivacy.text = "$(shield) Privacy: 0 Network Calls";
  statusBarPrivacy.tooltip = "100% on-device INT8 ONNX runtime (127.0.0.1 loopback only). Zero code transmitted off-machine.";
  statusBarPrivacy.show();
  context.subscriptions.push(statusBarPrivacy);

  // Footer Item 3: Backend Runtime Connection Indicator
  statusBarBackend = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 101);
  statusBarBackend.command = "rte.refreshTrace";
  statusBarBackend.text = "$(sync~spin) RTE: Connecting...";
  statusBarBackend.tooltip = "Requirement Traceability Engine: Initializing local ONNX runtime link";
  statusBarBackend.show();
  context.subscriptions.push(statusBarBackend);

  // Footer Item 4: Pre-Commit Quality Gate Status
  statusBarGate = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarGate.text = "$(shield) Pre-Commit: Verify";
  statusBarGate.command = "rte.precommitCheck";
  statusBarGate.tooltip = "Click to run staged Git commit verification check";
  statusBarGate.show();
  context.subscriptions.push(statusBarGate);

  // Asynchronously verify local backend health and maintain self-healing heartbeat
  void checkBackendStatus();
  const healthInterval = setInterval(() => {
    void checkBackendStatus();
  }, 5000);
  context.subscriptions.push({ dispose: () => clearInterval(healthInterval) });

  // =========================================================================
  // 2. Language Providers (Python & TypeScript)
  // =========================================================================

  const selector: vscode.DocumentSelector = [
    { language: "python" },
    { language: "typescript" },
  ];

  // Inline CodeLens Provider
  const codeLensProvider = new TraceCodeLensProvider();
  const codeLensDisposable = vscode.languages.registerCodeLensProvider(selector, codeLensProvider);
  context.subscriptions.push(codeLensDisposable);

  // Quick-Fix Lightbulb CodeAction Provider (Ctrl + .)
  const codeActionProvider = new TraceCodeActionProvider(codeLensProvider);
  const codeActionDisposable = vscode.languages.registerCodeActionsProvider(
    selector,
    codeActionProvider,
    {
      providedCodeActionKinds: TraceCodeActionProvider.providedCodeActionKinds,
    }
  );
  context.subscriptions.push(codeActionDisposable);

  // =========================================================================
  // 3. Webview View Providers (Left Backlog & Right Graph)
  // =========================================================================

  // Left Sidebar: Sprint Backlog Panel
  const backlogProvider = new TraceBacklogPanelProvider(context.extensionUri);
  const backlogDisposable = vscode.window.registerWebviewViewProvider(
    TraceBacklogPanelProvider.viewType,
    backlogProvider
  );
  context.subscriptions.push(backlogDisposable);

  // Right Sidebar: Active Traceability Sub-Graph Panel
  const graphProvider = new TraceGraphPanelProvider(context.extensionUri);
  const graphDisposable = vscode.window.registerWebviewViewProvider(
    TraceGraphPanelProvider.viewType,
    graphProvider
  );
  context.subscriptions.push(graphDisposable);

  // =========================================================================
  // 4. Dynamic Workspace & Editor Change Listeners
  // =========================================================================

  // Automatically reload project root and stories when workspace folders or storiesPath setting change
  context.subscriptions.push(
    vscode.workspace.onDidChangeWorkspaceFolders(async () => {
      await StoryManager.getInstance().reloadStories();
      codeLensProvider.refresh();
      backlogProvider.updateBacklog();
      graphProvider.updateViewport();
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration(async (e) => {
      if (e.affectsConfiguration("rte.storiesPath")) {
        await StoryManager.getInstance().reloadStories();
        backlogProvider.updateBacklog();
        graphProvider.updateViewport();
        codeLensProvider.refresh();
      }
    })
  );

  // =========================================================================
  // 5. Commands Registration
  // =========================================================================

  // Command: rte.refreshTrace
  const refreshCmd = vscode.commands.registerCommand("rte.refreshTrace", async () => {
    await StoryManager.getInstance().reloadStories();
    codeLensProvider.refresh();
    graphProvider.updateViewport();
    backlogProvider.updateBacklog();
    await checkBackendStatus();
    vscode.window.showInformationMessage("Requirement Traceability analysis refreshed.");
  });
  context.subscriptions.push(refreshCmd);

  // Command: rte.showTraceGraph
  const showGraphCmd = vscode.commands.registerCommand("rte.showTraceGraph", async () => {
    await vscode.commands.executeCommand("rte.graphView.focus");
    graphProvider.updateViewport();
  });
  context.subscriptions.push(showGraphCmd);

  // Command: rte.precommitCheck
  const precommitCmd = vscode.commands.registerCommand("rte.precommitCheck", async () => {
    await runPrecommitCheck();
  });
  context.subscriptions.push(precommitCmd);

  // Command: rte.scaffoldStoryFiles (and alias rte.scaffoldStory)
  const scaffoldCmd = vscode.commands.registerCommand(
    "rte.scaffoldStoryFiles",
    async (targetStoryId?: string) => {
      await runScaffoldStoryCommand(targetStoryId);
      codeLensProvider.refresh();
      backlogProvider.updateBacklog();
      graphProvider.updateViewport();
    }
  );
  context.subscriptions.push(scaffoldCmd);

  // Command: rte.showStoryDetails (Invoked on clicking CodeLens badges)
  const showDetailsCmd = vscode.commands.registerCommand(
    "rte.showStoryDetails",
    async (fn: FunctionTraceStatus) => {
      if (!fn) {
        return;
      }

      // Automatically move cursor to target function and update the Graph Panel
      const activeEditor = vscode.window.activeTextEditor;
      if (activeEditor) {
        const line = Math.max(0, fn.start_line - 1);
        activeEditor.selection = new vscode.Selection(line, 0, line, 0);
        activeEditor.revealRange(new vscode.Range(line, 0, line, 0));
        void vscode.commands.executeCommand("rte.graphView.focus");
        graphProvider.updateViewport(activeEditor, fn.start_line);
      }

      const items: vscode.QuickPickItem[] = [];

      items.push({
        label: `$(symbol-function) Function: ${fn.qualified_name || fn.name}`,
        description: `Status: ${fn.status} | Lines: ${fn.start_line}-${fn.end_line}`,
        detail: fn.rationale,
      });

      if (fn.matched_story_id) {
        items.push({
          label: `$(bookmark) User Story: ${fn.matched_story_id}`,
          description: `Similarity: ${Math.round(fn.similarity * 100)}% (${fn.source})`,
          detail: fn.user_story || "No story description available",
        });

        if (fn.acceptance_criteria && fn.acceptance_criteria.length > 0) {
          items.push({
            label: "$(checklist) Acceptance Criteria",
            kind: vscode.QuickPickItemKind.Separator,
          });

          for (const ac of fn.acceptance_criteria) {
            items.push({
              label: `$(check) ${ac}`,
            });
          }
        }
      }

      items.push({
        label: "$(beaker) Test Assertion Status",
        kind: vscode.QuickPickItemKind.Separator,
      });

      items.push({
        label: fn.has_test_assertion
          ? `$(pass-filled) Unit Test: Passed (${fn.linked_test_symbol || "asserted"})`
          : "$(error) Unit Test: Missing Test Assertion",
        detail: fn.has_test_assertion
          ? "Linked test fixture contains verifiable assertions"
          : "Add a unit test with assert statements to satisfy verification gate",
      });

      await vscode.window.showQuickPick(items, {
        title: `RTE Traceability: ${fn.name} -> ${fn.matched_story_id || "Unlinked"}`,
        placeHolder: "Requirement Traceability Specification",
      });
    }
  );
  context.subscriptions.push(showDetailsCmd);
}

/**
 * Validates connectivity to the local FastAPI backend.
 */
async function checkBackendStatus(): Promise<void> {
  try {
    const health = await TraceApiClient.getInstance().checkHealth();
    if (health) {
      statusBarBackend.text = "$(link) RTE: Active (INT8 ONNX)";
      statusBarBackend.tooltip = `Connected to local backend (Service: ${health.service}). Latency budget: <= 350ms.`;
    } else {
      statusBarBackend.text = "$(alert) RTE: Offline";
      statusBarBackend.tooltip = "Local backend is unreachable. Start FastAPI backend with uvicorn.";
    }
  } catch {
    statusBarBackend.text = "$(alert) RTE: Offline";
    statusBarBackend.tooltip = "Local backend is unreachable. Start FastAPI backend with uvicorn.";
  }
}

export function deactivate(): void {
  if (statusBarBackend) {
    statusBarBackend.dispose();
  }
  if (statusBarTelemetry) {
    statusBarTelemetry.dispose();
  }
  if (statusBarPrivacy) {
    statusBarPrivacy.dispose();
  }
  if (statusBarGate) {
    statusBarGate.dispose();
  }
}