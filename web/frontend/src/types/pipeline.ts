export type RunStatus = "queued" | "running" | "retrying" | "success" | "error";

export type NodeExecutionStatus = "idle" | "queued" | "running" | "success" | "error";

export interface ProfileOptions {
  profile_id: string;
  display_name: string;
  description: string;
  source_language: string;
  supports_images: boolean;
  available_transform_names: string[];
  unavailable_transform_reasons: Record<string, string>;
  always_included_transform_names: string[];
  default_optional_transform_names: string[];
  default_ordered_transform_names: string[];
}

export interface PipelineOptionsResponse {
  profiles: ProfileOptions[];
  default_profile_id: string;
}

export interface CreateRunRequest {
  profile_id: string;
  transform_names: string[];
  words: string[];
}

export interface RunSummary {
  id: string;
  status: RunStatus;
  profile_id: string;
  source_language: string;
  selected_transform_names: string[];
  ordered_transform_names: string[];
  total_input_words: number;
  error_message: string;
  csv_output_path: string;
  csv_download_name: string;
  total_duration_seconds: number | null;
  counters: Record<string, number>;
  slowest_steps: Array<{ stage: string; step: string; seconds: number }>;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  event_count: number;
}

export interface ResultRow {
  row_index: number;
  word: string;
  row_data: Record<string, string | number | boolean | null>;
}

export interface RunResultsResponse {
  run_id: string;
  status: RunStatus;
  columns: string[];
  csv_url: string | null;
  count: number;
  next: string | null;
  previous: string | null;
  results: ResultRow[];
}

export interface AddCategoryRequest {
  category: string;
}

export interface AddCategoryResponse {
  run: RunSummary;
  category: string;
  updated_rows: number;
}

export type PipelineEventType =
  | "pipeline_start"
  | "cache_checked"
  | "transform_start"
  | "transform_complete"
  | "pipeline_complete"
  | "pipeline_error"
  | "category_applied"
  | string;

export interface PipelineEventPayload {
  event: PipelineEventType;
  stage?: string;
  transform_name?: string;
  transform_key?: string;
  progress_ratio?: number;
  status_text?: string;
  error?: string;
  duration_seconds?: number;
  total_duration_seconds?: number;
  [key: string]: unknown;
}

export interface PipelineEventEnvelope {
  id: number;
  run_id: string;
  sequence: number;
  created_at: string;
  payload: PipelineEventPayload;
}

export interface PipelineWebsocketMessage {
  type: "pipeline_event";
  event: PipelineEventEnvelope;
}
