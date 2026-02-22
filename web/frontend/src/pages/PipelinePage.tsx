import { useEffect, useMemo, useRef, useState } from "react";

import {
  addCategoryToRun,
  createPipelineRun,
  getPipelineOptions,
  getPipelineRun,
  getPipelineRunResults,
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
import { PipelineOptionsResponse, RunResultsResponse, RunSummary } from "../types/pipeline";
import { subscribeToPipelineRun } from "../ws/pipeline";

const PAGE_SIZE = 25;

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

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [categoryUpdating, setCategoryUpdating] = useState(false);
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

    const isTerminal = run.status === "success" || run.status === "error";
    if (isTerminal) {
      return;
    }

    const timer = window.setInterval(() => {
      void getPipelineRun(run.id)
        .then((freshRun) => {
          setRun(freshRun);
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
      setResults(null);
      setResultsPage(1);
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
      await fetchResults(run.id, resultsPage, resultsSearch);
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setCategoryUpdating(false);
    }
  };

  return (
    <div className="workspace-page">
      <header className="page-header">
        <h1>Ankineitor Pipeline Workspace</h1>
        <p>React Flow visualization with live pipeline execution events via Django Channels.</p>
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
            <h2>Execution Graph</h2>
            <p className="muted">
              Run ID: {run?.id ?? "not started"}
              {run?.status ? ` | Status: ${run.status}` : ""}
            </p>
          </div>
          <PipelineFlow
            transformNames={run?.ordered_transform_names ?? []}
            nodeStatuses={graphState.nodeStatuses}
            nodeDurations={graphState.nodeDurations}
            activeNode={graphState.activeNode}
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
        categoryUpdating={categoryUpdating}
      />

      <footer className="page-footer">
        <span>
          Next page hint: {parsePageFromUrl(results?.next) ?? "none"} | Previous page hint:{" "}
          {parsePageFromUrl(results?.previous) ?? "none"}
        </span>
      </footer>
    </div>
  );
}
