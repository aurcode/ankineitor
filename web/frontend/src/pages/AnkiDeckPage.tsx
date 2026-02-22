import { useEffect, useState } from "react";

import { generateAnkiDeck, getAnkiPresets } from "../api/pipeline";
import { AnkiConfigPayload, AnkiPresetsResponse, GenerateAnkiDeckResponse } from "../types/pipeline";

function prettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function AnkiDeckPage() {
  const [presets, setPresets] = useState<AnkiPresetsResponse | null>(null);
  const [presetKey, setPresetKey] = useState<"default" | "chinese_pipeline">("default");
  const [configJson, setConfigJson] = useState("");
  const [deckName, setDeckName] = useState("My Anki Deck");
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [result, setResult] = useState<GenerateAnkiDeckResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let active = true;

    const loadPresets = async () => {
      try {
        const payload = await getAnkiPresets();
        if (!active) {
          return;
        }
        setPresets(payload);
        setConfigJson(prettyJson(payload.default));
      } catch (error) {
        if (active) {
          setErrorMessage(String(error));
        }
      }
    };

    void loadPresets();
    return () => {
      active = false;
    };
  }, []);

  const handlePresetChange = (value: "default" | "chinese_pipeline") => {
    setPresetKey(value);
    if (!presets) {
      return;
    }
    const config = value === "chinese_pipeline" ? presets.chinese_pipeline : presets.default;
    setConfigJson(prettyJson(config));
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
    setResult(null);

    try {
      const payload = await generateAnkiDeck({
        csvFile,
        deckName,
        config: parsedConfig,
      });
      setResult(payload);
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="workspace-page single-column">
      <header className="page-header">
        <h1>Anki Deck Generator</h1>
        <p>Generate `.apkg` decks from CSV using the existing Python deck generator and templates.</p>
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

        {errorMessage ? <p className="error-message">{errorMessage}</p> : null}

        <button type="button" className="primary" disabled={isSubmitting} onClick={handleGenerate}>
          {isSubmitting ? "Generating..." : "Generate Deck"}
        </button>

        {result ? (
          <div className="result-box">
            <p>
              Deck generated: <strong>{result.deck_name}</strong>
            </p>
            <p className="muted">Source: {result.source_csv_name}</p>
            <a className="secondary" href={result.download_url} target="_blank" rel="noreferrer">
              Download .apkg
            </a>
          </div>
        ) : null}
      </section>
    </div>
  );
}
