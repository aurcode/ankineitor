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
      await screen.findByRole("heading", { name: "Ankineitor Pipeline Workspace" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Anki Deck Generator" }));
    expect(await screen.findByRole("heading", { name: "Anki Deck Generator" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Flashcard Reviewer" }));
    expect(await screen.findByRole("heading", { name: "Flashcard Reviewer" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Word Extractor" }));
    expect(await screen.findByRole("heading", { name: "Word Extractor" })).toBeInTheDocument();
  });
});
