/**
 * Sprint Backlog Story Manager for Requirement Traceability Engine.
 *
 * Reads active sprint backlog stories from workspace `.rte/stories.json`
 * or provides default project stories.
 */

import * as vscode from "vscode";
import { StoryRef } from "../api/types";

const DEFAULT_SPRINT_STORIES: StoryRef[] = [
  {
    story_id: "STORY-101",
    user_story: "As an authenticated user, I want to securely log in with JWT tokens and validate sessions.",
    acceptance_criteria: [
      "Validate JWT signature and expiration",
      "Return authenticated user principal with claims",
      "Reject expired or malformed bearer tokens with 401 Unauthorized",
    ],
  },
  {
    story_id: "STORY-102",
    user_story: "As a checkout system, I want accurate state tax calculated based on customer billing location.",
    acceptance_criteria: [
      "Query tax rate for jurisdiction state code",
      "Round calculated tax to two decimal places",
      "Handle tax-exempt customer accounts",
    ],
  },
  {
    story_id: "STORY-103",
    user_story: "As a compliance officer, I want audit log records emitted on sensitive data access.",
    acceptance_criteria: [
      "Log user ID, timestamp, and accessed resource ID",
      "Emit immutable audit event stream",
    ],
  },
];

export class StoryManager {
  private static instance: StoryManager | null = null;
  private cachedStories: StoryRef[] = [];

  private constructor() {
    this.reloadStories();
  }

  public static getInstance(): StoryManager {
    if (!StoryManager.instance) {
      StoryManager.instance = new StoryManager();
    }
    return StoryManager.instance;
  }

  public async reloadStories(): Promise<StoryRef[]> {
    const folders = vscode.workspace.workspaceFolders;
    if (folders && folders.length > 0) {
      const rootUri = folders[0].uri;
      const candidates = [
        vscode.Uri.joinPath(rootUri, ".rte", "stories.json"),
        vscode.Uri.joinPath(rootUri, "stories.json"),
      ];

      for (const uri of candidates) {
        try {
          const raw = await vscode.workspace.fs.readFile(uri);
          const parsed = JSON.parse(new TextDecoder().decode(raw));
          if (Array.isArray(parsed) && parsed.length > 0) {
            this.cachedStories = parsed;
            return this.cachedStories;
          }
        } catch {
          // File not found or unparseable, try next
        }
      }
    }

    this.cachedStories = DEFAULT_SPRINT_STORIES;
    return this.cachedStories;
  }

  public getStories(): StoryRef[] {
    return this.cachedStories.length > 0 ? this.cachedStories : DEFAULT_SPRINT_STORIES;
  }
}
