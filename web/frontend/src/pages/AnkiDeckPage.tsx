import { useEffect, useMemo, useRef, useState } from "react";

import {
  downloadAuthenticatedFile,
  generateAnkiDeck,
  getAnkiPresets,
  getBackgroundJob,
  getBackgroundJobEvents,
  listBackgroundJobs,
  retryBackgroundJob,
} from "../api/pipeline";
import {
  AnkiConfigPayload,
  AnkiJobResultPayload,
  AnkiPresetsResponse,
  BackgroundJobEventEnvelope,
  BackgroundJobSummary,
} from "../types/pipeline";
import { subscribeToBackgroundJob } from "../ws/pipeline";

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function upsertEvent(
  previous: BackgroundJobEventEnvelope[],
  incoming: BackgroundJobEventEnvelope,
): BackgroundJobEventEnvelope[] {
  const existing = previous.find((item) => item.sequence === incoming.sequence);
  if (existing) {
    return previous.map((item) => (item.sequence === incoming.sequence ? incoming : item));
  }
  return [...previous, incoming].sort((a, b) => a.sequence - b.sequence);
}

function upsertJob(
  previous: BackgroundJobSummary[],
  incoming: BackgroundJobSummary,
): BackgroundJobSummary[] {
  const filtered = previous.filter((job) => job.id !== incoming.id);
  return [incoming, ...filtered];
}

function parseAnkiResult(payload: Record<string, unknown>): AnkiJobResultPayload | null {
  const artifactId = payload.artifact_id;
  const deckName = payload.deck_name;
  const sourceCsvName = payload.source_csv_name;
  const fileSizeBytes = payload.file_size_bytes;
  const outputPath = payload.output_path;
  const createdAt = payload.created_at;

  if (
    typeof artifactId !== "string" ||
    typeof deckName !== "string" ||
    typeof sourceCsvName !== "string" ||
    typeof fileSizeBytes !== "number" ||
    typeof outputPath !== "string" ||
    typeof createdAt !== "string"
  ) {
    return null;
  }

  const downloadUrl = typeof payload.download_url === "string" ? payload.download_url : undefined;
  return {
    artifact_id: artifactId,
    deck_name: deckName,
    source_csv_name: sourceCsvName,
    file_size_bytes: fileSizeBytes,
    output_path: outputPath,
    created_at: createdAt,
    download_url: downloadUrl,
  };
}

