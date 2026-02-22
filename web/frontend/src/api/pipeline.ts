import {
  AddCategoryRequest,
  AddCategoryResponse,
  AnkiConfigPayload,
  AnkiPresetsResponse,
  CreateRunRequest,
  FlashcardCardResponse,
  FlashcardDatasetSummary,
  FlashcardSavedFilesResponse,
  FlashcardSavedProfilesResponse,
  GenerateAnkiDeckResponse,
  PipelineOptionsResponse,
  RunResultsResponse,
  RunSummary,
  WordExtractorResponse,
} from "../types/pipeline";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });

  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    let message = `Request failed (${response.status})`;
    if (contentType.includes("application/json")) {
      const payload = await response.json();
      message = String(payload.detail || payload.error || message);
    } else {
      const text = await response.text();
      if (text) {
        message = text;
      }
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

async function requestFormJson<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    let message = `Request failed (${response.status})`;
    if (contentType.includes("application/json")) {
      const payload = await response.json();
      message = String(payload.detail || payload.error || message);
    } else {
      const text = await response.text();
      if (text) {
        message = text;
      }
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
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
}): Promise<GenerateAnkiDeckResponse> {
  const formData = new FormData();
  formData.append("csv_file", params.csvFile);
  formData.append("deck_name", params.deckName);
  formData.append("config", JSON.stringify(params.config));
  return requestFormJson<GenerateAnkiDeckResponse>("/api/anki/decks/generate", formData);
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
}): Promise<WordExtractorResponse> {
  const formData = new FormData();
  for (const file of params.files) {
    formData.append("files", file);
  }
  formData.append("text_input", params.textInput);
  for (const level of params.selectedHskLevels) {
    formData.append("selected_hsk_levels", level);
  }
  formData.append("min_frequency", String(params.minFrequency));

  return requestFormJson<WordExtractorResponse>("/api/word-extractor/analyze", formData);
}
