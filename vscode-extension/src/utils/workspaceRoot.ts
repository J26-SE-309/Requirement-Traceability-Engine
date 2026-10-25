/**
 * Dynamic Project and Extension Storage Resolution Utility.
 *
 * Separates the user's active code workspace from the extension's internal .rte storage.
 */

import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";

let globalExtensionContext: vscode.ExtensionContext | undefined;

/**
 * Call this once in extension.ts activate(context) to capture the extension's runtime location.
 */
export function setExtensionContext(context: vscode.ExtensionContext): void {
  globalExtensionContext = context;
}

/**
 * Resolves the user's active workspace (where their production Python code and tests live).
 */
export function resolveWorkspaceRootUri(): vscode.Uri {
  // 1. If an editor is open, use its containing workspace folder
  const activeEditor = vscode.window.activeTextEditor;
  if (activeEditor) {
    const activeFolder = vscode.workspace.getWorkspaceFolder(activeEditor.document.uri);
    if (activeFolder) {
      return activeFolder.uri;
    }
  }

  // 2. Otherwise default to the first open folder
  const workspaceFolders = vscode.workspace.workspaceFolders;
  if (workspaceFolders && workspaceFolders.length > 0) {
    return workspaceFolders[0].uri;
  }

  // Fallback to process CWD if opened in standalone mode
  return vscode.Uri.file(process.cwd());
}

/**
 * Resolves the project root URI.
 * Alias for resolveWorkspaceRootUri() to maintain backwards compatibility.
 */
export function resolveProjectRootUri(): vscode.Uri {
  return resolveWorkspaceRootUri();
}

/**
 * Resolves the location of .rte and stories.json.
 * 
 * Priority:
 * 1. User's workspace has its own .rte/ (if they want custom stories)
 * 2. Extension's own internal .rte directory (via ExtensionContext)
 * 3. Settings override ("rte.storiesPath")
 */
export function resolveRteStorageUri(): vscode.Uri {
  // 1. Check user settings override in settings.json
  const config = vscode.workspace.getConfiguration("rte");
  const customStoriesPath = config.get<string>("storiesPath");
  if (customStoriesPath && fs.existsSync(customStoriesPath)) {
    return vscode.Uri.file(customStoriesPath);
  }

  // 2. Check if the active workspace contains an override .rte/ folder
  const workspaceUri = resolveWorkspaceRootUri();
  const workspaceRte = path.join(workspaceUri.fsPath, ".rte");
  if (fs.existsSync(workspaceRte)) {
    return vscode.Uri.file(workspaceRte);
  }

  // 3. Check canonical Requirement-Traceability-Engine/.rte path requested by user
  const canonicalRte = "C:/Users/DINUWA/Desktop/Reserach resources/Requirement-Traceability-Engine/.rte";
  if (fs.existsSync(canonicalRte)) {
    return vscode.Uri.file(canonicalRte);
  }

  // 4. Resolve dynamically from the Extension's parent directory
  if (globalExtensionContext) {
    const extDir = globalExtensionContext.extensionUri.fsPath;
    const parentRte = path.join(path.dirname(extDir), ".rte");
    if (fs.existsSync(parentRte)) {
      return vscode.Uri.file(parentRte);
    }
    const directRte = path.join(extDir, ".rte");
    if (fs.existsSync(directRte)) {
      return vscode.Uri.file(directRte);
    }
    return globalExtensionContext.extensionUri;
  }

  // Safe fallback to workspace
  return workspaceUri;
}