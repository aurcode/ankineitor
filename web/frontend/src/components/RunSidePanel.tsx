import { PipelineEventEnvelope, RunSummary } from "../types/pipeline";

interface RunSidePanelProps {
  run: RunSummary | null;
  progressRatio: number;
  statusText: string;
  counters: Record<string, number>;
  events: PipelineEventEnvelope[];
}

export function RunSidePanel(props: RunSidePanelProps) {
  const recentEvents = props.events.slice(-12).reverse();

  return (
    <aside className="run-side-panel">
      <section className="panel-card">
        <h3>Run Status</h3>
        <p>
          <strong>{props.run?.status ?? "idle"}</strong>
        </p>
        <progress max={1} value={Math.max(0, Math.min(1, props.progressRatio || 0))} />
        <p className="muted">{props.statusText || "Awaiting pipeline events..."}</p>
      </section>

      <section className="panel-card">
        <h3>Counters</h3>
        <ul className="plain-list">
          <li>Cached: {props.counters.cached_words ?? 0}</li>
          <li>New: {props.counters.new_words ?? 0}</li>
          <li>Backfill: {props.counters.backfill_words ?? 0}</li>
          <li>Unique: {props.counters.total_unique_words ?? 0}</li>
        </ul>
      </section>

      <section className="panel-card">
        <h3>Slowest Steps</h3>
        {props.run?.slowest_steps && props.run.slowest_steps.length > 0 ? (
          <ul className="plain-list">
            {props.run.slowest_steps.map((item) => (
              <li key={`${item.stage}:${item.step}`}>
                {item.step} ({item.stage}) - {item.seconds.toFixed(2)}s
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No timings yet.</p>
        )}
      </section>

      <section className="panel-card events-card">
        <h3>Events</h3>
        <ul className="plain-list events-list">
          {recentEvents.map((event) => (
            <li key={`${event.sequence}:${event.id}`}>
              <div className="event-type">{String(event.payload.event)}</div>
              <div className="event-meta">
                #{event.sequence} {new Date(event.created_at).toLocaleTimeString()}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
