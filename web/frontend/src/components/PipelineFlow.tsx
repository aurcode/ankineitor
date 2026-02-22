import { useMemo } from "react";
import {
  Background,
  Controls,
  Edge,
  MarkerType,
  MiniMap,
  Node,
  Position,
  ReactFlow,
} from "@xyflow/react";

import { NodeExecutionStatus } from "../types/pipeline";

interface PipelineFlowProps {
  transformNames: string[];
  nodeStatuses: Record<string, NodeExecutionStatus>;
  nodeDurations: Record<string, number>;
  activeNode: string | null;
}

const STATUS_COLORS: Record<NodeExecutionStatus, string> = {
  idle: "#6b7280",
  queued: "#7c5f00",
  running: "#0b7285",
  success: "#256d1b",
  error: "#b3261e",
};

const STATUS_BG: Record<NodeExecutionStatus, string> = {
  idle: "#f3f4f6",
  queued: "#fff7d6",
  running: "#dff6fb",
  success: "#e3f8de",
  error: "#fde4e1",
};

export function PipelineFlow(props: PipelineFlowProps) {
  const nodes = useMemo<Node[]>(() => {
    return props.transformNames.map((name, index) => {
      const status = props.nodeStatuses[name] ?? "idle";
      const seconds = props.nodeDurations[name];
      const timingLabel = typeof seconds === "number" ? `${seconds.toFixed(2)}s` : "";

      return {
        id: name,
        position: { x: 220 * index, y: 120 },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        data: {
          label: (
            <div className="flow-node">
              <div className="flow-node-title">{name}</div>
              <div className="flow-node-meta">
                <span className="flow-node-status">{status}</span>
                {timingLabel ? <span>{timingLabel}</span> : null}
              </div>
            </div>
          ),
        },
        style: {
          borderRadius: 14,
          border: `2px solid ${STATUS_COLORS[status]}`,
          background: STATUS_BG[status],
          width: 190,
          minHeight: 92,
          fontSize: 12,
          boxShadow: status === "running" ? "0 0 0 3px rgba(11, 114, 133, 0.18)" : "none",
        },
      };
    });
  }, [props.activeNode, props.nodeDurations, props.nodeStatuses, props.transformNames]);

  const edges = useMemo<Edge[]>(() => {
    const generated: Edge[] = [];
    for (let index = 0; index < props.transformNames.length - 1; index += 1) {
      const source = props.transformNames[index];
      const target = props.transformNames[index + 1];
      generated.push({
        id: `${source}->${target}`,
        source,
        target,
        animated: props.activeNode === source,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: props.activeNode === source ? "#0b7285" : "#9ca3af",
        },
        style: {
          strokeWidth: props.activeNode === source ? 3 : 2,
          stroke: props.activeNode === source ? "#0b7285" : "#9ca3af",
        },
      });
    }
    return generated;
  }, [props.activeNode, props.transformNames]);

  return (
    <div className="flow-wrapper">
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <MiniMap pannable zoomable />
        <Background color="#e7eef1" gap={20} />
        <Controls />
      </ReactFlow>
    </div>
  );
}
