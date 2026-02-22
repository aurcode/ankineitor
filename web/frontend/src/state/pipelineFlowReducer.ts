import {
  NodeExecutionStatus,
  PipelineEventEnvelope,
  PipelineEventPayload,
} from "../types/pipeline";

export interface NodeRuntimeState {
  currentWord: string;
  wordsLeft: number | null;
  runningWords: string[];
  queuedWords: string[];
}

export interface GraphExecutionState {
  nodeStatuses: Record<string, NodeExecutionStatus>;
  nodeDurations: Record<string, number>;
  nodeRuntime: Record<string, NodeRuntimeState>;
  activeNode: string | null;
  activeNodes: string[];
  statusText: string;
  progressRatio: number;
  counters: Record<string, number>;
  eventLog: PipelineEventEnvelope[];
}

const CLASS_NAME_TO_LABEL: Record<string, string> = {
  AudioTransformation: "Audio",
  TimestampTransformation: "Timestamp",
  LLMTransformation: "LLM (Meanings/Sentences)",
  LLMImagePromptTransformation: "LLM Image Prompt (Visual Translator)",
  LLMImageTransformation: "LLM Image Renderer (Master Prompt)",
  LLMAudioTransformation: "LLM Audio (Sentences)",
};

function normalizeToken(value: string): string {
  return value.replace(/[^a-zA-Z0-9]/g, "").toLowerCase();
}

function mapEventToNode(payload: PipelineEventPayload, nodes: string[]): string | null {
  const explicit = typeof payload.transform_key === "string" ? payload.transform_key : "";
  if (explicit && nodes.includes(explicit)) {
    return explicit;
  }

  const rawName = typeof payload.transform_name === "string" ? payload.transform_name : "";
  if (!rawName) {
    return null;
  }

  const mapped = CLASS_NAME_TO_LABEL[rawName];
  if (mapped && nodes.includes(mapped)) {
    return mapped;
  }

  if (nodes.includes(rawName)) {
    return rawName;
  }

  const stripped = rawName.replace(/Transformation$/, "");
  const normalizedStripped = normalizeToken(stripped);
  const normalizedRaw = normalizeToken(rawName);

  for (const node of nodes) {
    const normalizedNode = normalizeToken(node);
    if (normalizedNode === normalizedStripped || normalizedNode === normalizedRaw) {
      return node;
    }
    if (normalizedNode.startsWith(normalizedStripped) && normalizedStripped.length >= 3) {
      return node;
    }
  }

  return null;
}

function toWordsLeft(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return Math.max(Math.floor(value), 0);
}