function formatTimestamp(value: string | null): string {
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

export function AnkiDeckPage() {
  const [presets, setPresets] = useState<AnkiPresetsResponse | null>(null);
  const [presetKey, setPresetKey] = useState<"default" | "chinese_pipeline">("default");
  const [configJson, setConfigJson] = useState("");
  const [deckName, setDeckName] = useState("My Anki Deck");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [job, setJob] = useState<BackgroundJobSummary | null>(null);
  const [jobHistory, setJobHistory] = useState<BackgroundJobSummary[]>([]);
  const [events, setEvents] = useState<BackgroundJobEventEnvelope[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  const wsCleanupRef = useRef<(() => void) | null>(null);

  const isTerminal =
    job?.status === "success" || job?.status === "error" || job?.status === "canceled";
  const ankiResult = useMemo(() => parseAnkiResult(job?.result_payload || {}), [job?.result_payload]);

  useEffect(() => {
    let active = true;

    const loadInitialState = async () => {
      try {
        const [presetsPayload, jobsPayload] = await Promise.all([
          getAnkiPresets(),
          listBackgroundJobs({ jobType: "anki_deck", limit: 20 }),
        ]);
        if (!active) {
          return;
        }
        setPresets(presetsPayload);
        setConfigJson(prettyJson(presetsPayload.default));
        setJobHistory(jobsPayload.jobs || []);
      } catch (error) {
        if (active) {
          setErrorMessage(String(error));
        }
      }
    };

    void loadInitialState();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!job) {
      return;
    }

    wsCleanupRef.current?.();
    wsCleanupRef.current = subscribeToBackgroundJob(job.id, {
      onSnapshot: (snapshot) => {
        setJob(snapshot);
        setJobHistory((previous) => upsertJob(previous, snapshot));
      },
      onEvent: (event) => {
        setEvents((previous) => upsertEvent(previous, event));
      },
      onError: (error) => {
        setErrorMessage(error);
      },
    });

    return () => {
      wsCleanupRef.current?.();
      wsCleanupRef.current = null;
    };
  }, [job?.id]);

  useEffect(() => {
    if (!job || isTerminal) {
      return;
    }

    const timer = window.setInterval(() => {
      void getBackgroundJob(job.id)
        .then((payload) => {
          setJob(payload.job);
          setJobHistory((previous) => upsertJob(previous, payload.job));
        })
        .catch((error) => {
          setErrorMessage(String(error));
        });
    }, 2000);

    return () => {
      window.clearInterval(timer);
    };
  }, [job?.id, isTerminal]);

  const handlePresetChange = (value: "default" | "chinese_pipeline") => {
    setPresetKey(value);
    if (!presets) {
      return;
    }
    const config = value === "chinese_pipeline" ? presets.chinese_pipeline : presets.default;
    setConfigJson(prettyJson(config));
  };

  const handleSelectJob = async (jobId: string) => {
    setErrorMessage("");
    try {
      const [jobPayload, eventsPayload] = await Promise.all([
        getBackgroundJob(jobId),
        getBackgroundJobEvents(jobId),
      ]);
      setJob(jobPayload.job);
      setEvents(eventsPayload.events || []);
      setJobHistory((previous) => upsertJob(previous, jobPayload.job));
    } catch (error) {
      setErrorMessage(String(error));
    }
  };

  const handleGenerate = async () => {
    if (!csvFile) {
      setErrorMessage("Upload a CSV file first.");
      return;
    }

    let parsedConfig: AnkiConfigPayload;
    try {
      parsedConfig = JSON.parse(configJson) as AnkiConfigPayload;
    } catch (error) {
      setErrorMessage(`Invalid config JSON: ${String(error)}`);
      return;
    }

    setIsSubmitting(true);
    setErrorMessage("");
    setEvents([]);

    try {
      const payload = await generateAnkiDeck({
        csvFile,
        deckName,
        config: parsedConfig,
      });
      setJob(payload.job);
      setEvents(payload.events || []);
      setJobHistory((previous) => upsertJob(previous, payload.job));
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRetry = async (jobId: string) => {
    setRetryingJobId(jobId);
    setErrorMessage("");
    try {
      const payload = await retryBackgroundJob(jobId);
      setJob(payload.job);
      setEvents(payload.events || []);
      setJobHistory((previous) => upsertJob(previous, payload.job));
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setRetryingJobId(null);
    }
  };

  const handleDownload = async () => {
    if (!ankiResult?.download_url) {
      return;
    }
    setIsDownloading(true);
    setErrorMessage("");
    try {
      await downloadAuthenticatedFile({
        url: ankiResult.download_url,
        fallbackFileName: `${ankiResult.deck_name}.apkg`,
      });
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="workspace-page single-column">
      <header className="page-header">
        <h1>Anki Deck Generator</h1>
        <p>Generate `.apkg` decks in a background worker and stream progress events live.</p>
      </header>

      <section className="panel-block">
        <label className="field-label" htmlFor="anki-preset-select">
          Preset
        </label>
        <select
          id="anki-preset-select"
          value={presetKey}
          onChange={(event) => handlePresetChange(event.target.value as "default" | "chinese_pipeline")}
        >
          <option value="default">Default</option>
          <option value="chinese_pipeline">Chinese Pipeline</option>
        </select>

        <label className="field-label" htmlFor="anki-deck-name">
          Deck Name
        </label>
        <input
          id="anki-deck-name"
          value={deckName}
          onChange={(event) => setDeckName(event.target.value)}
        />

        <label className="field-label" htmlFor="anki-csv-upload">
          Vocabulary CSV
        </label>
        <input
          id="anki-csv-upload"
          type="file"
          accept=".csv"
          onChange={(event) => setCsvFile(event.target.files?.[0] ?? null)}
        />

        <label className="field-label" htmlFor="anki-config-json">
          Config JSON
        </label>
        <textarea
          id="anki-config-json"
          value={configJson}
          onChange={(event) => setConfigJson(event.target.value)}
          rows={16}
        />

        {errorMessage ? (
          <p className="error-message" role="alert">
            {errorMessage}
          </p>
        ) : null}

        <button type="button" className="primary" disabled={isSubmitting} onClick={handleGenerate}>
          {isSubmitting ? "Queuing..." : "Generate Deck"}
        </button>
      </section>

      <section className="panel-block">
        <h2>Recent Deck Jobs</h2>
        {jobHistory.length === 0 ? (
          <p className="muted">No jobs yet.</p>
        ) : (
          <ul className="plain-list job-history-list">
            {jobHistory.map((historyJob) => (
              <li key={historyJob.id} className="job-history-item">
                <div className="job-history-main">
                  <strong className="status-chip" data-status={historyJob.status}>
                    {historyJob.status}
                  </strong>
                  <span>{formatTimestamp(historyJob.created_at)}</span>
                  <code>{historyJob.id}</code>
                  <span className="muted">({formatPercent(historyJob.progress_ratio)})</span>
                </div>
                <div className="inline-controls wrap">
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => void handleSelectJob(historyJob.id)}
                  >
                    Open
                  </button>
                  {(historyJob.status === "error" || historyJob.status === "canceled") ? (
                    <button
                      type="button"
                      className="secondary"
                      disabled={retryingJobId === historyJob.id}
                      onClick={() => void handleRetry(historyJob.id)}
                    >
                      {retryingJobId === historyJob.id ? "Retrying..." : "Retry"}
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {job ? (
        <section className="panel-block">
          <h2>Job Status</h2>
          <p>
            Job <strong>{job.id}</strong>
          </p>
          <p className="muted">Status: {job.status}</p>
          <progress value={Math.max(0, Math.min(100, Math.round((job.progress_ratio || 0) * 100)))} max={100} />
          <p className="muted">{job.status_text || "In progress..."}</p>
          {job.error_message ? (
            <p className="error-message" role="alert">
              {job.error_message}
            </p>
          ) : null}

          {job.status === "success" && ankiResult ? (
            <div className="result-box">
              <p>
                Deck generated: <strong>{ankiResult.deck_name}</strong>
              </p>
              <p className="muted">Source: {ankiResult.source_csv_name}</p>
              {ankiResult.download_url ? (
                <button
                  type="button"
                  className="secondary"
                  onClick={handleDownload}
                  disabled={isDownloading}
                >
                  {isDownloading ? "Preparing..." : "Download .apkg"}
                </button>
              ) : null}
            </div>
          ) : null}

          <h3>Events</h3>
          {events.length === 0 ? (
            <p className="muted">No events yet.</p>
          ) : (
            <ul className="plain-list timeline-list">
              {events.slice(-20).map((event) => (
                <li key={`${event.job_id}:${event.sequence}`}>
                  [{event.sequence}] {String(event.payload.event || event.payload.event_type || "event")}
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
    </div>
  );
}
