import { useEffect, useState } from "react";

import {
  adminCancelPipelineRun,
  adminPausePipelineRun,
  adminResumePipelineRun,
  getAdminQueueMonitor,
} from "../api/pipeline";
import { AdminQueueMonitorResponse, CeleryTaskSnapshot, CeleryWorkerSnapshot } from "../types/pipeline";

const REFRESH_INTERVAL_MS = 3000;

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "n/a";
  }
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function formatPercent(value: number): string {
  const safe = Math.max(0, Math.min(1, Number(value || 0)));
  return `${Math.round(safe * 100)}%`;
}

function TaskList(props: {
  title: string;
  tasks: CeleryTaskSnapshot[];
  showEta?: boolean;
}): JSX.Element {
  return (
    <div className="admin-task-column">
      <h4>
        {props.title} ({props.tasks.length})
      </h4>
      {props.tasks.length === 0 ? (
        <p className="muted">None.</p>
      ) : (
        <div className="admin-task-list">
          {props.tasks.map((task, index) => (
            <div key={`${props.title}:${task.id}:${task.name}:${index}`} className="admin-task-row">
              <p className="event-type">{task.name || "unknown task"}</p>
              <p className="small">id: {task.id || "n/a"}</p>
              {props.showEta ? <p className="small">eta: {task.eta || "n/a"}</p> : null}
              <p className="small">args: {task.args || "[]"}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function WorkerCard(props: { worker: CeleryWorkerSnapshot }): JSX.Element {
  const worker = props.worker;
  return (
    <article className="panel-card">
      <div className="inline-controls wrap">
        <h3>{worker.worker_name}</h3>
        <span className="muted">max concurrency: {worker.max_concurrency || 0}</span>
      </div>
      <p className="small">
        queues: {worker.queues.length > 0 ? worker.queues.join(", ") : "none"}
      </p>
      <p className="small">
        active {worker.active_count} | reserved {worker.reserved_count} | scheduled{" "}
        {worker.scheduled_count}
      </p>
      <div className="admin-task-columns">
        <TaskList title="Active" tasks={worker.active_tasks} />
        <TaskList title="Reserved" tasks={worker.reserved_tasks} />
        <TaskList title="Scheduled" tasks={worker.scheduled_tasks} showEta />
      </div>
    </article>
  );
}

export function AdminQueueMonitorPage() {
  const [snapshot, setSnapshot] = useState<AdminQueueMonitorResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [actionRunId, setActionRunId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  const refreshSnapshot = async (): Promise<void> => {
    const payload = await getAdminQueueMonitor();
    setSnapshot(payload);
    setErrorMessage("");
  };

  useEffect(() => {
    let active = true;

    const loadSnapshot = async (asRefresh: boolean) => {
      if (asRefresh) {
        if (active) {
          setIsRefreshing(true);
        }
      } else if (active) {
        setIsLoading(true);
      }

      try {
        const payload = await getAdminQueueMonitor();
        if (!active) {
          return;
        }
        setSnapshot(payload);
        setErrorMessage("");
      } catch (error) {
        if (!active) {
          return;
        }
        setErrorMessage(String(error));
      } finally {
        if (active) {
          setIsLoading(false);
          setIsRefreshing(false);
        }
      }
    };

    void loadSnapshot(false);
    const timer = window.setInterval(() => {
      void loadSnapshot(true);
    }, REFRESH_INTERVAL_MS);

    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const handleRunAction = async (
    runId: string,
    action: "pause" | "cancel" | "resume",
  ): Promise<void> => {
    setActionRunId(runId);
    setErrorMessage("");
    try {
      if (action === "pause") {
        await adminPausePipelineRun(runId);
      } else if (action === "cancel") {
        await adminCancelPipelineRun(runId);
      } else {
        await adminResumePipelineRun(runId);
      }
      await refreshSnapshot();
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setActionRunId(null);
    }
  };

  const summary = snapshot?.summary || {
    active_pipeline_runs: 0,
    active_background_jobs: 0,
    celery_workers: 0,
    celery_active_tasks: 0,
    celery_reserved_tasks: 0,
    celery_scheduled_tasks: 0,
  };
  const pipelineRuns = snapshot?.pipeline_runs || [];
  const backgroundJobs = snapshot?.background_jobs || [];
  const celeryWorkers = snapshot?.celery.workers || [];
  const celeryError = snapshot?.celery.error || "";

  return (
    <div className="workspace-page single-column">
      <header className="page-header">
        <h1>Admin Queue Monitor</h1>
        <p>Live view of all active queues and worker processes across users.</p>
      </header>

      <section className="panel-block admin-metric-grid">
        <article className="panel-card admin-metric-card">
          <p className="muted">Pipeline Runs</p>
          <p className="admin-metric-value">{summary.active_pipeline_runs}</p>
        </article>
        <article className="panel-card admin-metric-card">
          <p className="muted">Background Jobs</p>
          <p className="admin-metric-value">{summary.active_background_jobs}</p>
        </article>
        <article className="panel-card admin-metric-card">
          <p className="muted">Celery Workers</p>
          <p className="admin-metric-value">{summary.celery_workers}</p>
        </article>
        <article className="panel-card admin-metric-card">
          <p className="muted">Celery Active Tasks</p>
          <p className="admin-metric-value">{summary.celery_active_tasks}</p>
        </article>
        <article className="panel-card admin-metric-card">
          <p className="muted">Celery Reserved Tasks</p>
          <p className="admin-metric-value">{summary.celery_reserved_tasks}</p>
        </article>
        <article className="panel-card admin-metric-card">
          <p className="muted">Celery Scheduled Tasks</p>
          <p className="admin-metric-value">{summary.celery_scheduled_tasks}</p>
        </article>
      </section>

      <section className="panel-block">
        <div className="inline-controls wrap">
          <p className="muted">
            Last updated: {formatTimestamp(snapshot?.generated_at)}{" "}
            {isRefreshing ? "(refreshing...)" : ""}
          </p>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setIsRefreshing(true);
              void refreshSnapshot()
                .catch((error) => {
                  setErrorMessage(String(error));
                })
                .finally(() => {
                  setIsRefreshing(false);
                });
            }}
            disabled={isLoading || isRefreshing}
          >
            {isLoading || isRefreshing ? "Refreshing..." : "Refresh now"}
          </button>
        </div>
        {errorMessage ? (
          <p className="error-message" role="alert">
            {errorMessage}
          </p>
        ) : null}
      </section>

      <section className="panel-block">
        <h2>Active Pipeline Runs</h2>
        {pipelineRuns.length === 0 ? (
          <p className="muted">No active pipeline runs.</p>
        ) : (
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th scope="col">Run</th>
                  <th scope="col">Owner</th>
                  <th scope="col">Status</th>
                  <th scope="col">Profile</th>
                  <th scope="col">Transform</th>
                  <th scope="col">Word</th>
                  <th scope="col">Left</th>
                  <th scope="col">Running</th>
                  <th scope="col">Queued</th>
                  <th scope="col">Created</th>
                  <th scope="col">Started</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {pipelineRuns.map((run) => (
                  <tr key={run.id}>
                    <td title={run.id}>{run.id.slice(0, 8)}...</td>
                    <td>{run.owner_username || "n/a"}</td>
                    <td>{run.status}</td>
                    <td>{run.profile_id}</td>
                    <td>{run.current_transform || run.last_event_type || "n/a"}</td>
                    <td>{run.current_word || "n/a"}</td>
                    <td>{run.words_left}</td>
                    <td>{run.running_count}</td>
                    <td>{run.queued_count}</td>
                    <td>{formatTimestamp(run.created_at)}</td>
                    <td>{formatTimestamp(run.started_at)}</td>
                    <td>
                      <div className="inline-controls wrap">
                        {run.status === "paused" ? (
                          <button
                            type="button"
                            className="secondary"
                            disabled={actionRunId === run.id}
                            onClick={() => {
                              void handleRunAction(run.id, "resume");
                            }}
                          >
                            {actionRunId === run.id ? "Resuming..." : "Resume"}
                          </button>
                        ) : null}
                        {run.status !== "paused" && run.status !== "canceled" ? (
                          <button
                            type="button"
                            className="secondary"
                            disabled={actionRunId === run.id}
                            onClick={() => {
                              void handleRunAction(run.id, "pause");
                            }}
                          >
                            {actionRunId === run.id ? "Pausing..." : "Pause"}
                          </button>
                        ) : null}
                        {run.status !== "canceled" ? (
                          <button
                            type="button"
                            className="secondary"
                            disabled={actionRunId === run.id}
                            onClick={() => {
                              void handleRunAction(run.id, "cancel");
                            }}
                          >
                            {actionRunId === run.id ? "Canceling..." : "Cancel"}
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel-block">
        <h2>Active Background Jobs</h2>
        {backgroundJobs.length === 0 ? (
          <p className="muted">No active background jobs.</p>
        ) : (
          <div className="table-shell">
            <table>
              <thead>
                <tr>
                  <th scope="col">Job</th>
                  <th scope="col">Owner</th>
                  <th scope="col">Type</th>
                  <th scope="col">Status</th>
                  <th scope="col">Progress</th>
                  <th scope="col">Status Text</th>
                  <th scope="col">Created</th>
                  <th scope="col">Started</th>
                </tr>
              </thead>
              <tbody>
                {backgroundJobs.map((job) => (
                  <tr key={job.id}>
                    <td title={job.id}>{job.id.slice(0, 8)}...</td>
                    <td>{job.owner_username || "n/a"}</td>
                    <td>{job.job_type}</td>
                    <td>{job.status}</td>
                    <td>{formatPercent(job.progress_ratio)}</td>
                    <td>{job.status_text || "n/a"}</td>
                    <td>{formatTimestamp(job.created_at)}</td>
                    <td>{formatTimestamp(job.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="panel-block">
        <h2>Celery Workers</h2>
        {celeryError ? (
          <p className="error-message" role="alert">
            {celeryError}
          </p>
        ) : null}
      {celeryWorkers.length === 0 ? (
          <p className="muted">No worker inspector data available.</p>
        ) : (
          <div className="admin-worker-grid">
            {celeryWorkers.map((worker) => (
              <WorkerCard key={worker.worker_name} worker={worker} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
