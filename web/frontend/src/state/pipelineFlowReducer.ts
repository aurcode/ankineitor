import {
  NodeExecutionStatus,
  PipelineEventEnvelope,
  PipelineEventPayload,
} from "../types/pipeline";

export interface GraphExecutionState {
  nodeStatuses: Record<string, NodeExecutionStatus>;
  nodeDurations: Record<string, number>;
  activeNode: string | null;
  statusText: string;
  progressRatio: number;
  counters: Record<string, number>;
  eventLog: PipelineEventEnvelope[];
}

const CLASS_NAME_TO_LABEL: Record<string, string> = {
  PinyinTransformation: "Pinyin",
  TranslationTransformation: "Translation (Legacy Google/CEDICT)",
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

export function initializeGraphState(transformNames: string[]): GraphExecutionState {
  const nodeStatuses: Record<string, NodeExecutionStatus> = {};
  for (const name of transformNames) {
    nodeStatuses[name] = "queued";
  }

  return {
    nodeStatuses,
    nodeDurations: {},
    activeNode: null,
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
  const nextCounters = { ...previous.counters };
  let activeNode = previous.activeNode;
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

  if (eventType === "transform_start" && resolvedNode) {
    nextStatuses[resolvedNode] = "running";
    activeNode = resolvedNode;
  }

  if (eventType === "transform_complete" && resolvedNode) {
    const hasError = Boolean(payload.error);
    nextStatuses[resolvedNode] = hasError ? "error" : "success";
    activeNode = hasError ? resolvedNode : activeNode === resolvedNode ? null : activeNode;
    if (typeof payload.duration_seconds === "number") {
      nextDurations[resolvedNode] = payload.duration_seconds;
    }
  }

  if (eventType === "pipeline_complete") {
    for (const name of transformNames) {
      if (nextStatuses[name] === "queued" || nextStatuses[name] === "running") {
        nextStatuses[name] = "success";
      }
    }
    activeNode = null;
  }

  if (eventType === "pipeline_error") {
    if (activeNode) {
      nextStatuses[activeNode] = "error";
    }
  }

  if (typeof payload.progress_ratio === "number") {
    progressRatio = payload.progress_ratio;
  }

  const nextLog = [...previous.eventLog, envelope];
  if (nextLog.length > 200) {
    nextLog.splice(0, nextLog.length - 200);
  }

  return {
    nodeStatuses: nextStatuses,
    nodeDurations: nextDurations,
    activeNode,
    statusText: String(payload.status_text || previous.statusText || ""),
    progressRatio,
    counters: nextCounters,
    eventLog: nextLog,
  };
}
