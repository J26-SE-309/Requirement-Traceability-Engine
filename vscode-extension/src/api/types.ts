/**
 * TypeScript contracts mirroring backend/app/schemas.py.
 */

export interface StoryRef {
  story_id: string;
  user_story: string;
  acceptance_criteria?: string[];
}

export interface CoverageRequest {
  project_id?: string | null;
  stories: StoryRef[];
  workspace_path?: string | null;
  target_file?: string | null;
  file_content?: string | null;
  delta_only?: boolean;
}

export interface LinkedArtifact {
  path: string;
  symbol?: string | null;
  kind: "code" | "test";
  source: "tag" | "semantic";
  similarity: number;
  rationale: string;
}

export interface StoryCoverage {
  story_id: string;
  coverage_pct: number;
  linked_artifacts: LinkedArtifact[];
  unlinked_artifact_count: number;
  has_linked_tests: boolean;
  trace_gaps: string[];
  model_version: string;
  analysed_at: string;
}

export interface CoverageResponse {
  items: StoryCoverage[];
}

export type FunctionTraceStatusKind = "VERIFIED" | "MISSING_TEST" | "CANDIDATE" | "ORPHAN";

export interface FunctionTraceStatus {
  name: string;
  qualified_name: string;
  start_line: number;
  end_line: number;
  kind: "code" | "test";
  status: FunctionTraceStatusKind;
  matched_story_id?: string | null;
  user_story?: string | null;
  acceptance_criteria?: string[];
  similarity: number;
  source: "tag" | "semantic" | "none";
  has_test_assertion: boolean;
  linked_test_symbol?: string | null;
  rationale: string;
}

export interface FileTraceRequest {
  file_path: string;
  file_content?: string | null;
  stories?: StoryRef[];
  delta_only?: boolean;
}

export interface FileTraceResponse {
  file_path: string;
  functions: FunctionTraceStatus[];
  model_version: string;
  latency_ms: number;
  analysed_at: string;
}

export interface GraphRequest {
  file_path: string;
  cursor_line: number;
  file_content?: string | null;
  stories?: StoryRef[];
}

export interface CytoscapeElementData {
  id: string;
  label?: string;
  type?: "story" | "function" | "test";
  status?: string;
  kind?: string;
  source?: string;
  target?: string;
  similarity?: number;
  has_assertion?: boolean;
}

export interface CytoscapeElement {
  data: CytoscapeElementData;
}

export interface CytoscapeGraph {
  elements: CytoscapeElement[];
}

export interface GraphResponse {
  graph: CytoscapeGraph;
  active_function?: string | null;
  story_id?: string | null;
  user_story?: string | null;
  ac_statuses?: unknown[];
  analysed_at: string;
}

export interface ScaffoldNamingRequest {
  story_id: string;
  user_story: string;
  acceptance_criteria?: string[];
}

export interface ScaffoldNamingResponse {
  story_id: string;
  module_name: string;
  implementation_file: string;
  test_file: string;
  confidence: number;
  top_candidates: string[];
}
