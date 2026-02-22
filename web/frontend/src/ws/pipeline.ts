import { PipelineEventEnvelope, PipelineWebsocketMessage } from "../types/pipeline";

const WS_BASE = import.meta.env.VITE_WS_BASE_URL || "";

function buildWebsocketUrl(path: string): string {
  if (WS_BASE) {
    return `${WS_BASE}${path}`;
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.host}${path}`;
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
