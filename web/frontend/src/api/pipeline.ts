import {
  AddCategoryRequest,
  AddCategoryResponse,
  AnkiConfigPayload,
  AnkiPresetsResponse,
  AuthTokenResponse,
  BackgroundJobCreateResponse,
  BackgroundJobDetailResponse,
  BackgroundJobEventsResponse,
  BackgroundJobListResponse,
  CreateRunRequest,
  FlashcardCardResponse,
  FlashcardDatasetSummary,
  FlashcardSavedFilesResponse,
  FlashcardSavedProfilesResponse,
  PipelineOptionsResponse,
  RunResultsResponse,
  RunSummary,
} from "../types/pipeline";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const AUTH_TOKEN_STORAGE_KEY = "ankineitor_web_auth_token";
const AUTH_USERNAME_STORAGE_KEY = "ankineitor_web_auth_username";

function resolveApiUrl(pathOrUrl: string): string {
  if (pathOrUrl.startsWith("http://") || pathOrUrl.startsWith("https://")) {
    return pathOrUrl;
  }
  return `${API_BASE}${pathOrUrl}`;
}

function getErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") {
    return fallback;
  }
  const record = payload as Record<string, unknown>;
  const detail = record.detail;
  const error = record.error;
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (typeof error === "string" && error.trim()) {
    return error;
  }
  return fallback;
}

async function readErrorMessage(response: Response): Promise<string> {
  const fallback = `Request failed (${response.status})`;
  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    try {
      const payload = await response.json();
      return getErrorMessage(payload, fallback);
    } catch {
      return fallback;
    }
  }

  const text = await response.text();
  if (text && text.trim()) {
    return text;
  }
  return fallback;
}

