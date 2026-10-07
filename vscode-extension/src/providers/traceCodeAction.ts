/**
 * Quick-Fix CodeAction Provider for Requirement Traceability Engine.
 *
 * Provides one-click lightbulb actions (Ctrl + .) to insert '# Trace: STORY-ID'
 * directly above unlinked or candidate function definitions.
 */

import * as vscode from "vscode";
import { StoryManager } from "../stories/storyManager";
import { TraceCodeLensProvider } from "./traceCodeLens";

export class TraceCodeActionProvider implements vscode.CodeActionProvider {
  public static readonly providedCodeActionKinds = [vscode.CodeActionKind.QuickFix];

  constructor(private readonly codeLensProvider: TraceCodeLensProvider) {}

  public provideCodeActions(
    document: vscode.TextDocument,
    range: vscode.Range | vscode.Selection
  ): vscode.CodeAction[] {
    const uriKey = document.uri.toString();
    const cursorLine = range.start.line;

    // 1. Check if the cursor sits within a recognized AST function range
    const fn = this.codeLensProvider.getFunctionAtLine(uriKey, cursorLine);
    if (!fn) {
      return [];
    }

    // 2. If the function is already explicitly tagged, don't show the fix
    if (fn.source === "tag") {
      return [];
    }

    const actions: vscode.CodeAction[] = [];
    const insertLine = Math.max(0, fn.start_line - 1);
    const insertPosition = new vscode.Position(insertLine, 0);

    // 3. Primary action: Best semantic match recommended by the ONNX model
    if (fn.matched_story_id && fn.similarity > 0) {
      const simPct = Math.round(fn.similarity * 100);
      const bestAction = new vscode.CodeAction(
        `🔗 Link to ${fn.matched_story_id} (${simPct}% AI match)`,
        vscode.CodeActionKind.QuickFix
      );
      bestAction.isPreferred = true;
      bestAction.edit = new vscode.WorkspaceEdit();
      bestAction.edit.insert(document.uri, insertPosition, `# Trace: ${fn.matched_story_id}\n`);
      actions.push(bestAction);
    }

    // 4. Secondary actions: Alternative sprint backlog stories
    const stories = StoryManager.getInstance().getStories();
    for (const story of stories) {
      if (story.story_id === fn.matched_story_id) {
        continue;
      }

      const truncatedStory =
        story.user_story.length > 45 ? `${story.user_story.slice(0, 45)}...` : story.user_story;

      const altAction = new vscode.CodeAction(
        `🏷️ Link to ${story.story_id} (${truncatedStory})`,
        vscode.CodeActionKind.QuickFix
      );
      altAction.edit = new vscode.WorkspaceEdit();
      altAction.edit.insert(document.uri, insertPosition, `# Trace: ${story.story_id}\n`);
      actions.push(altAction);
    }

    return actions;
  }
}