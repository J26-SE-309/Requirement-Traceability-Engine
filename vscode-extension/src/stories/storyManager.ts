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
    user_story: "As a registered customer, I want to authenticate with JWT tokens so that I can securely access protected platform resources.",
    acceptance_criteria: [
      "Validate user authentication token signature and expiration",
      "Return authenticated user principal with claims",
      "Reject expired or malformed bearer tokens with 401 Unauthorized",
    ],
  },
  {
    story_id: "STORY-102",
    user_story: "As a checkout billing system, I want state sales tax computed accurately based on customer jurisdiction.",
    acceptance_criteria: [
      "Query tax rate for jurisdiction state code and calculate tax",
      "Round calculated tax to two decimal places",
      "Support California, New York, and Texas state rate lookups",
    ],
  },
  {
    story_id: "STORY-103",
    user_story: "As a merchant, I want credit card payments captured through Stripe and recorded to the transaction ledger.",
    acceptance_criteria: [
      "Process card transaction charge through payment gateway",
      "Validate charge currency and minimum order amount",
      "Issue partial or full refund against captured charge ID",
    ],
  },
  {
    story_id: "STORY-104",
    user_story: "As an inventory manager, I want warehouse stock reserved atomically when items are added to a checkout cart.",
    acceptance_criteria: [
      "Query available warehouse SKU quantity from database",
      "Atomically decrement stock count to avoid overselling",
      "Raise OutOfStockError if requested quantity exceeds inventory",
    ],
  },
  {
    story_id: "STORY-105",
    user_story: "As a compliance officer, I want sensitive account and payment operations recorded to an immutable audit trail.",
    acceptance_criteria: [
      "Capture actor user ID, client IP address, action name, and timestamp",
      "Serialize audit record to JSON and write to compliance stream",
    ],
  },
];

export class StoryManager {
  private static instance: StoryManager | null = null;
  private cachedStories: StoryRef[] = [];

  private constructor() {
    void this.reloadStories();
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
          // File not found or unparseable, try next candidate
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