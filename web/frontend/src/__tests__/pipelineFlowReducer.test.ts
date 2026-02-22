import { describe, expect, it } from "vitest";

import {
  applyPipelineEvent,
  initializeGraphState,
} from "../state/pipelineFlowReducer";

const ordered = ["Timestamp", "LLM (Meanings/Sentences)", "LLM Audio (Sentences)"];

describe("pipelineFlowReducer", () => {
  it("initializes all nodes as queued", () => {
    const state = initializeGraphState(ordered);

    expect(state.nodeStatuses.Timestamp).toBe("queued");
    expect(state.nodeStatuses["LLM (Meanings/Sentences)"]).toBe("queued");
    expect(state.activeNode).toBeNull();
  });

  it("marks node running and then success with duration", () => {
    const initial = initializeGraphState(ordered);

    const running = applyPipelineEvent(
      initial,
      {
        id: 1,
        run_id: "run-1",
        sequence: 1,
        created_at: new Date().toISOString(),
        payload: {
          event: "transform_start",
          transform_name: "LLMTransformation",
        },
      },
      ordered,
    );

    expect(running.nodeStatuses["LLM (Meanings/Sentences)"]).toBe("running");
    expect(running.activeNode).toBe("LLM (Meanings/Sentences)");

    const complete = applyPipelineEvent(
      running,
      {
        id: 2,
        run_id: "run-1",
        sequence: 2,
        created_at: new Date().toISOString(),
        payload: {
          event: "transform_complete",
          transform_name: "LLMTransformation",
          duration_seconds: 2.4,
        },
      },
      ordered,
    );

    expect(complete.nodeStatuses["LLM (Meanings/Sentences)"]).toBe("success");
    expect(complete.nodeDurations["LLM (Meanings/Sentences)"]).toBe(2.4);
    expect(complete.activeNode).toBeNull();
  });

  it("marks node as error when transform_complete includes error", () => {
    const initial = initializeGraphState(ordered);

    const state = applyPipelineEvent(
      initial,
      {
        id: 3,
        run_id: "run-1",
        sequence: 3,
        created_at: new Date().toISOString(),
        payload: {
          event: "transform_complete",
          transform_key: "Timestamp",
          error: "boom",
        },
      },
      ordered,
    );

    expect(state.nodeStatuses.Timestamp).toBe("error");
  });

  it("promotes queued nodes to success when pipeline completes", () => {
    const initial = initializeGraphState(ordered);

    const state = applyPipelineEvent(
      initial,
      {
        id: 4,
        run_id: "run-1",
        sequence: 4,
        created_at: new Date().toISOString(),
        payload: {
          event: "pipeline_complete",
        },
      },
      ordered,
    );

    expect(state.nodeStatuses.Timestamp).toBe("success");
    expect(state.nodeStatuses["LLM Audio (Sentences)"]).toBe("success");
  });
});
