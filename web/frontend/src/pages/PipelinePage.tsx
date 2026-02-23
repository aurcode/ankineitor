import { useEffect, useMemo, useRef, useState } from "react";

import {
  addCategoryToRun,
  createPipelineRun,
  downloadAuthenticatedFile,
  getPipelineOptions,
  getPipelineRun,
  getPipelineRunResults,
  listPipelineRuns,
  rerunPipelineRunBlock,
} from "../api/pipeline";
import { PipelineFlow } from "../components/PipelineFlow";
import { PipelineRunForm } from "../components/PipelineRunForm";
import { ResultsTable } from "../components/ResultsTable";
import { RunSidePanel } from "../components/RunSidePanel";
import {
  applyPipelineEvent,
  GraphExecutionState,
  initializeGraphState,
} from "../state/pipelineFlowReducer";
import {
  PipelineOptionsResponse,
  RunResultsResponse,
  RunStatus,
  RunSummary,
} from "../types/pipeline";
import { subscribeToPipelineRun } from "../ws/pipeline";

const PAGE_SIZE = 25;
const HISTORY_LIMIT = 40;

type HistoryStatusFilter = "all" | RunStatus;

const HISTORY_STATUS_OPTIONS: Array<{ value: HistoryStatusFilter; label: string }> = [
  { value: "all", label: "All statuses" },
  { value: "success", label: "Success" },
  { value: "error", label: "Error" },
  { value: "paused", label: "Paused" },
  { value: "canceled", label: "Canceled" },
  { value: "running", label: "Running" },
  { value: "queued", label: "Queued" },
  { value: "retrying", label: "Retrying" },
];

function parseWords(input: string): string[] {
  return input
    .split("\n")
    .map((word) => word.trim())
    .filter((word) => word.length > 0);
}

function parsePageFromUrl(url: string | null | undefined): number | null {
  if (!url) {
    return null;
  }
  try {
    const parsed = new URL(url);
    const page = parsed.searchParams.get("page");
    if (!page) {
      return null;
    }
    const parsedNumber = Number(page);
    if (Number.isNaN(parsedNumber) || parsedNumber <= 0) {
      return null;
    }
    return parsedNumber;
  } catch {
    return null;
  }
}

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

function toTime(value: string | null | undefined): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function upsertRunHistory(previous: RunSummary[], incoming: RunSummary): RunSummary[] {
  const filtered = previous.filter((run) => run.id !== incoming.id);
  const next = [incoming, ...filtered];
  next.sort((left, right) => toTime(right.created_at) - toTime(left.created_at));
  return next;
}

