import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  generateAnkiDeck,
  getPipelineOptions,
  saveAuthSession,
} from "../api/pipeline";

function createMockResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

describe("API token auth", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("adds Authorization header to JSON requests", async () => {
    saveAuthSession({
      token: "json-token",
      user: { id: 1, username: "demo" },
    });
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () => createMockResponse({ profiles: [], default_profile_id: "default" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await getPipelineOptions();

    const init = (fetchMock.mock.calls[0]?.[1] || {}) as RequestInit;
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Token json-token");
  });

  it("adds Authorization header to multipart requests", async () => {
    saveAuthSession({
      token: "multipart-token",
      user: { id: 1, username: "demo" },
    });
    const fetchMock = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () =>
        createMockResponse({
          job: {
            id: "job-1",
            job_type: "anki_deck",
            status: "queued",
            progress_ratio: 0,
            status_text: "Queued",
            result_payload: {},
            csv_output_path: "",
            csv_download_name: "",
            celery_task_id: "",
            error_message: "",
            created_at: null,
            started_at: null,
            completed_at: null,
          },
          events: [],
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await generateAnkiDeck({
      csvFile: new File(["word,translation\nhello,hola"], "cards.csv", { type: "text/csv" }),
      deckName: "My Deck",
      config: {
        model_id: 1,
        model_name: "M",
        deck_id: 2,
        note_type: "Vocabulary",
        model_fields: [{ name: "Front" }],
        model_builder: [{ csv_column: "word" }],
        media_fields: [],
        model_templates_yaml: "{}",
        tag_rules_yaml: [],
      },
    });

    const init = (fetchMock.mock.calls[0]?.[1] || {}) as RequestInit;
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Token multipart-token");
  });
});
