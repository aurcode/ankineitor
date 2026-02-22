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
    expect(state.nodeRuntime.Timestamp.currentWord).toBe("");
    expect(state.nodeRuntime.Timestamp.wordsLeft).toBeNull();
    expect(state.nodeRuntime.Timestamp.runningWords).toEqual([]);
    expect(state.nodeRuntime.Timestamp.queuedWords).toEqual([]);
    expect(state.activeNodes).toEqual([]);
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
          current_word: "苹果",
          words_left: 4,
          running_words: ["苹果"],
          queued_words: ["你好", "谢谢", "再见", "学习"],
        },
      },
      ordered,
    );

    expect(running.nodeStatuses["LLM (Meanings/Sentences)"]).toBe("running");
    expect(running.activeNode).toBe("LLM (Meanings/Sentences)");
    expect(running.activeNodes).toEqual(["LLM (Meanings/Sentences)"]);
    expect(running.nodeRuntime["LLM (Meanings/Sentences)"].currentWord).toBe("苹果");
    expect(running.nodeRuntime["LLM (Meanings/Sentences)"].wordsLeft).toBe(4);
    expect(running.nodeRuntime["LLM (Meanings/Sentences)"].runningWords).toEqual(["苹果"]);
    expect(running.nodeRuntime["LLM (Meanings/Sentences)"].queuedWords).toEqual([
      "你好",
      "谢谢",
      "再见",
      "学习",
    ]);

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
          current_word: "苹果",
          words_left: 3,
          running_words: [],
          queued_words: ["你好", "谢谢", "再见"],
        },
      },
      ordered,
    );

    expect(complete.nodeStatuses["LLM (Meanings/Sentences)"]).toBe("queued");
    expect(complete.nodeDurations["LLM (Meanings/Sentences)"]).toBe(2.4);
    expect(complete.nodeRuntime["LLM (Meanings/Sentences)"].currentWord).toBe("苹果");
    expect(complete.nodeRuntime["LLM (Meanings/Sentences)"].wordsLeft).toBe(3);
    expect(complete.nodeRuntime["LLM (Meanings/Sentences)"].runningWords).toEqual([]);
    expect(complete.nodeRuntime["LLM (Meanings/Sentences)"].queuedWords).toEqual([
      "你好",
      "谢谢",
      "再见",
    ]);
    expect(complete.activeNodes).toEqual([]);
    expect(complete.activeNode).toBeNull();
  });

  it("stores queued words from transform_queue events", () => {
    const initial = initializeGraphState(ordered);

    const queued = applyPipelineEvent(
      initial,
      {
        id: 20,
        run_id: "run-queue",
        sequence: 1,
        created_at: new Date().toISOString(),
        payload: {
          event: "transform_queue",
          transform_name: "LLMAudioTransformation",
          queued_words: ["你好", "谢谢"],
          words_left: 2,
        },
      },
      ordered,
    );

    expect(queued.nodeStatuses["LLM Audio (Sentences)"]).toBe("queued");
    expect(queued.nodeRuntime["LLM Audio (Sentences)"].queuedWords).toEqual(["你好", "谢谢"]);
    expect(queued.nodeRuntime["LLM Audio (Sentences)"].runningWords).toEqual([]);
    expect(queued.nodeRuntime["LLM Audio (Sentences)"].wordsLeft).toBe(2);
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