export function PipelinePage() {
  const [options, setOptions] = useState<PipelineOptionsResponse | null>(null);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [selectedTransforms, setSelectedTransforms] = useState<string[]>([]);
  const [wordsInput, setWordsInput] = useState("你好\n谢谢\n苹果");

  const [run, setRun] = useState<RunSummary | null>(null);
  const [graphState, setGraphState] = useState<GraphExecutionState>(initializeGraphState([]));

  const [results, setResults] = useState<RunResultsResponse | null>(null);
  const [resultsPage, setResultsPage] = useState(1);
  const [resultsSearch, setResultsSearch] = useState("");
  const [resultsLoading, setResultsLoading] = useState(false);
  const [runHistory, setRunHistory] = useState<RunSummary[]>([]);
  const [historyStatus, setHistoryStatus] = useState<HistoryStatusFilter>("all");
  const [historyLoading, setHistoryLoading] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [categoryUpdating, setCategoryUpdating] = useState(false);
  const [csvDownloading, setCsvDownloading] = useState(false);
  const [rerunBlockPending, setRerunBlockPending] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  const wsCleanupRef = useRef<(() => void) | null>(null);
  const transformNamesRef = useRef<string[]>([]);

  const selectedProfile = useMemo(
    () => options?.profiles.find((profile) => profile.profile_id === selectedProfileId) ?? null,
    [options, selectedProfileId],
  );

  const totalPages = useMemo(() => {
    if (!results) {
      return 1;
    }
    return Math.max(1, Math.ceil(results.count / PAGE_SIZE));
  }, [results]);

  const effectiveCounters = useMemo(
    () => ({ ...(run?.counters || {}), ...(graphState.counters || {}) }),
    [graphState.counters, run?.counters],
  );

  const fetchResults = async (runId: string, page: number, search: string): Promise<void> => {
    setResultsLoading(true);
    try {
      const payload = await getPipelineRunResults(runId, {
        page,
        pageSize: PAGE_SIZE,
        search,
      });
      setResults(payload);
      setResultsPage(page);
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setResultsLoading(false);
    }
  };

  const fetchRunHistory = async (statusFilter: HistoryStatusFilter): Promise<void> => {
    setHistoryLoading(true);
    try {
      const payload = await listPipelineRuns({
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: HISTORY_LIMIT,
      });
      setRunHistory(Array.isArray(payload.runs) ? payload.runs : []);
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    let active = true;

    const loadOptions = async () => {
      try {
        const payload = await getPipelineOptions();
        if (!active) {
          return;
        }
        setOptions(payload);

        const defaultProfileId = payload.default_profile_id;
        const defaultProfile =
          payload.profiles.find((profile) => profile.profile_id === defaultProfileId) ||
          payload.profiles[0] ||
          null;
        if (defaultProfile) {
          setSelectedProfileId(defaultProfile.profile_id);
          setSelectedTransforms(defaultProfile.default_optional_transform_names);
        }
      } catch (error) {
        if (active) {
          setErrorMessage(String(error));
        }
      }
    };

    void loadOptions();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    void fetchRunHistory(historyStatus);
  }, [historyStatus]);

  useEffect(() => {
    if (!selectedProfile) {
      return;
    }

    setSelectedTransforms((previous) => {
      const available = new Set(selectedProfile.available_transform_names);
      const filtered = previous.filter((transform) => available.has(transform));
      if (filtered.length > 0) {
        return filtered;
      }
      return selectedProfile.default_optional_transform_names;
    });
  }, [selectedProfile]);

  useEffect(() => {
    transformNamesRef.current = run?.ordered_transform_names ?? [];
  }, [run?.ordered_transform_names]);

  useEffect(() => {
    if (!run) {
      return;
    }

    wsCleanupRef.current?.();
    wsCleanupRef.current = subscribeToPipelineRun(run.id, {
      onEvent: (event) => {
        setGraphState((previous) =>
          applyPipelineEvent(previous, event, transformNamesRef.current),
        );
      },
      onError: (error) => {
        setErrorMessage(error);
      },
    });

    return () => {
      wsCleanupRef.current?.();
      wsCleanupRef.current = null;
    };
  }, [run?.id]);

  useEffect(() => {
    if (!run) {
      return;
    }

    const isTerminal =
      run.status === "success" ||
      run.status === "error" ||
      run.status === "paused" ||
      run.status === "canceled";
    if (isTerminal) {
      return;
    }

    const timer = window.setInterval(() => {
      void getPipelineRun(run.id)
        .then((freshRun) => {
          setRun(freshRun);
          setRunHistory((previous) => upsertRunHistory(previous, freshRun));
        })
        .catch((error) => {
          setErrorMessage(String(error));
        });
    }, 2000);

    return () => {
      window.clearInterval(timer);
    };
  }, [run?.id, run?.status]);

  useEffect(() => {
    if (!run || run.status !== "success") {
      return;
    }

    void fetchResults(run.id, 1, resultsSearch);
  }, [run?.id, run?.status]);

  const handleSubmit = async () => {
    if (!selectedProfile) {
      setErrorMessage("Profile options are not loaded.");
      return;
    }

    const words = parseWords(wordsInput);
    if (words.length === 0) {
      setErrorMessage("Please provide at least one word.");
      return;
    }

    setIsSubmitting(true);
    setErrorMessage("");

    try {
      const createdRun = await createPipelineRun({
        profile_id: selectedProfile.profile_id,
        transform_names: selectedTransforms,
        words,
      });

      setRun(createdRun);
      setRunHistory((previous) => upsertRunHistory(previous, createdRun));
      setResults(null);
      setResultsPage(1);
      setResultsSearch("");
      setGraphState(initializeGraphState(createdRun.ordered_transform_names));
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSearchSubmit = () => {
    if (!run) {
      return;
    }
    void fetchResults(run.id, 1, resultsSearch);
  };

  const handlePageChange = (page: number) => {
    if (!run) {
      return;
    }
    void fetchResults(run.id, page, resultsSearch);
  };

  const handleAddCategory = async (category: string) => {
    if (!run) {
      return;
    }

    setCategoryUpdating(true);
    setErrorMessage("");
    try {
      const response = await addCategoryToRun(run.id, { category });
      setRun(response.run);
      setRunHistory((previous) => upsertRunHistory(previous, response.run));
      await fetchResults(run.id, resultsPage, resultsSearch);
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setCategoryUpdating(false);
    }
  };

  const handleDownloadCsv = async () => {
    const csvUrl = results?.csv_url;
    if (!csvUrl || !run) {
      return;
    }

    setCsvDownloading(true);
    setErrorMessage("");
    try {
      await downloadAuthenticatedFile({
        url: csvUrl,
        fallbackFileName: run.csv_download_name || `pipeline_run_${run.id}.csv`,
      });
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setCsvDownloading(false);
    }
  };

  const handleRerunBlock = async (transformName: string) => {
    if (!run) {
      return;
    }

    setRerunBlockPending(transformName);
    setErrorMessage("");
    try {
      const rerun = await rerunPipelineRunBlock({
        runId: run.id,
        transformName,
      });
      setRun(rerun);
      setRunHistory((previous) => upsertRunHistory(previous, rerun));
      setResults(null);
      setResultsPage(1);
      setResultsSearch("");
      setGraphState(initializeGraphState(rerun.ordered_transform_names));
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setRerunBlockPending(null);
    }
  };

  const handleSelectHistoryRun = async (runId: string) => {
    setErrorMessage("");
    try {
      const selectedRun = await getPipelineRun(runId);
      setRun(selectedRun);
      setRunHistory((previous) => upsertRunHistory(previous, selectedRun));
      setGraphState(initializeGraphState(selectedRun.ordered_transform_names));
      setResults(null);
      setResultsPage(1);
      setResultsSearch("");
    } catch (error) {
      setErrorMessage(String(error));
    }
  };

  return (
    <div className="workspace-page">
      <header className="page-header">
        <h1>Pipeline</h1>
      </header>

      <main className="page-grid">
        <PipelineRunForm
          profiles={options?.profiles ?? []}
          selectedProfileId={selectedProfileId}
          selectedTransforms={selectedTransforms}
          wordsInput={wordsInput}
          isSubmitting={isSubmitting}
          errorMessage={errorMessage}
          onProfileChange={setSelectedProfileId}
          onTransformsChange={setSelectedTransforms}
          onWordsInputChange={setWordsInput}
          onSubmit={handleSubmit}
        />

        <section className="flow-section">
          <div className="flow-header">
            <h2>Execution</h2>
            <div className="inline-controls wrap flow-status-line">
              <span className="status-chip" data-status={run?.status ?? "idle"}>
                {run?.status ?? "idle"}
              </span>
              <span className="flow-run-id">
                <code>{run?.id ?? "not-started"}</code>
              </span>
            </div>
          </div>
          <PipelineFlow
            transformNames={run?.ordered_transform_names ?? []}
            nodeStatuses={graphState.nodeStatuses}
            nodeDurations={graphState.nodeDurations}
            nodeRuntime={graphState.nodeRuntime}
            activeNodes={graphState.activeNodes}
            onRerunNode={run ? handleRerunBlock : undefined}
            rerunPendingNode={rerunBlockPending}
            disableRerun={!run || Boolean(rerunBlockPending)}
          />
        </section>

        <RunSidePanel
          run={run}
          progressRatio={graphState.progressRatio}
          statusText={graphState.statusText}
          counters={effectiveCounters}
          events={graphState.eventLog}
        />
      </main>

      <ResultsTable
        runId={run?.id ?? null}
        results={results}
        isLoading={resultsLoading}
        currentPage={resultsPage}
        totalPages={totalPages}
        search={resultsSearch}
        onSearchChange={setResultsSearch}
        onSearchSubmit={handleSearchSubmit}
        onPageChange={handlePageChange}
        onAddCategory={handleAddCategory}
        onDownloadCsv={handleDownloadCsv}
        categoryUpdating={categoryUpdating}
        csvDownloading={csvDownloading}
      />

      <footer className="page-footer">
        <span>
          Next page hint: {parsePageFromUrl(results?.next) ?? "none"} | Previous page hint:{" "}
          {parsePageFromUrl(results?.previous) ?? "none"}
        </span>
      </footer>

      <details className="panel-block history-toggle">
        <summary className="history-toggle-summary">
          <span>Prediction History</span>
          <span className="muted small">
            {runHistory.length} run{runHistory.length === 1 ? "" : "s"}
          </span>
        </summary>
        <div className="history-toggle-body">
          <div className="inline-controls wrap">
            <label className="field-label" htmlFor="history-status-filter">
              Status
            </label>
            <select
              id="history-status-filter"
              value={historyStatus}
              onChange={(event) => setHistoryStatus(event.target.value as HistoryStatusFilter)}
            >
              {HISTORY_STATUS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                void fetchRunHistory(historyStatus);
              }}
              disabled={historyLoading}
            >
              {historyLoading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          {runHistory.length === 0 ? (
            <p className="muted">No past runs found.</p>
          ) : (
            <div className="history-list">
              {runHistory.map((historyRun) => (
                <button
                  key={historyRun.id}
                  type="button"
                  className={
                    run?.id === historyRun.id ? "history-item active secondary" : "history-item secondary"
                  }
                  onClick={() => {
                    void handleSelectHistoryRun(historyRun.id);
                  }}
                >
                  <span className="history-item-id">{historyRun.id}</span>
                  <span className="history-item-meta">
                    {historyRun.status} | {historyRun.profile_id} | words {historyRun.total_input_words}
                  </span>
                  <span className="history-item-meta">
                    created {formatTimestamp(historyRun.created_at)} | completed{" "}
                    {formatTimestamp(historyRun.completed_at)}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </details>
    </div>
  );
}
