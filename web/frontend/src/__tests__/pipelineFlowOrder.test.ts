import { describe, expect, it } from "vitest";

import {
  resolveDependencyEdges,
  resolveGraphLayout,
  resolveGraphOrder,
  resolveRenderableEdges,
} from "../components/PipelineFlow";

describe("PipelineFlow dependency ordering", () => {
  it("orders image prompt before image renderer", () => {
    const input = [
      "Timestamp",
      "LLM (Meanings/Sentences)",
      "LLM Image Renderer (Master Prompt)",
      "LLM Image Prompt (Visual Translator)",
    ];

    const ordered = resolveGraphOrder(input);
    expect(
      ordered.indexOf("LLM Image Prompt (Visual Translator)"),
    ).toBeLessThan(ordered.indexOf("LLM Image Renderer (Master Prompt)"));
  });

  it("builds prompt-to-renderer dependency edge", () => {
    const edges = resolveDependencyEdges([
      "LLM Image Renderer (Master Prompt)",
      "LLM Image Prompt (Visual Translator)",
    ]);

    expect(edges).toContainEqual({
      source: "LLM Image Prompt (Visual Translator)",
      target: "LLM Image Renderer (Master Prompt)",
    });
  });

  it("places dependent nodes vertically and parallel nodes horizontally", () => {
    const layout = resolveGraphLayout([
      "Timestamp",
      "Audio",
      "LLM (Meanings/Sentences)",
      "LLM Image Prompt (Visual Translator)",
      "LLM Audio (Sentences)",
      "LLM Image Renderer (Master Prompt)",
    ]);

    expect(layout["LLM Audio (Sentences)"].y).toBeGreaterThan(
      layout["LLM (Meanings/Sentences)"].y,
    );
    expect(layout["LLM Image Renderer (Master Prompt)"].y).toBeGreaterThan(
      layout["LLM Image Prompt (Visual Translator)"].y,
    );
    expect(layout.Timestamp.y).toBe(layout["Audio"].y);
    expect(layout.Timestamp.x).not.toBe(layout["Audio"].x);
  });

  it("falls back to vertical chain layout when no known dependencies exist", () => {
    const edges = resolveRenderableEdges(["A", "B", "C"]);
    expect(edges).toEqual([
      { source: "A", target: "B" },
      { source: "B", target: "C" },
    ]);

    const layout = resolveGraphLayout(["A", "B", "C"]);
    expect(layout.B.y).toBeGreaterThan(layout.A.y);
    expect(layout.C.y).toBeGreaterThan(layout.B.y);
  });
});
