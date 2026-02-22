import {
  AddCategoryRequest,
  AddCategoryResponse,
  CreateRunRequest,
  PipelineOptionsResponse,
  RunResultsResponse,
  RunSummary,
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
