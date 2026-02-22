import { useMemo, useState } from "react";

import { analyzeWordExtractor } from "../api/pipeline";
import { WordExtractorResponse } from "../types/pipeline";

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
                  <th key={column}>{column}</th>
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

export function WordExtractorPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [textInput, setTextInput] = useState("");
  const [selectedHskLevels, setSelectedHskLevels] = useState<string[]>([]);
  const [minFrequency, setMinFrequency] = useState(2);
  const [result, setResult] = useState<WordExtractorResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

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

  const handleAnalyze = async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const payload = await analyzeWordExtractor({
        files,
        textInput,
        selectedHskLevels,
        minFrequency,
      });
      setResult(payload);
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="workspace-page single-column">
      <header className="page-header">
        <h1>Word Extractor</h1>
        <p>Extract Chinese words from documents or pasted text, then filter by HSK level and frequency.</p>
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

        {errorMessage ? <p className="error-message">{errorMessage}</p> : null}

        <button type="button" className="primary" disabled={isLoading} onClick={handleAnalyze}>
          {isLoading ? "Analyzing..." : "Analyze Text"}
        </button>
      </section>

      {result ? (
        <section className="panel-block">
          <h2>Summary</h2>
          <ul className="plain-list">
            <li>Initial words: {result.summary.initial_count}</li>
            <li>After HSK filter: {result.summary.filtered_count}</li>
            <li>Removed words: {result.summary.removed_count}</li>
            <li>Final words: {result.summary.final_count}</li>
          </ul>

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
