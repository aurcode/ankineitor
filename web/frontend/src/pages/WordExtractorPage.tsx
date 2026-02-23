import { useEffect, useMemo, useRef, useState } from "react";

import {
  analyzeWordExtractor,
  cancelBackgroundJob,
  downloadAuthenticatedFile,
  getBackgroundJob,
  getBackgroundJobEvents,
  listBackgroundJobs,
  retryBackgroundJob,
} from "../api/pipeline";
import {
  BackgroundJobEventEnvelope,
  BackgroundJobSummary,
  WordExtractorResponse,
} from "../types/pipeline";
import { subscribeToBackgroundJob } from "../ws/pipeline";

const HSK_LEVELS = ["hsk1", "hsk2", "hsk3", "hsk4", "hsk5"];

function DataPreviewTable(props: {
  title: string;
  rows: Array<Record<string, string | number | null>>;
}): JSX.Element {
  const columns = useMemo(() => {
    const first = props.rows[0] || {};
    return Object.keys(first);
  }, [props.rows]);

  return (
    <div className="table-preview">
      <h3>{props.title}</h3>
      {props.rows.length === 0 ? (
        <p className="muted">No rows.</p>
      ) : (
        <div className="table-shell">
          <table>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column} scope="col">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {props.rows.slice(0, 30).map((row, rowIndex) => (
                <tr key={`${props.title}:${rowIndex}`}>
                  {columns.map((column) => (
                    <td key={`${props.title}:${rowIndex}:${column}`}>{String(row[column] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
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

function parseWordExtractorResult(payload: Record<string, unknown>): WordExtractorResponse | null {
  const summary = payload.summary;
  if (!summary || typeof summary !== "object") {
    return null;
  }

  const initialWords = Array.isArray(payload.initial_words) ? payload.initial_words : null;
  const filteredWords = Array.isArray(payload.filtered_words) ? payload.filtered_words : null;
  const removedWords = Array.isArray(payload.removed_words) ? payload.removed_words : null;
  const finalWords = Array.isArray(payload.final_words) ? payload.final_words : null;
  const copyableWordList = payload.copyable_word_list;
  const extractionErrors = payload.extraction_errors;

  if (
    !initialWords ||
    !filteredWords ||
    !removedWords ||
    !finalWords ||
    typeof copyableWordList !== "string" ||
    !extractionErrors ||
    typeof extractionErrors !== "object"
  ) {
    return null;
  }

  return payload as unknown as WordExtractorResponse;
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

export function WordExtractorPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [textInput, setTextInput] = useState("");
  const [selectedHskLevels, setSelectedHskLevels] = useState<string[]>([]);
  const [minFrequency, setMinFrequency] = useState(2);
  const [job, setJob] = useState<BackgroundJobSummary | null>(null);
  const [jobHistory, setJobHistory] = useState<BackgroundJobSummary[]>([]);
  const [events, setEvents] = useState<BackgroundJobEventEnvelope[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isDownloadingCsv, setIsDownloadingCsv] = useState(false);
  const [retryingJobId, setRetryingJobId] = useState<string | null>(null);
  const [cancelingJobId, setCancelingJobId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  const wsCleanupRef = useRef<(() => void) | null>(null);

  const isTerminal =
    job?.status === "success" || job?.status === "error" || job?.status === "canceled";
  const result = useMemo(
    () => parseWordExtractorResult(job?.result_payload || {}),
    [job?.result_payload],
  );
  const csvDownloadUrl = useMemo(() => {
    if (!job) {
      return "";
    }
    const fromPayload = job.result_payload?.csv_url;
    if (typeof fromPayload === "string" && fromPayload.trim()) {
      return fromPayload;
    }
    if (typeof job.csv_url === "string" && job.csv_url.trim()) {
      return job.csv_url;
    }
    return "";
  }, [job]);

  useEffect(() => {
    let active = true;

    const loadJobs = async () => {
      try {
        const payload = await listBackgroundJobs({ jobType: "word_extractor", limit: 20 });
        if (!active) {
          return;
        }
        setJobHistory(payload.jobs || []);
      } catch (error) {
        if (active) {
          setErrorMessage(String(error));
        }
      }
    };

    void loadJobs();
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

  const toggleHsk = (level: string, checked: boolean) => {
    setSelectedHskLevels((previous) => {
      const next = new Set(previous);
      if (checked) {
        next.add(level);
      } else {
        next.delete(level);
      }
      return Array.from(next);
    });
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

  const handleAnalyze = async () => {
    setIsLoading(true);
    setErrorMessage("");
    setEvents([]);
    try {
      const payload = await analyzeWordExtractor({
        files,
        textInput,
        selectedHskLevels,
        minFrequency,
      });
      setJob(payload.job);
      setEvents(payload.events || []);
      setJobHistory((previous) => upsertJob(previous, payload.job));
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsLoading(false);
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

  const handleCancel = async (jobId: string) => {
    setCancelingJobId(jobId);
    setErrorMessage("");
    try {
      const payload = await cancelBackgroundJob(jobId);
      setJob(payload.job);
      setJobHistory((previous) => upsertJob(previous, payload.job));
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setCancelingJobId(null);
    }
  };

  const handleDownloadCsv = async () => {
    if (!job || !csvDownloadUrl) {
      return;
    }
    setIsDownloadingCsv(true);
    setErrorMessage("");
    try {
      await downloadAuthenticatedFile({
        url: csvDownloadUrl,
        fallbackFileName: job.csv_download_name || `word_extractor_${job.id}.csv`,
      });
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsDownloadingCsv(false);
    }
  };

  return (
    <div className="workspace-page single-column">
      <header className="page-header">
        <h1>Word Extractor</h1>
        <p>Extract Chinese words in a background worker with live progress and filtering results.</p>
      </header>

      <section className="panel-block">
        <label className="field-label" htmlFor="word-files">
          Upload Documents
        </label>
        <input
          id="word-files"
          type="file"
          accept=".pdf,.docx,.txt,.pptx"
          multiple
          onChange={(event) => setFiles(Array.from(event.target.files || []))}
        />

        <label className="field-label" htmlFor="word-text">
          Or Paste Text
        </label>
        <textarea
          id="word-text"
          rows={8}
          value={textInput}
          onChange={(event) => setTextInput(event.target.value)}
        />

        <label className="field-label">Remove HSK Levels</label>
        <div className="inline-controls wrap">
          {HSK_LEVELS.map((level) => (
            <label key={level} className="checkbox-inline">
              <input
                type="checkbox"
                checked={selectedHskLevels.includes(level)}
                onChange={(event) => toggleHsk(level, event.target.checked)}
              />
              {level.toUpperCase()}
            </label>
          ))}
        </div>

        <label className="field-label" htmlFor="min-frequency">
          Minimum Frequency
        </label>
        <input
          id="min-frequency"
          type="number"
          min={1}
          value={minFrequency}
          onChange={(event) => setMinFrequency(Math.max(1, Number(event.target.value) || 1))}
        />

        {errorMessage ? (
          <p className="error-message" role="alert">
            {errorMessage}
          </p>
        ) : null}

        <button type="button" className="primary" disabled={isLoading} onClick={handleAnalyze}>
          {isLoading ? "Queuing..." : "Analyze Text"}
        </button>
      </section>

      <section className="panel-block">
        <h2>Recent Extractor Jobs</h2>
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

          {(job.status === "queued" || job.status === "running") ? (
            <button
              type="button"
              className="secondary"
              disabled={cancelingJobId === job.id}
              onClick={() => void handleCancel(job.id)}
            >
              {cancelingJobId === job.id ? "Canceling..." : "Cancel Job"}
            </button>
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

      {job?.status === "success" && result ? (
        <section className="panel-block">
          <h2>Summary</h2>
          <ul className="plain-list summary-list">
            <li>Initial words: {result.summary.initial_count}</li>
            <li>After HSK filter: {result.summary.filtered_count}</li>
            <li>Removed words: {result.summary.removed_count}</li>
            <li>Final words: {result.summary.final_count}</li>
          </ul>

          <div className="inline-controls">
            {csvDownloadUrl ? (
              <button
                type="button"
                className="secondary"
                disabled={isDownloadingCsv}
                onClick={handleDownloadCsv}
              >
                {isDownloadingCsv ? "Preparing..." : "Download Final Words CSV"}
              </button>
            ) : null}
          </div>

          <label className="field-label" htmlFor="copyable-words">
            Copyable Word List
          </label>
          <textarea id="copyable-words" rows={6} value={result.copyable_word_list} readOnly />

          {Object.keys(result.extraction_errors).length > 0 ? (
            <div>
              <h3>Extraction Warnings</h3>
              <ul className="plain-list">
                {Object.entries(result.extraction_errors).map(([fileName, message]) => (
                  <li key={fileName}>
                    {fileName}: {message}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <DataPreviewTable title="Final Words" rows={result.final_words} />
          <DataPreviewTable title="Removed Words" rows={result.removed_words} />
        </section>
      ) : null}
    </div>
  );
}
