/**
 * Main Extension Entrypoint for Requirement Traceability Engine.
 *
 * Registers CodeLens provider, Cytoscape graph WebviewView,
 * pre-commit verification gate, and status bar telemetry.
 */

import * as vscode from "vscode";
import { TraceApiClient } from "./api/client";
import { FunctionTraceStatus } from "./api/types";
import { runPrecommitCheck } from "./commands/precommitCheck";
import { TraceGraphPanelProvider } from "./providers/graphPanel";
import { TraceCodeLensProvider } from "./providers/traceCodeLens";
import { StoryManager } from "./stories/storyManager";

let statusBarItem: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext): void {
  console.log("Activating Requirement Traceability Engine (RTE) extension...");

  // 1. Status Bar Item
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusBarItem.command = "rte.refreshTrace";
  statusBarItem.text = "$(sync~spin) RTE: Connecting...";
  statusBarItem.tooltip = "Requirement Traceability Engine: Initializing local ONNX runtime link";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // Check backend health asynchronously
  void checkBackendStatus();

  // 2. Register CodeLens Provider
  const codeLensProvider = new TraceCodeLensProvider();
  const selector: vscode.DocumentSelector = [
    { language: "python", scheme: "file" },
    { language: "typescript", scheme: "file" },
  ];
  const codeLensDisposable = vscode.languages.registerCodeLensProvider(selector, codeLensProvider);
  context.subscriptions.push(codeLensDisposable);

  // 3. Register Cytoscape WebviewView Provider
  const graphProvider = new TraceGraphPanelProvider(context.extensionUri);
  const graphDisposable = vscode.window.registerWebviewViewProvider(
    TraceGraphPanelProvider.viewType,
    graphProvider
  );
  context.subscriptions.push(graphDisposable);

  // 4. Command: rte.refreshTrace
  const refreshCmd = vscode.commands.registerCommand("rte.refreshTrace", async () => {
    await StoryManager.getInstance().reloadStories();
    codeLensProvider.refresh();
    graphProvider.updateViewport();
    await checkBackendStatus();
    vscode.window.showInformationMessage("Requirement Traceability analysis refreshed.");
  });
  context.subscriptions.push(refreshCmd);

  // 5. Command: rte.showTraceGraph
  const showGraphCmd = vscode.commands.registerCommand("rte.showTraceGraph", async () => {
    await vscode.commands.executeCommand("rte.graphView.focus");
    graphProvider.updateViewport();
  });
  context.subscriptions.push(showGraphCmd);

  // 6. Command: rte.precommitCheck
  const precommitCmd = vscode.commands.registerCommand("rte.precommitCheck", async () => {
    await runPrecommitCheck();
  });
  context.subscriptions.push(precommitCmd);

  // 7. Command: rte.showStoryDetails (invoked on clicking CodeLens)
  const showDetailsCmd = vscode.commands.registerCommand(
    "rte.showStoryDetails",
    async (fn: FunctionTraceStatus) => {
      if (!fn) {
        return;
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

async function checkBackendStatus(): Promise<void> {
  try {
    const health = await TraceApiClient.getInstance().checkHealth();
    if (health) {
      statusBarItem.text = "$(link) RTE: Active (INT8 ONNX)";
      statusBarItem.tooltip = `Connected to local backend (Service: ${health.service}). Latency budget: <= 350ms.`;
    } else {
      statusBarItem.text = "$(alert) RTE: Offline";
      statusBarItem.tooltip = "Local backend is unreachable. Start FastAPI backend with uvicorn.";
    }
  } catch {
    statusBarItem.text = "$(alert) RTE: Offline";
    statusBarItem.tooltip = "Local backend is unreachable. Start FastAPI backend with uvicorn.";
  }
}

export function deactivate(): void {
  if (statusBarItem) {
    statusBarItem.dispose();
  }
}
