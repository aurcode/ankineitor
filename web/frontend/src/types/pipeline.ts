export type RunStatus =
  | "queued"
  | "running"
  | "retrying"
  | "paused"
  | "canceled"
  | "success"
  | "error";
export type BackgroundJobStatus = "queued" | "running" | "success" | "error" | "canceled";
export type BackgroundJobType = "anki_deck" | "word_extractor";

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

export interface AuthTokenResponse {
  token: string;
  user: {
    id: number;
    username: string;
  };
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

export interface RunListResponse {
  runs: RunSummary[];
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
  | "transform_queue"
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
  current_word?: string;
  words_left?: number;
  running_words?: string[];
  queued_words?: string[];
  running_count?: number;
  queued_count?: number;
  execution_mode?: string;
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

export interface BackgroundJobSummary {
  id: string;
  job_type: BackgroundJobType;
  status: BackgroundJobStatus;
  progress_ratio: number;
  status_text: string;
  result_payload: Record<string, unknown>;
  csv_output_path: string;
  csv_download_name: string;
  celery_task_id: string;
  csv_url?: string | null;
  error_message: string;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface BackgroundJobEventPayload {
  event: string;
  [key: string]: unknown;
}

export interface BackgroundJobEventEnvelope {
  id: number;
  job_id: string;
  sequence: number;
  created_at: string;
  payload: BackgroundJobEventPayload;
}

export interface BackgroundJobCreateResponse {
  job: BackgroundJobSummary;
  events: BackgroundJobEventEnvelope[];
}

export interface BackgroundJobDetailResponse {
  job: BackgroundJobSummary;
}

export interface BackgroundJobEventsResponse {
  job_id: string;
  events: BackgroundJobEventEnvelope[];
}

export interface BackgroundJobListResponse {
  jobs: BackgroundJobSummary[];
}

export interface AdminPipelineRunSnapshot {
  id: string;
  owner_username: string;
  status: RunStatus;
  profile_id: string;
  source_language: string;
  total_input_words: number;
  celery_task_id: string;
  current_transform: string;
  current_word: string;
  words_left: number;
  running_count: number;
  queued_count: number;
  last_event_type: string;
  last_event_sequence: number;
  last_event_at: string | null;
  created_at: string | null;
  started_at: string | null;
  updated_at: string | null;
}

export interface AdminBackgroundJobSnapshot {
  id: string;
  owner_username: string;
  job_type: BackgroundJobType;
  status: BackgroundJobStatus;
  progress_ratio: number;
  status_text: string;
  celery_task_id: string;
  created_at: string | null;
  started_at: string | null;
  updated_at: string | null;
}

export interface CeleryTaskSnapshot {
  id: string;
  name: string;
  args: string;
  kwargs: string;
  eta: string | null | "";
}

export interface CeleryWorkerSnapshot {
  worker_name: string;
  queues: string[];
  max_concurrency: number;
  active_count: number;
  reserved_count: number;
  scheduled_count: number;
  active_tasks: CeleryTaskSnapshot[];
  reserved_tasks: CeleryTaskSnapshot[];
  scheduled_tasks: CeleryTaskSnapshot[];
}

export interface AdminQueueMonitorResponse {
  generated_at: string;
  summary: {
    active_pipeline_runs: number;
    active_background_jobs: number;
    celery_workers: number;
    celery_active_tasks: number;
    celery_reserved_tasks: number;
    celery_scheduled_tasks: number;
  };
  pipeline_runs: AdminPipelineRunSnapshot[];
  background_jobs: AdminBackgroundJobSnapshot[];
  celery: {
    workers: CeleryWorkerSnapshot[];
    totals: {
      workers: number;
      active_tasks: number;
      reserved_tasks: number;
      scheduled_tasks: number;
    };
    error: string;
  };
}

export type JobWebsocketMessage =
  | { type: "job_snapshot"; job: BackgroundJobSummary }
  | { type: "job_event"; event: BackgroundJobEventEnvelope };

export interface AnkiField {
  name: string;
}

export interface AnkiModelBuilderEntry {
  csv_column: string;
}

export interface AnkiMediaField {
  column_name: string;
  media_type: string;
}

export interface AnkiConfigPayload {
  model_id: number;
  model_name: string;
  deck_id: number;
  note_type: string;
  model_fields: AnkiField[];
  model_builder: AnkiModelBuilderEntry[];
  media_fields: AnkiMediaField[];
  model_templates_yaml: string | Record<string, unknown>;
  tag_rules_yaml: string | unknown[];
}

export interface AnkiPresetsResponse {
  default: AnkiConfigPayload;
  chinese_pipeline: AnkiConfigPayload;
}

export interface AnkiJobResultPayload {
  artifact_id: string;
  deck_name: string;
  source_csv_name: string;
  file_size_bytes: number;
  output_path: string;
  created_at: string;
  download_url?: string;
}

export interface FlashcardSavedFile {
  file_name: string;
  file_path: string;
  modified_at: string | null;
  size_bytes: number;
}

export interface FlashcardSavedProfilesResponse {
  profiles: string[];
}

export interface FlashcardSavedFilesResponse {
  profile_id: string;
  files: FlashcardSavedFile[];
}

export interface FlashcardDatasetSummary {
  dataset_id: string;
  source_type: "saved" | "upload";
  source_label: string;
  total_cards: number;
  columns: string[];
  available_profiles: string[];
  created_at: string;
}

export interface FlashcardFrontView {
  word: string;
  pronunciation: string;
  part_of_speech: string;
  register: string;
  profile_id: string;
  timestamp: string;
  audio: string;
}

export interface FlashcardSentenceView {
  index: string;
  sentence: string;
  tts_clean: string;
  cloze: string;
  pronunciation: string;
  translation_english: string;
  translation_spanish: string;
  audio: string;
}

export interface FlashcardBackView {
  meaning_english: string;
  meaning_spanish: string;
  details: Record<string, string>;
  relationships: {
    synonyms: string[];
    antonyms: string[];
    collocations: string[];
  };
  sentences: FlashcardSentenceView[];
  image: {
    picture: string;
    picture_url?: string;
    image_term_type: string;
    visual_description: string;
    master_image_prompt: string;
    image_generation_skip_reason: string;
    image_render_status: string;
    image_render_skip_reason: string;
  };
}

export interface FlashcardCardResponse {
  index: number;
  total: number;
  front: FlashcardFrontView;
  back: FlashcardBackView;
  raw_row: Record<string, string | number | boolean | null>;
}

export interface FlashcardCardMutationResponse {
  dataset: FlashcardDatasetSummary;
  card: FlashcardCardResponse;
  rerun_mode?: "full" | "image";
  applied_transforms?: string[];
}


export type GeneratedRowRerunProcess =
  | "full"
  | "meaning_sentences"
  | "audio_word"
  | "audio_sentences"
  | "image_prompt"
  | "image_renderer"
  | "image";

export interface GeneratedRowSummary {
  row_id: number;
  run_id: string;
  run_status: RunStatus;
  profile_id: string;
  row_index: number;
  word: string;
  created_at: string;
  meaning_english: string;
  meaning_spanish: string;
  picture: string;
  picture_url: string;
  image_render_status: string;
}

export interface GeneratedRowsResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: GeneratedRowSummary[];
}

export interface GeneratedRowDetail {
  row_id: number;
  run_id: string;
  run_status: RunStatus;
  profile_id: string;
  row_index: number;
  word: string;
  created_at: string;
  row_data: Record<string, string | number | boolean | null>;
  card: FlashcardCardResponse;
}

export interface GeneratedRowDetailResponse {
  row: GeneratedRowDetail;
}

export interface GeneratedRowMutationResponse {
  row: GeneratedRowDetail;
  rerun_process?: GeneratedRowRerunProcess;
  applied_transforms?: string[];
}

export interface WordExtractorSummary {
  initial_count: number;
  filtered_count: number;
  removed_count: number;
  final_count: number;
  min_frequency: number;
  applied_hsk_levels: string[];
}

export interface WordExtractorResponse {
  initial_words: Array<Record<string, string | number | null>>;
  filtered_words: Array<Record<string, string | number | null>>;
  removed_words: Array<Record<string, string | number | null>>;
  final_words: Array<Record<string, string | number | null>>;
  copyable_word_list: string;
  extraction_errors: Record<string, string>;
  summary: WordExtractorSummary;
}