function toCurrentWord(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function toWordList(value: unknown): string[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter((item) => item.length > 0);
}

function defaultRuntimeState(): NodeRuntimeState {
  return {
    currentWord: "",
    wordsLeft: null,
    runningWords: [],
    queuedWords: [],
  };
}

export function initializeGraphState(transformNames: string[]): GraphExecutionState {
  const nodeStatuses: Record<string, NodeExecutionStatus> = {};
  const nodeRuntime: Record<string, NodeRuntimeState> = {};
  for (const name of transformNames) {
    nodeStatuses[name] = "queued";
    nodeRuntime[name] = defaultRuntimeState();
  }

  return {
    nodeStatuses,
    nodeDurations: {},
    nodeRuntime,
    activeNode: null,
    activeNodes: [],
    statusText: "",
    progressRatio: 0,
    counters: {},
    eventLog: [],
  };
}

export function applyPipelineEvent(
  previous: GraphExecutionState,
  envelope: PipelineEventEnvelope,
  transformNames: string[],
): GraphExecutionState {
  const payload = envelope.payload;
  const eventType = String(payload.event || "");
  const nextStatuses: Record<string, NodeExecutionStatus> = { ...previous.nodeStatuses };
  const nextDurations = { ...previous.nodeDurations };
  const nextNodeRuntime = { ...previous.nodeRuntime };
  const nextCounters = { ...previous.counters };
  const nextActiveNodes = new Set(previous.activeNodes);
  let progressRatio = previous.progressRatio;

  const resolvedNode = mapEventToNode(payload, transformNames);

  if (eventType === "pipeline_start") {
    for (const name of transformNames) {
      if (nextStatuses[name] === "idle") {
        nextStatuses[name] = "queued";
      }
    }
  }

  if (eventType === "cache_checked") {
    if (typeof payload.cached_words === "number") {
      nextCounters.cached_words = payload.cached_words;
    }
    if (typeof payload.new_words === "number") {
      nextCounters.new_words = payload.new_words;
    }
    if (typeof payload.backfill_words === "number") {
      nextCounters.backfill_words = payload.backfill_words;
    }
    if (typeof payload.total_unique_words === "number") {
      nextCounters.total_unique_words = payload.total_unique_words;
    }
  }

  if (eventType === "transform_queue" && resolvedNode) {
    const previousRuntime = previous.nodeRuntime[resolvedNode] ?? defaultRuntimeState();
    const eventCurrentWord = toCurrentWord(payload.current_word);
    const eventWordsLeft = toWordsLeft(payload.words_left);
    const eventQueuedWords = toWordList(payload.queued_words);
    const queuedWords = eventQueuedWords ?? previousRuntime.queuedWords;

    nextNodeRuntime[resolvedNode] = {
      currentWord: eventCurrentWord ?? previousRuntime.currentWord,
      wordsLeft:
        eventWordsLeft !== null
          ? eventWordsLeft
          : queuedWords.length > 0
            ? queuedWords.length
            : previousRuntime.wordsLeft,
      runningWords: [],
      queuedWords,
    };

    if (nextStatuses[resolvedNode] !== "running" && nextStatuses[resolvedNode] !== "error") {
      nextStatuses[resolvedNode] = "queued";
    }
  }

  if (eventType === "transform_start" && resolvedNode) {
    nextStatuses[resolvedNode] = "running";
    nextActiveNodes.add(resolvedNode);

    const previousRuntime = previous.nodeRuntime[resolvedNode] ?? defaultRuntimeState();
    const eventCurrentWord = toCurrentWord(payload.current_word);
    const eventWordsLeft = toWordsLeft(payload.words_left);
    const eventRunningWords = toWordList(payload.running_words);
    const eventQueuedWords = toWordList(payload.queued_words);
    const inputRows = toWordsLeft(payload.input_rows);
    const fallbackWordsLeft =
      inputRows !== null ? Math.max(inputRows - (eventCurrentWord ? 1 : 0), 0) : null;
    const runningWords =
      eventRunningWords ??
      (eventCurrentWord
        ? Array.from(new Set([...previousRuntime.runningWords, eventCurrentWord]))
        : previousRuntime.runningWords);
    const queuedWords = eventQueuedWords ?? previousRuntime.queuedWords;

    nextNodeRuntime[resolvedNode] = {
      currentWord: eventCurrentWord ?? previousRuntime.currentWord,
      wordsLeft:
        eventWordsLeft !== null
          ? eventWordsLeft
          : queuedWords.length > 0
            ? queuedWords.length
            : fallbackWordsLeft !== null
              ? fallbackWordsLeft
              : previousRuntime.wordsLeft,
      runningWords,
      queuedWords,
    };
  }

  if (eventType === "transform_complete" && resolvedNode) {
    const hasError = Boolean(payload.error);
    if (typeof payload.duration_seconds === "number") {
      nextDurations[resolvedNode] = payload.duration_seconds;
    }

    const previousRuntime = previous.nodeRuntime[resolvedNode] ?? defaultRuntimeState();
    const eventCurrentWord = toCurrentWord(payload.current_word);
    const eventWordsLeft = toWordsLeft(payload.words_left);
    const eventRunningWords = toWordList(payload.running_words);
    const eventQueuedWords = toWordList(payload.queued_words);
    const runningWords =
      eventRunningWords ??
      previousRuntime.runningWords.filter((word) => !eventCurrentWord || word !== eventCurrentWord);
    const queuedWords = eventQueuedWords ?? previousRuntime.queuedWords;

    nextNodeRuntime[resolvedNode] = {
      currentWord: eventCurrentWord ?? previousRuntime.currentWord,
      wordsLeft:
        eventWordsLeft !== null
          ? eventWordsLeft
          : queuedWords.length > 0
            ? queuedWords.length
            : 0,
      runningWords,
      queuedWords,
    };

    if (hasError) {
      nextStatuses[resolvedNode] = "error";
      nextActiveNodes.delete(resolvedNode);
    } else if (runningWords.length > 0) {
      nextStatuses[resolvedNode] = "running";
      nextActiveNodes.add(resolvedNode);
    } else if (queuedWords.length > 0) {
      nextStatuses[resolvedNode] = "queued";
      nextActiveNodes.delete(resolvedNode);
    } else {
      nextStatuses[resolvedNode] = "success";
      nextActiveNodes.delete(resolvedNode);
    }
  }

  if (eventType === "pipeline_complete") {
    for (const name of transformNames) {
      if (nextStatuses[name] === "queued" || nextStatuses[name] === "running") {
        nextStatuses[name] = "success";
      }
      const previousRuntime = nextNodeRuntime[name] ?? defaultRuntimeState();
      nextNodeRuntime[name] = {
        currentWord: previousRuntime.currentWord,
        wordsLeft: 0,
        runningWords: [],
        queuedWords: [],
      };
    }
    nextActiveNodes.clear();
  }

  if (eventType === "pipeline_error") {
    for (const node of nextActiveNodes) {
      nextStatuses[node] = "error";
    }
    nextActiveNodes.clear();
  }

  if (typeof payload.progress_ratio === "number") {
    progressRatio = payload.progress_ratio;
  }

  const nextLog = [...previous.eventLog, envelope];
  if (nextLog.length > 200) {
    nextLog.splice(0, nextLog.length - 200);
  }

  const orderedActiveNodes = transformNames.filter((name) => nextActiveNodes.has(name));
  const activeNode = orderedActiveNodes[0] ?? null;

  return {
    nodeStatuses: nextStatuses,
    nodeDurations: nextDurations,
    nodeRuntime: nextNodeRuntime,
    activeNode,
    activeNodes: orderedActiveNodes,
    statusText: String(payload.status_text || previous.statusText || ""),
    progressRatio,
    counters: nextCounters,
    eventLog: nextLog,
  };
}
