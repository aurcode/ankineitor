import { getAuthToken } from "../api/pipeline";
import {
  BackgroundJobEventEnvelope,
  BackgroundJobSummary,
  JobWebsocketMessage,
  PipelineEventEnvelope,
  PipelineWebsocketMessage,
} from "../types/pipeline";

const WS_BASE = import.meta.env.VITE_WS_BASE_URL || "";

function buildWebsocketUrl(path: string): string {
  let baseUrl = "";
  if (WS_BASE) {
    baseUrl = `${WS_BASE}${path}`;
  } else {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    baseUrl = `${protocol}://${window.location.host}${path}`;
  }

  const token = getAuthToken();
  if (!token) {
    return baseUrl;
  }

  const separator = baseUrl.includes("?") ? "&" : "?";
  return `${baseUrl}${separator}token=${encodeURIComponent(token)}`;
}

export function subscribeToPipelineRun(
  runId: string,
  handlers: {
    onEvent: (event: PipelineEventEnvelope) => void;
    onOpen?: () => void;
    onClose?: () => void;
    onError?: (error: string) => void;
  },
): () => void {
  const socket = new WebSocket(buildWebsocketUrl(`/ws/pipeline/runs/${runId}`));

  socket.onopen = () => {
    handlers.onOpen?.();
  };

  socket.onclose = () => {
    handlers.onClose?.();
  };

  socket.onerror = () => {
    handlers.onError?.("WebSocket connection error");
  };

  socket.onmessage = (message) => {
    try {
      const parsed = JSON.parse(String(message.data || "{}")) as PipelineWebsocketMessage;
      if (parsed.type !== "pipeline_event" || !parsed.event) {
        return;
      }
      handlers.onEvent(parsed.event);
    } catch (error) {
      handlers.onError?.(`Invalid websocket payload: ${String(error)}`);
    }
  };

  return () => {
    socket.close();
  };
}

export function subscribeToBackgroundJob(
  jobId: string,
  handlers: {
    onEvent: (event: BackgroundJobEventEnvelope) => void;
    onSnapshot?: (job: BackgroundJobSummary) => void;
    onOpen?: () => void;
    onClose?: () => void;
    onError?: (error: string) => void;
  },
): () => void {
  const socket = new WebSocket(buildWebsocketUrl(`/ws/jobs/${jobId}`));

  socket.onopen = () => {
    handlers.onOpen?.();
  };

  socket.onclose = () => {
    handlers.onClose?.();
  };

  socket.onerror = () => {
    handlers.onError?.("WebSocket connection error");
  };

  socket.onmessage = (message) => {
    try {
      const parsed = JSON.parse(String(message.data || "{}")) as JobWebsocketMessage;
      if (parsed.type === "job_snapshot" && parsed.job) {
        handlers.onSnapshot?.(parsed.job);
        return;
      }
      if (parsed.type === "job_event" && parsed.event) {
        handlers.onEvent(parsed.event);
      }
    } catch (error) {
      handlers.onError?.(`Invalid websocket payload: ${String(error)}`);
    }
  };

  return () => {
    socket.close();
  };
}
