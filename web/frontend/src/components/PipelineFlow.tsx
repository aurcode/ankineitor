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
import { NodeRuntimeState } from "../state/pipelineFlowReducer";

interface PipelineFlowProps {
  transformNames: string[];
  nodeStatuses: Record<string, NodeExecutionStatus>;
  nodeDurations: Record<string, number>;
  nodeRuntime: Record<string, NodeRuntimeState>;
  activeNodes: string[];
}

const DEPENDENCY_RULES: Record<string, string[]> = {
  "LLM Audio (Sentences)": ["LLM (Meanings/Sentences)"],
  "LLM Image Renderer (Master Prompt)": ["LLM Image Prompt (Visual Translator)"],
};

interface DependencyEdge {
  source: string;
  target: string;
}

interface GraphPoint {
  x: number;
  y: number;
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

export function resolveDependencyEdges(transformNames: string[]): DependencyEdge[] {
  const edges: DependencyEdge[] = [];
  for (const target of transformNames) {
    const dependencies = DEPENDENCY_RULES[target] ?? [];
    for (const source of dependencies) {
      if (!transformNames.includes(source)) {
        continue;
      }
      edges.push({ source, target });
    }
  }
  return edges;
}

function resolveChainEdges(transformNames: string[]): DependencyEdge[] {
  const edges: DependencyEdge[] = [];
  for (let index = 0; index < transformNames.length - 1; index += 1) {
    edges.push({
      source: transformNames[index],
      target: transformNames[index + 1],
    });
  }
  return edges;
}

export function resolveRenderableEdges(transformNames: string[]): DependencyEdge[] {
  const names = [...transformNames];
  const knownDependencies = resolveDependencyEdges(names);
  if (knownDependencies.length > 0) {
    return knownDependencies;
  }
  return resolveChainEdges(names);
}

function resolveTopologicalOrder(
  names: string[],
  edges: DependencyEdge[],
): { ordered: string[]; outgoing: Record<string, string[]> } {
  const originalIndex: Record<string, number> = {};
  const indegree: Record<string, number> = {};
  const outgoing: Record<string, string[]> = {};
  for (let index = 0; index < names.length; index += 1) {
    originalIndex[names[index]] = index;
    indegree[names[index]] = 0;
    outgoing[names[index]] = [];
  }

  for (const edge of edges) {
    outgoing[edge.source].push(edge.target);
    indegree[edge.target] += 1;
  }

  const queue = names.filter((name) => indegree[name] === 0);
  queue.sort((a, b) => originalIndex[a] - originalIndex[b]);

  const ordered: string[] = [];
  while (queue.length > 0) {
    const current = queue.shift();
    if (!current) {
      break;
    }
    ordered.push(current);

    for (const target of outgoing[current]) {
      indegree[target] -= 1;
      if (indegree[target] === 0) {
        queue.push(target);
      }
    }
    queue.sort((a, b) => originalIndex[a] - originalIndex[b]);
  }

  if (ordered.length !== names.length) {
    return { ordered: names, outgoing };
  }
  return { ordered, outgoing };
}

export function resolveGraphOrder(transformNames: string[]): string[] {
  const names = [...transformNames];
  const edges = resolveRenderableEdges(names);
  return resolveTopologicalOrder(names, edges).ordered;
}

export function resolveGraphLayout(transformNames: string[]): Record<string, GraphPoint> {
  const names = [...transformNames];
  const edges = resolveRenderableEdges(names);
  const { ordered, outgoing } = resolveTopologicalOrder(names, edges);

  const originalIndex: Record<string, number> = {};
  for (let index = 0; index < names.length; index += 1) {
    originalIndex[names[index]] = index;
  }

  const depthByNode: Record<string, number> = {};
  for (const name of names) {
    depthByNode[name] = 0;
  }
  for (const name of ordered) {
    const sourceDepth = depthByNode[name];
    for (const target of outgoing[name] ?? []) {
      depthByNode[target] = Math.max(depthByNode[target], sourceDepth + 1);
    }
  }

  const nodesByDepth: Record<number, string[]> = {};
  for (const name of names) {
    const depth = depthByNode[name] ?? 0;
    if (!nodesByDepth[depth]) {
      nodesByDepth[depth] = [];
    }
    nodesByDepth[depth].push(name);
  }
  for (const depthKey of Object.keys(nodesByDepth)) {
    const depth = Number(depthKey);
    nodesByDepth[depth].sort((a, b) => originalIndex[a] - originalIndex[b]);
  }

  const HORIZONTAL_GAP = 230;
  const VERTICAL_GAP = 180;
  const BASE_Y = 120;
  const positions: Record<string, GraphPoint> = {};

  const sortedDepths = Object.keys(nodesByDepth)
    .map((key) => Number(key))
    .sort((a, b) => a - b);
  for (const depth of sortedDepths) {
    const rowNodes = nodesByDepth[depth] ?? [];
    const rowOffset = (rowNodes.length - 1) / 2;
    for (let rowIndex = 0; rowIndex < rowNodes.length; rowIndex += 1) {
      const name = rowNodes[rowIndex];
      positions[name] = {
        x: (rowIndex - rowOffset) * HORIZONTAL_GAP,
        y: BASE_Y + depth * VERTICAL_GAP,
      };
    }
  }

  return positions;
}

export function PipelineFlow(props: PipelineFlowProps) {
  const orderedTransformNames = useMemo(() => resolveGraphOrder(props.transformNames), [
    props.transformNames,
  ]);
  const graphLayout = useMemo(() => resolveGraphLayout(props.transformNames), [
    props.transformNames,
  ]);

  const nodes = useMemo<Node[]>(() => {
    return orderedTransformNames.map((name, index) => {
      const status = props.nodeStatuses[name] ?? "idle";
      const seconds = props.nodeDurations[name];
      const runtime = props.nodeRuntime[name];
      const timingLabel = typeof seconds === "number" ? `${seconds.toFixed(2)}s` : "";
      const currentWord = runtime?.currentWord || "-";
      const wordsLeftLabel =
        typeof runtime?.wordsLeft === "number" ? String(runtime.wordsLeft) : "-";
      const runningWords = runtime?.runningWords ?? [];
      const queuedWords = runtime?.queuedWords ?? [];
      const runningLabel = runningWords.length > 0 ? runningWords.join(", ") : "-";
      const queuePreview =
        queuedWords.length > 0 ? queuedWords.slice(0, 2).join(", ") : "";
      const queueLabel = queuePreview
        ? `${queuedWords.length} (${queuePreview}${queuedWords.length > 2 ? ", ..." : ""})`
        : wordsLeftLabel;

      return {
        id: name,
        position: graphLayout[name] ?? { x: 220 * index, y: 120 },
        sourcePosition: Position.Bottom,
        targetPosition: Position.Top,
        data: {
          label: (
            <div className="flow-node">
              <div className="flow-node-title">{name}</div>
              <div className="flow-node-meta">
                <span className="flow-node-status">{status}</span>
                {timingLabel ? <span>{timingLabel}</span> : null}
              </div>
              <div className="flow-node-progress">
                <span>word: {currentWord}</span>
                <span>left: {wordsLeftLabel}</span>
              </div>
              <div className="flow-node-progress">
                <span>running: {runningLabel}</span>
              </div>
              <div className="flow-node-progress">
                <span>queue: {queueLabel}</span>
              </div>
            </div>
          ),
        },
        style: {
          borderRadius: 14,
          border: `2px solid ${STATUS_COLORS[status]}`,
          background: STATUS_BG[status],
          width: 190,
          minHeight: 128,
          fontSize: 12,
          boxShadow: status === "running" ? "0 0 0 3px rgba(11, 114, 133, 0.18)" : "none",
        },
      };
    });
  }, [
    props.activeNodes,
    props.nodeDurations,
    props.nodeRuntime,
    props.nodeStatuses,
    graphLayout,
    orderedTransformNames,
  ]);

  const edges = useMemo<Edge[]>(() => {
    const generated: Edge[] = [];
    const renderableEdges = resolveRenderableEdges(orderedTransformNames);
    for (const dependencyEdge of renderableEdges) {
      const source = dependencyEdge.source;
      const target = dependencyEdge.target;
      generated.push({
        id: `${source}->${target}`,
        source,
        target,
        animated: props.activeNodes.includes(source),
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: props.activeNodes.includes(source) ? "#0b7285" : "#9ca3af",
        },
        style: {
          strokeWidth: props.activeNodes.includes(source) ? 3 : 2,
          stroke: props.activeNodes.includes(source) ? "#0b7285" : "#9ca3af",
        },
      });
    }
    return generated;
  }, [props.activeNodes, orderedTransformNames]);

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