function getAuthHeaders(baseHeaders?: HeadersInit): Headers {
  const headers = new Headers(baseHeaders || {});
  const token = getAuthToken();
  if (token) {
    headers.set("Authorization", `Token ${token}`);
  }
  return headers;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = getAuthHeaders(init?.headers);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(resolveApiUrl(path), {
    ...init,
    headers,
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return (await response.json()) as T;
}

async function requestFormJson<T>(path: string, formData: FormData): Promise<T> {
  const headers = getAuthHeaders();
  const response = await fetch(resolveApiUrl(path), {
    method: "POST",
    headers,
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return (await response.json()) as T;
}

function parseFilenameFromDisposition(contentDisposition: string | null, fallback: string): string {
  if (!contentDisposition) {
    return fallback;
  }
  const match = contentDisposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
  if (!match?.[1]) {
    return fallback;
  }
  try {
    return decodeURIComponent(match[1].trim());
  } catch {
    return match[1].trim();
  }
}

export function getApiBaseUrl(): string {
  return API_BASE;
}

export function getAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
}

export function getAuthUsername(): string | null {
  return localStorage.getItem(AUTH_USERNAME_STORAGE_KEY);
}

export function saveAuthSession(payload: AuthTokenResponse): void {
  localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, payload.token);
  localStorage.setItem(AUTH_USERNAME_STORAGE_KEY, payload.user.username);
}

export function clearAuthSession(): void {
  localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  localStorage.removeItem(AUTH_USERNAME_STORAGE_KEY);
}

export function createAuthToken(params: { username: string; password: string }): Promise<AuthTokenResponse> {
  return requestJson<AuthTokenResponse>("/api/auth/token", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function downloadAuthenticatedFile(params: {
  url: string;
  fallbackFileName: string;
}): Promise<void> {
  const response = await fetch(resolveApiUrl(params.url), {
    method: "GET",
    headers: getAuthHeaders(),
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = parseFilenameFromDisposition(
    response.headers.get("content-disposition"),
    params.fallbackFileName,
  );
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

export function getPipelineOptions(): Promise<PipelineOptionsResponse> {
  return requestJson<PipelineOptionsResponse>("/api/pipeline/options");
}

export function createPipelineRun(payload: CreateRunRequest): Promise<RunSummary> {
  return requestJson<RunSummary>("/api/pipeline/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getPipelineRun(runId: string): Promise<RunSummary> {
  return requestJson<RunSummary>(`/api/pipeline/runs/${runId}`);
}

export function getPipelineRunResults(
  runId: string,
  params: { page?: number; pageSize?: number; search?: string } = {},
): Promise<RunResultsResponse> {
  const query = new URLSearchParams();
  if (params.page) {
    query.set("page", String(params.page));
  }
  if (params.pageSize) {
    query.set("page_size", String(params.pageSize));
  }
  if (params.search) {
    query.set("search", params.search);
  }

  const queryString = query.toString();
  const suffix = queryString ? `?${queryString}` : "";
  return requestJson<RunResultsResponse>(`/api/pipeline/runs/${runId}/results${suffix}`);
}

export function addCategoryToRun(
  runId: string,
  payload: AddCategoryRequest,
): Promise<AddCategoryResponse> {
  return requestJson<AddCategoryResponse>(`/api/pipeline/runs/${runId}/add-category`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAnkiPresets(): Promise<AnkiPresetsResponse> {
  return requestJson<AnkiPresetsResponse>("/api/anki/presets");
}

export function generateAnkiDeck(params: {
  csvFile: File;
  deckName: string;
  config: AnkiConfigPayload;
}): Promise<BackgroundJobCreateResponse> {
  const formData = new FormData();
  formData.append("csv_file", params.csvFile);
  formData.append("deck_name", params.deckName);
  formData.append("config", JSON.stringify(params.config));
  return requestFormJson<BackgroundJobCreateResponse>("/api/anki/decks/generate", formData);
}

export function getBackgroundJob(jobId: string): Promise<BackgroundJobDetailResponse> {
  return requestJson<BackgroundJobDetailResponse>(`/api/jobs/${jobId}`);
}

export function listBackgroundJobs(params?: {
  jobType?: "anki_deck" | "word_extractor";
  limit?: number;
}): Promise<BackgroundJobListResponse> {
  const query = new URLSearchParams();
  if (params?.jobType) {
    query.set("job_type", params.jobType);
  }
  if (params?.limit) {
    query.set("limit", String(params.limit));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return requestJson<BackgroundJobListResponse>(`/api/jobs${suffix}`);
}

export function getBackgroundJobEvents(jobId: string): Promise<BackgroundJobEventsResponse> {
  return requestJson<BackgroundJobEventsResponse>(`/api/jobs/${jobId}/events`);
}

export function retryBackgroundJob(jobId: string): Promise<BackgroundJobCreateResponse> {
  return requestJson<BackgroundJobCreateResponse>(`/api/jobs/${jobId}/retry`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function cancelBackgroundJob(jobId: string): Promise<BackgroundJobDetailResponse> {
  return requestJson<BackgroundJobDetailResponse>(`/api/jobs/${jobId}/cancel`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function getFlashcardSavedProfiles(): Promise<FlashcardSavedProfilesResponse> {
  return requestJson<FlashcardSavedProfilesResponse>("/api/flashcards/saved-profiles");
}

export function getFlashcardSavedFiles(profileId: string): Promise<FlashcardSavedFilesResponse> {
  const query = new URLSearchParams({ profile_id: profileId });
  return requestJson<FlashcardSavedFilesResponse>(`/api/flashcards/saved-files?${query.toString()}`);
}

export function createFlashcardDatasetFromSaved(params: {
  profileId: string;
  fileName?: string;
}): Promise<FlashcardDatasetSummary> {
  return requestJson<FlashcardDatasetSummary>("/api/flashcards/datasets/from-saved", {
    method: "POST",
    body: JSON.stringify({
      profile_id: params.profileId,
      file_name: params.fileName || "",
    }),
  });
}

export function createFlashcardDatasetFromUpload(csvFile: File): Promise<FlashcardDatasetSummary> {
  const formData = new FormData();
  formData.append("csv_file", csvFile);
  return requestFormJson<FlashcardDatasetSummary>("/api/flashcards/datasets/upload", formData);
}

export function getFlashcardDatasetSummary(datasetId: string): Promise<FlashcardDatasetSummary> {
  return requestJson<FlashcardDatasetSummary>(`/api/flashcards/datasets/${datasetId}`);
}

export function getFlashcardCard(params: {
  datasetId: string;
  index: number;
  profileFilter?: string;
}): Promise<FlashcardCardResponse> {
  const query = new URLSearchParams({ index: String(params.index) });
  if (params.profileFilter) {
    query.set("profile_filter", params.profileFilter);
  }
  return requestJson<FlashcardCardResponse>(
    `/api/flashcards/datasets/${params.datasetId}/card?${query.toString()}`,
  );
}

export function analyzeWordExtractor(params: {
  files: File[];
  textInput: string;
  selectedHskLevels: string[];
  minFrequency: number;
}): Promise<BackgroundJobCreateResponse> {
  const formData = new FormData();
  for (const file of params.files) {
    formData.append("files", file);
  }
  formData.append("text_input", params.textInput);
  for (const level of params.selectedHskLevels) {
    formData.append("selected_hsk_levels", level);
  }
  formData.append("min_frequency", String(params.minFrequency));

  return requestFormJson<BackgroundJobCreateResponse>("/api/word-extractor/analyze", formData);
}
