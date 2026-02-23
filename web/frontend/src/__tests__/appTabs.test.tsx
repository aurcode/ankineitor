import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";

function createMockResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

describe("App tab navigation", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/auth/token")) {
          return createMockResponse({
            token: "test-token",
            user: { id: 1, username: "demo" },
          });
        }
        if (url.includes("/api/pipeline/options")) {
          return createMockResponse({
            profiles: [
              {
                profile_id: "lotm_zh_en_es",
                display_name: "LOTM",
                description: "Profile",
                source_language: "Chinese",
                supports_images: true,
                available_transform_names: ["Audio"],
                unavailable_transform_reasons: {},
                always_included_transform_names: ["Timestamp"],
                default_optional_transform_names: ["Audio"],
                default_ordered_transform_names: ["Timestamp", "Audio"],
              },
            ],
            default_profile_id: "lotm_zh_en_es",
          });
        }
        if (url.includes("/api/anki/presets")) {
          return createMockResponse({
            default: {
              model_id: 1,
              model_name: "Default",
              deck_id: 2,
              note_type: "Vocabulary",
              model_fields: [{ name: "Front" }],
              model_builder: [{ csv_column: "word" }],
              media_fields: [],
              model_templates_yaml: "{}",
              tag_rules_yaml: "[]",
            },
            chinese_pipeline: {
              model_id: 1,
              model_name: "Chinese",
              deck_id: 2,
              note_type: "Vocabulary",
              model_fields: [{ name: "Front" }],
              model_builder: [{ csv_column: "word" }],
              media_fields: [],
              model_templates_yaml: "{}",
              tag_rules_yaml: "[]",
            },
          });
        }
        if (url.includes("/api/flashcards/saved-profiles")) {
          return createMockResponse({ profiles: [] });
        }
        if (url.includes("/api/admin/monitor")) {
          return createMockResponse({
            generated_at: "2026-02-22T00:00:00Z",
            summary: {
              active_pipeline_runs: 0,
              active_background_jobs: 0,
              celery_workers: 0,
              celery_active_tasks: 0,
              celery_reserved_tasks: 0,
              celery_scheduled_tasks: 0,
            },
            pipeline_runs: [],
            background_jobs: [],
            celery: {
              workers: [],
              totals: {
                workers: 0,
                active_tasks: 0,
                reserved_tasks: 0,
                scheduled_tasks: 0,
              },
              error: "",
            },
          });
        }
        if (url.includes("/api/generated/rows")) {
          if (url.match(/\/api\/generated\/rows\/\d+/)) {
            return createMockResponse({
              row: {
                row_id: 1,
                run_id: "run-1",
                run_status: "success",
                profile_id: "lotm_zh_en_es",
                row_index: 0,
                word: "你好",
                created_at: "2026-02-22T00:00:00Z",
                row_data: { word: "你好", meaning_english: "hello", meaning_spanish: "hola" },
                card: {
                  index: 0,
                  total: 1,
                  front: {
                    word: "你好",
                    pronunciation: "",
                    part_of_speech: "",
                    register: "",
                    profile_id: "lotm_zh_en_es",
                    timestamp: "",
                    audio: "",
                  },
                  back: {
                    meaning_english: "hello",
                    meaning_spanish: "hola",
                    details: {},
                    relationships: { synonyms: [], antonyms: [], collocations: [] },
                    sentences: [],
                    image: {
                      picture: "",
                      image_term_type: "",
                      visual_description: "",
                      master_image_prompt: "",
                      image_generation_skip_reason: "",
                      image_render_status: "",
                      image_render_skip_reason: "",
                    },
                  },
                  raw_row: { word: "你好" },
                },
              },
            });
          }
          return createMockResponse({
            count: 1,
            next: null,
            previous: null,
            results: [
              {
                row_id: 1,
                run_id: "run-1",
                run_status: "success",
                profile_id: "lotm_zh_en_es",
                row_index: 0,
                word: "你好",
                created_at: "2026-02-22T00:00:00Z",
                meaning_english: "hello",
                meaning_spanish: "hola",
                picture: "",
                picture_url: "",
                image_render_status: "",
              },
            ],
          });
        }
        return createMockResponse({});
      }),
    );
  });

  it("signs in and switches between migrated workspace tabs", async () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "Sign In" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "demo" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "demo-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign In" }));

    expect(
      await screen.findByRole("heading", { name: "Pipeline" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Anki Deck Generator" }));
    expect(await screen.findByRole("heading", { name: "Anki Deck Generator" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Flashcard Reviewer" }));
    expect(await screen.findByRole("heading", { name: "Flashcard Reviewer" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Generated Library" }));
    expect(await screen.findByRole("heading", { name: "Generated Library" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Word Extractor" }));
    expect(await screen.findByRole("heading", { name: "Word Extractor" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Admin Queue Monitor" }));
    expect(await screen.findByRole("heading", { name: "Admin Queue Monitor" })).toBeInTheDocument();
  });
});
