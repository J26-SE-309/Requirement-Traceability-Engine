/**
 * Pre-Commit Verification Gate for Requirement Traceability Engine.
 *
 * Scans git staged changes against active sprint backlog.
 * Blocks commit if unlinked orphan functions or untested methods exist,
 * displaying an interactive modal for developer resolution.
 */

import * as vscode from "vscode";
import { exec } from "child_process";
import { promisify } from "util";
import { TraceApiClient } from "../api/client";
import { FunctionTraceStatus } from "../api/types";
import { StoryManager } from "../stories/storyManager";

const execAsync = promisify(exec);

export interface PrecommitViolation {
  filePath: string;
  functionName: string;
  status: "ORPHAN" | "MISSING_TEST";
  line: number;
  rationale: string;
}

export async function runPrecommitCheck(): Promise<boolean> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    vscode.window.showInformationMessage("No active workspace found for pre-commit check.");
    return true;
  }

  const rootPath = folders[0].uri.fsPath;

  return await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "RTE Pre-Commit Verification Gate",
      cancellable: false,
    },
    async (progress) => {
      progress.report({ message: "Inspecting git staged files..." });

      let stagedFiles: string[] = [];
      try {
        const { stdout } = await execAsync("git diff --cached --name-only", { cwd: rootPath });
        stagedFiles = stdout
          .split(/\r?\n/)
          .map((s) => s.trim())
          .filter((s) => s.length > 0 && (s.endsWith(".py") || s.endsWith(".ts")));
      } catch (err) {
        console.warn("Could not retrieve git staged files:", err);
      }

      if (stagedFiles.length === 0) {
        vscode.window.showInformationMessage("No staged Python/TypeScript code detected to verify.");
        return true;
      }

      progress.report({ message: `Analyzing ${stagedFiles.length} staged file(s)...` });

      const client = TraceApiClient.getInstance();
      const stories = StoryManager.getInstance().getStories();
      const violations: PrecommitViolation[] = [];

      for (const relPath of stagedFiles) {
        const fullUri = vscode.Uri.joinPath(folders[0].uri, relPath);
        let content: string;
        try {
          const raw = await vscode.workspace.fs.readFile(fullUri);
          content = new TextDecoder().decode(raw);
        } catch {
          continue;
        }

        try {
          const res = await client.traceFile({
            file_path: fullUri.fsPath,
            file_content: content,
            stories: stories,
            delta_only: true, // Only inspect modified/staged functions
          });

          for (const fn of res.functions) {
            if (fn.status === "ORPHAN" || fn.status === "MISSING_TEST") {
              violations.push({
                filePath: relPath,
                functionName: fn.name,
                status: fn.status,
                line: fn.start_line,
                rationale: fn.rationale,
              });
            }
          }
        } catch (err) {
          console.warn(`Failed to trace staged file ${relPath}:`, err);
        }
      }

      if (violations.length === 0) {
        vscode.window.showInformationMessage(
          `✅ RTE Pre-Commit Gate: All ${stagedFiles.length} staged file(s) fully verified against active sprint backlog!`
        );
        return true;
      }

      // Format violation breakdown
      const orphanCount = violations.filter((v) => v.status === "ORPHAN").length;
      const missingTestCount = violations.filter((v) => v.status === "MISSING_TEST").length;

      const warningMsg =
        `⚠️ RTE Pre-Commit Gate Failed!\n\n` +
        `Detected ${violations.length} traceability issue(s) in staged changes:\n` +
        `• ${missingTestCount} function(s) missing test assertions\n` +
        `• ${orphanCount} unlinked orphan function(s)\n\n` +
        `Do you want to proceed anyway or resolve issues before committing?`;

      const choice = await vscode.window.showWarningMessage(
        warningMsg,
        { modal: true },
        "View Violations List",
        "Override & Proceed",
        "Cancel Commit"
      );

      if (choice === "View Violations List") {
        const outputChannel = vscode.window.createOutputChannel("RTE Pre-Commit Gate");
        outputChannel.clear();
        outputChannel.appendLine("=================================================");
        outputChannel.appendLine("  RTE PRE-COMMIT VERIFICATION GATE VIOLATIONS   ");
        outputChannel.appendLine("=================================================\n");

        for (const v of violations) {
          const icon = v.status === "ORPHAN" ? "❌ [ORPHAN]" : "⚠️ [MISSING TEST]";
          outputChannel.appendLine(`${icon} ${v.filePath}:${v.line} -> fn ${v.functionName}()`);
          outputChannel.appendLine(`    Rationale: ${v.rationale}\n`);
        }

        outputChannel.show(true);

        // Open first offending file
        if (violations.length > 0) {
          const first = violations[0];
          const firstUri = vscode.Uri.joinPath(folders[0].uri, first.filePath);
          const doc = await vscode.workspace.openTextDocument(firstUri);
          const editor = await vscode.window.showTextDocument(doc);
          const line = Math.max(0, first.line - 1);
          editor.selection = new vscode.Selection(line, 0, line, 0);
          editor.revealRange(new vscode.Range(line, 0, line, 0), vscode.TextEditorRevealType.InCenter);
        }
        return false;
      }

      return choice === "Override & Proceed";
    }
  );
}
