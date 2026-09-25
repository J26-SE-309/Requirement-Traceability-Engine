import * as vscode from "vscode";

/**
 * Entry point of the Synapse Traceability extension.
 *
 * The heavy work (parsing, embeddings, linking) runs in the local Python engine
 * (../backend and ../ml-engine). The extension observes the workspace and shows
 * results inside VS Code.
 */
export function activate(context: vscode.ExtensionContext): void {
  const showStatus = vscode.commands.registerCommand("synapseTraceability.showStatus", async () => {
    const engineUrl = vscode.workspace
      .getConfiguration("synapseTraceability")
      .get<string>("engineUrl", "http://localhost:8003");
    try {
      const response = await fetch(`${engineUrl}/health`);
      const health = (await response.json()) as { version: string };
      void vscode.window.showInformationMessage(`Traceability engine ${health.version} is running at ${engineUrl}.`);
    } catch {
      void vscode.window.showWarningMessage(
        `Traceability engine is not reachable at ${engineUrl}. Start it with uvicorn or docker compose.`,
      );
    }
  });
  context.subscriptions.push(showStatus);
}

export function deactivate(): void {}
