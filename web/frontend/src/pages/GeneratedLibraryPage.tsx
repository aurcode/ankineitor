import { useEffect, useMemo, useState } from "react";

import {
  getGeneratedRow,
  listGeneratedRows,
  rerunGeneratedRowProcess,
  updateGeneratedRow,
  uploadGeneratedRowImage,
} from "../api/pipeline";
import { GeneratedRowDetail, GeneratedRowRerunProcess, GeneratedRowSummary } from "../types/pipeline";

function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "n/a";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function asText(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

const RERUN_ACTIONS: Array<{ process: GeneratedRowRerunProcess; label: string }> = [
  { process: "full", label: "Rerun Full" },
  { process: "meaning_sentences", label: "Rerun Meanings + Sentences" },
  { process: "audio_word", label: "Rerun Word Audio" },
  { process: "audio_sentences", label: "Rerun Sentence Audio" },
  { process: "image_prompt", label: "Rerun Image Prompt" },
  { process: "image_renderer", label: "Rerun Image Render" },
];

export function GeneratedLibraryPage() {
  const [rows, setRows] = useState<GeneratedRowSummary[]>([]);
  const [selectedRow, setSelectedRow] = useState<GeneratedRowDetail | null>(null);
  const [search, setSearch] = useState("");
  const [profileFilter, setProfileFilter] = useState("");
  const [runIdFilter, setRunIdFilter] = useState("");
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [nextUrl, setNextUrl] = useState<string | null>(null);
  const [previousUrl, setPreviousUrl] = useState<string | null>(null);
  const [isLoadingRows, setIsLoadingRows] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isRerunning, setIsRerunning] = useState(false);
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const [customImageFile, setCustomImageFile] = useState<File | null>(null);
  const [actionMessage, setActionMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const [editMeaningEnglish, setEditMeaningEnglish] = useState("");
  const [editMeaningSpanish, setEditMeaningSpanish] = useState("");
  const [editSentence1, setEditSentence1] = useState("");
  const [editSentence2, setEditSentence2] = useState("");
  const [editSentence3, setEditSentence3] = useState("");
  const [editVisualDescription, setEditVisualDescription] = useState("");
  const [editMasterImagePrompt, setEditMasterImagePrompt] = useState("");

  const totalPages = useMemo(() => {
    if (count <= 0) {
      return 1;
    }
    return Math.max(1, Math.ceil(count / 25));
  }, [count]);

  useEffect(() => {
    if (!selectedRow) {
      return;
    }
    const rowData = selectedRow.row_data || {};
    setEditMeaningEnglish(asText(rowData.meaning_english));
    setEditMeaningSpanish(asText(rowData.meaning_spanish));
    setEditSentence1(asText(rowData.sentence_1));
    setEditSentence2(asText(rowData.sentence_2));
    setEditSentence3(asText(rowData.sentence_3));
    setEditVisualDescription(asText(rowData.visual_description));
    setEditMasterImagePrompt(asText(rowData.master_image_prompt));
  }, [selectedRow?.row_id]);

  const loadRows = async (pageToLoad: number, preserveSelectionId?: number) => {
    setIsLoadingRows(true);
    setErrorMessage("");
    try {
      const payload = await listGeneratedRows({
        search: search.trim() || undefined,
        profileId: profileFilter.trim() || undefined,
        runId: runIdFilter.trim() || undefined,
        page: pageToLoad,
        pageSize: 25,
      });
      setRows(payload.results);
      setCount(payload.count);
      setNextUrl(payload.next);
      setPreviousUrl(payload.previous);
      setPage(pageToLoad);

      const keepId = preserveSelectionId ?? selectedRow?.row_id;
      if (keepId) {
        const stillPresent = payload.results.some((row) => row.row_id === keepId);
        if (!stillPresent) {
          setSelectedRow(null);
        }
      }
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsLoadingRows(false);
    }
  };

  const loadRowDetail = async (rowId: number) => {
    setIsLoadingDetail(true);
    setErrorMessage("");
    try {
      const payload = await getGeneratedRow(rowId);
      setSelectedRow(payload.row);
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsLoadingDetail(false);
    }
  };

  useEffect(() => {
    void loadRows(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleApplyFilters = async () => {
    await loadRows(1);
  };

  const handleSaveEdits = async () => {
    if (!selectedRow) {
      return;
    }
    setIsSaving(true);
    setActionMessage("");
    setErrorMessage("");
    try {
      const payload = await updateGeneratedRow({
        rowId: selectedRow.row_id,
        updates: {
          meaning_english: editMeaningEnglish,
          meaning_spanish: editMeaningSpanish,
          sentence_1: editSentence1,
          sentence_2: editSentence2,
          sentence_3: editSentence3,
          visual_description: editVisualDescription,
          master_image_prompt: editMasterImagePrompt,
        },
      });
      setSelectedRow(payload.row);
      setActionMessage("Row updated.");
      await loadRows(page, payload.row.row_id);
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsSaving(false);
    }
  };

  const handleRerun = async (process: GeneratedRowRerunProcess) => {
    if (!selectedRow) {
      return;
    }
    setIsRerunning(true);
    setActionMessage("");
    setErrorMessage("");
    try {
      const payload = await rerunGeneratedRowProcess({
        rowId: selectedRow.row_id,
        process,
      });
      setSelectedRow(payload.row);
      setActionMessage(`Process rerun complete: ${process}.`);
      await loadRows(page, payload.row.row_id);
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsRerunning(false);
    }
  };

  const handleUploadCustomImage = async () => {
    if (!selectedRow || !customImageFile) {
      return;
    }
    setIsUploadingImage(true);
    setActionMessage("");
    setErrorMessage("");
    try {
      const payload = await uploadGeneratedRowImage({
        rowId: selectedRow.row_id,
        imageFile: customImageFile,
      });
      setSelectedRow(payload.row);
      setCustomImageFile(null);
      setActionMessage("Custom image uploaded.");
      await loadRows(page, payload.row.row_id);
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsUploadingImage(false);
    }
  };

  return (
    <div className="workspace-page single-column">
      <header className="page-header">
        <h1>Generated Library</h1>
        <p>Browse all generated DB rows, edit fields, rerun specific processes, and upload custom images.</p>
      </header>

      <section className="panel-block">
        <div className="inline-controls wrap">
          <input
            placeholder="Search word..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <input
            placeholder="Filter profile_id..."
            value={profileFilter}
            onChange={(event) => setProfileFilter(event.target.value)}
          />
          <input
            placeholder="Filter run_id..."
            value={runIdFilter}
            onChange={(event) => setRunIdFilter(event.target.value)}
          />
          <button type="button" className="secondary" onClick={handleApplyFilters} disabled={isLoadingRows}>
            {isLoadingRows ? "Loading..." : "Apply Filters"}
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              void loadRows(page);
            }}
            disabled={isLoadingRows}
          >
            Refresh
          </button>
        </div>
        <p className="muted">
          Rows: {count} | Page {page}/{totalPages}
        </p>

        <div className="table-shell">
          <table>
            <thead>
              <tr>
                <th scope="col">Word</th>
                <th scope="col">Profile</th>
                <th scope="col">Run</th>
                <th scope="col">Idx</th>
                <th scope="col">Status</th>
                <th scope="col">Created</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.row_id}>
                  <td>{row.word}</td>
                  <td>{row.profile_id}</td>
                  <td>
                    <code>{row.run_id}</code>
                  </td>
                  <td>{row.row_index}</td>
                  <td>{row.run_status}</td>
                  <td>{formatTimestamp(row.created_at)}</td>
                  <td>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => {
                        void loadRowDetail(row.row_id);
                      }}
                    >
                      Open
                    </button>
                  </td>
                </tr>
              ))}
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="muted">
                    No generated rows found.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="inline-controls wrap">
          <button
            type="button"
            className="secondary"
            disabled={!previousUrl || isLoadingRows}
            onClick={() => {
              void loadRows(Math.max(1, page - 1));
            }}
          >
            Previous Page
          </button>
          <button
            type="button"
            className="secondary"
            disabled={!nextUrl || isLoadingRows}
            onClick={() => {
              void loadRows(page + 1);
            }}
          >
            Next Page
          </button>
        </div>
      </section>

      {errorMessage ? (
        <p className="error-message" role="alert">
          {errorMessage}
        </p>
      ) : null}
      {actionMessage ? (
        <p className="muted status-message" aria-live="polite">
          {actionMessage}
        </p>
      ) : null}

      {selectedRow ? (
        <section className="panel-block">
          <h2>
            Row #{selectedRow.row_id} | {selectedRow.word}
          </h2>
          <p className="muted">
            Run: <code>{selectedRow.run_id}</code> | Status: {selectedRow.run_status} | Profile:{" "}
            {selectedRow.profile_id}
          </p>

          {isLoadingDetail ? <p className="muted">Loading row detail...</p> : null}

          <div className="card-front">
            <h3>{selectedRow.card.front.word || "(no word)"}</h3>
            <p>{selectedRow.card.front.pronunciation}</p>
            {selectedRow.card.front.audio ? <audio controls src={selectedRow.card.front.audio} /> : null}
          </div>

          <div className="card-back">
            <h3>Meanings</h3>
            <p>{selectedRow.card.back.meaning_english}</p>
            <p>{selectedRow.card.back.meaning_spanish}</p>

            <h3>Sentences</h3>
            {selectedRow.card.back.sentences.length === 0 ? (
              <p className="muted">No sentence data.</p>
            ) : (
              selectedRow.card.back.sentences.map((sentence) => (
                <div key={`row-${selectedRow.row_id}-sentence-${sentence.index}`} className="sentence-item">
                  <p>{sentence.sentence}</p>
                  <p className="muted">{sentence.translation_english}</p>
                  <p className="muted">{sentence.translation_spanish}</p>
                  {sentence.audio ? <audio controls src={sentence.audio} /> : null}
                </div>
              ))
            )}

            {selectedRow.card.back.image.picture ? (
              <div>
                <h3>Image</h3>
                <img
                  src={selectedRow.card.back.image.picture_url || selectedRow.card.back.image.picture}
                  alt="generated visual"
                  className="review-image"
                />
                <p className="muted">
                  Render status: {selectedRow.card.back.image.image_render_status || "unknown"}
                </p>
              </div>
            ) : null}
          </div>

          <div className="panel-card">
            <h3>Edit Generated Content</h3>
            <label className="field-label" htmlFor="generated-edit-meaning-english">
              Meaning (English)
            </label>
            <textarea
              id="generated-edit-meaning-english"
              rows={2}
              value={editMeaningEnglish}
              onChange={(event) => setEditMeaningEnglish(event.target.value)}
            />

            <label className="field-label" htmlFor="generated-edit-meaning-spanish">
              Meaning (Spanish)
            </label>
            <textarea
              id="generated-edit-meaning-spanish"
              rows={2}
              value={editMeaningSpanish}
              onChange={(event) => setEditMeaningSpanish(event.target.value)}
            />

            <label className="field-label" htmlFor="generated-edit-sentence-1">
              Sentence 1
            </label>
            <textarea
              id="generated-edit-sentence-1"
              rows={2}
              value={editSentence1}
              onChange={(event) => setEditSentence1(event.target.value)}
            />

            <label className="field-label" htmlFor="generated-edit-sentence-2">
              Sentence 2
            </label>
            <textarea
              id="generated-edit-sentence-2"
              rows={2}
              value={editSentence2}
              onChange={(event) => setEditSentence2(event.target.value)}
            />

            <label className="field-label" htmlFor="generated-edit-sentence-3">
              Sentence 3
            </label>
            <textarea
              id="generated-edit-sentence-3"
              rows={2}
              value={editSentence3}
              onChange={(event) => setEditSentence3(event.target.value)}
            />

            <label className="field-label" htmlFor="generated-edit-visual-description">
              Visual Description
            </label>
            <textarea
              id="generated-edit-visual-description"
              rows={2}
              value={editVisualDescription}
              onChange={(event) => setEditVisualDescription(event.target.value)}
            />

            <label className="field-label" htmlFor="generated-edit-master-image-prompt">
              Master Image Prompt
            </label>
            <textarea
              id="generated-edit-master-image-prompt"
              rows={3}
              value={editMasterImagePrompt}
              onChange={(event) => setEditMasterImagePrompt(event.target.value)}
            />

            <div className="inline-controls wrap">
              <button type="button" className="primary" onClick={handleSaveEdits} disabled={isSaving}>
                {isSaving ? "Saving..." : "Save Edits"}
              </button>
            </div>
          </div>

          <div className="panel-card">
            <h3>Rerun Specific Process</h3>
            <div className="inline-controls wrap">
              {RERUN_ACTIONS.map((action) => (
                <button
                  key={action.process}
                  type="button"
                  className="secondary"
                  disabled={isRerunning}
                  onClick={() => {
                    void handleRerun(action.process);
                  }}
                >
                  {isRerunning ? "Rerunning..." : action.label}
                </button>
              ))}
            </div>
          </div>

          <div className="panel-card">
            <h3>Custom Image Override</h3>
            <input
              type="file"
              accept=".png,.jpg,.jpeg,.webp,.gif"
              onChange={(event) => setCustomImageFile(event.target.files?.[0] ?? null)}
            />
            <div className="inline-controls wrap">
              <button
                type="button"
                className="secondary"
                onClick={handleUploadCustomImage}
                disabled={!customImageFile || isUploadingImage}
              >
                {isUploadingImage ? "Uploading..." : "Upload Custom Image"}
              </button>
              <span className="muted small">{customImageFile?.name || "No file selected"}</span>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
