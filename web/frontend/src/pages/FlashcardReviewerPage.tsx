import { useEffect, useMemo, useRef, useState } from "react";

import {
  createFlashcardDatasetFromSaved,
  createFlashcardDatasetFromUpload,
  getFlashcardCard,
  getFlashcardSavedFiles,
  getFlashcardSavedProfiles,
  rerunFlashcardCardGeneration,
  updateFlashcardCard,
  uploadFlashcardCardImage,
} from "../api/pipeline";
import {
  FlashcardCardResponse,
  FlashcardDatasetSummary,
  FlashcardSavedFile,
} from "../types/pipeline";

const REVIEW_BATCH_SIZE = 5;
const REVIEW_BATCH_PRELOAD_PAGES = 2;

export function FlashcardReviewerPage() {
  const [sourceMode, setSourceMode] = useState<"saved" | "upload">("saved");
  const [profiles, setProfiles] = useState<string[]>([]);
  const [selectedProfile, setSelectedProfile] = useState("");
  const [savedFiles, setSavedFiles] = useState<FlashcardSavedFile[]>([]);
  const [selectedFileName, setSelectedFileName] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  const [summary, setSummary] = useState<FlashcardDatasetSummary | null>(null);
  const [currentCard, setCurrentCard] = useState<FlashcardCardResponse | null>(null);
  const [profileFilter, setProfileFilter] = useState("All profiles");
  const [isEditMode, setIsEditMode] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSavingEdits, setIsSavingEdits] = useState(false);
  const [isRerunning, setIsRerunning] = useState(false);
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const [customImageFile, setCustomImageFile] = useState<File | null>(null);
  const [editMeaningEnglish, setEditMeaningEnglish] = useState("");
  const [editMeaningSpanish, setEditMeaningSpanish] = useState("");
  const [editMasterImagePrompt, setEditMasterImagePrompt] = useState("");
  const [editVisualDescription, setEditVisualDescription] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const cardCacheRef = useRef<Map<string, FlashcardCardResponse>>(new Map());
  const inFlightCardRequestsRef = useRef<Set<string>>(new Set());
  const hasAutoLoadedSavedDatasetRef = useRef(false);

  useEffect(() => {
    let active = true;

    const loadProfiles = async () => {
      try {
        const payload = await getFlashcardSavedProfiles();
        if (!active) {
          return;
        }
        setProfiles(payload.profiles);
        if (payload.profiles.length > 0) {
          setSelectedProfile(payload.profiles[0]);
        }
      } catch (error) {
        if (active) {
          setErrorMessage(String(error));
        }
      }
    };

    void loadProfiles();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedProfile || sourceMode !== "saved") {
      return;
    }

    let active = true;

    const loadFiles = async () => {
      try {
        const payload = await getFlashcardSavedFiles(selectedProfile);
        if (!active) {
          return;
        }
        setSavedFiles(payload.files);
        setSelectedFileName(payload.files[0]?.file_name ?? "");
      } catch (error) {
        if (active) {
          setErrorMessage(String(error));
        }
      }
    };

    void loadFiles();
    return () => {
      active = false;
    };
  }, [selectedProfile, sourceMode]);

  const availableFilters = useMemo(() => {
    if (!summary) {
      return ["All profiles"];
    }
    return ["All profiles", ...summary.available_profiles];
  }, [summary]);
  const hasSavedProfiles = profiles.length > 0;
  const hasSavedFiles = savedFiles.length > 0;
  const currentProfileFilter = profileFilter === "All profiles" ? "" : profileFilter;

  const resolveFilterValue = (selectedFilter: string): string =>
    selectedFilter === "All profiles" ? "" : selectedFilter;

  const buildCardCacheKey = (datasetId: string, index: number, filterValue: string): string =>
    `${datasetId}|${filterValue}|${index}`;

  useEffect(() => {
    if (!currentCard) {
      return;
    }
    setEditMeaningEnglish(currentCard.back.meaning_english || "");
    setEditMeaningSpanish(currentCard.back.meaning_spanish || "");
    setEditMasterImagePrompt(currentCard.back.image.master_image_prompt || "");
    setEditVisualDescription(currentCard.back.image.visual_description || "");
  }, [currentCard?.index, currentCard?.raw_row]);

  const prefetchCard = async (
    datasetId: string,
    index: number,
    filterValue: string,
  ): Promise<void> => {
    const safeIndex = Math.max(0, index);
    const requestKey = buildCardCacheKey(datasetId, safeIndex, filterValue);
    if (cardCacheRef.current.has(requestKey) || inFlightCardRequestsRef.current.has(requestKey)) {
      return;
    }

    inFlightCardRequestsRef.current.add(requestKey);
    try {
      const payload = await getFlashcardCard({
        datasetId,
        index: safeIndex,
        profileFilter: filterValue,
      });
      const resolvedKey = buildCardCacheKey(datasetId, payload.index, filterValue);
      cardCacheRef.current.set(requestKey, payload);
      cardCacheRef.current.set(resolvedKey, payload);
    } catch {
      // Prefetch errors should not block main reviewer flow.
    } finally {
      inFlightCardRequestsRef.current.delete(requestKey);
    }
  };

  const prefetchUpcomingBatches = (
    datasetId: string,
    currentIndex: number,
    totalCards: number,
    filterValue: string,
  ): void => {
    for (let offset = 1; offset <= REVIEW_BATCH_PRELOAD_PAGES; offset += 1) {
      const nextIndex = currentIndex + offset * REVIEW_BATCH_SIZE;
      if (nextIndex >= totalCards) {
        break;
      }
      void prefetchCard(datasetId, nextIndex, filterValue);
    }
  };

  const setCurrentCardWithCache = (
    payload: FlashcardCardResponse,
    datasetId: string,
    filterValue: string,
  ): void => {
    const resolvedKey = buildCardCacheKey(datasetId, payload.index, filterValue);
    cardCacheRef.current.set(resolvedKey, payload);
    setCurrentCard(payload);
    prefetchUpcomingBatches(datasetId, payload.index, payload.total, filterValue);
  };

  const loadCard = async (index: number, selectedFilter: string): Promise<void> => {
    if (!summary) {
      return;
    }

    const datasetId = summary.dataset_id;
    const filterValue = resolveFilterValue(selectedFilter);
    const safeIndex = Math.max(0, index);
    const cacheKey = buildCardCacheKey(datasetId, safeIndex, filterValue);
    const cachedCard = cardCacheRef.current.get(cacheKey);
    if (cachedCard) {
      setCurrentCardWithCache(cachedCard, datasetId, filterValue);
      return;
    }

    const payload = await getFlashcardCard({
      datasetId,
      index: safeIndex,
      profileFilter: filterValue,
    });
    setCurrentCardWithCache(payload, datasetId, filterValue);
  };

  const currentBatchStart = currentCard
    ? Math.floor(currentCard.index / REVIEW_BATCH_SIZE) * REVIEW_BATCH_SIZE
    : 0;
  const currentBatchEnd = currentCard
    ? Math.min(currentCard.total, currentBatchStart + REVIEW_BATCH_SIZE) - 1
    : 0;

  const handleSaveEdits = async () => {
    if (!summary || !currentCard) {
      return;
    }
    setIsSavingEdits(true);
    setErrorMessage("");
    setActionMessage("");
    try {
      const payload = await updateFlashcardCard({
        datasetId: summary.dataset_id,
        index: currentCard.index,
        profileFilter: currentProfileFilter,
        updates: {
          meaning_english: editMeaningEnglish,
          meaning_spanish: editMeaningSpanish,
          master_image_prompt: editMasterImagePrompt,
          visual_description: editVisualDescription,
        },
      });
      setSummary(payload.dataset);
      setCurrentCardWithCache(payload.card, summary.dataset_id, currentProfileFilter);
      setActionMessage("Edits saved.");
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsSavingEdits(false);
    }
  };

  const handleRerunGeneration = async (mode: "full" | "image") => {
    if (!summary || !currentCard) {
      return;
    }
    setIsRerunning(true);
    setErrorMessage("");
    setActionMessage("");
    try {
      const payload = await rerunFlashcardCardGeneration({
        datasetId: summary.dataset_id,
        index: currentCard.index,
        profileFilter: currentProfileFilter,
        mode,
      });
      setSummary(payload.dataset);
      setCurrentCardWithCache(payload.card, summary.dataset_id, currentProfileFilter);
      setActionMessage(mode === "image" ? "Image generation rerun completed." : "Generation rerun completed.");
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsRerunning(false);
    }
  };

  const handleUploadCustomImage = async () => {
    if (!summary || !currentCard || !customImageFile) {
      return;
    }
    setIsUploadingImage(true);
    setErrorMessage("");
    setActionMessage("");
    try {
      const payload = await uploadFlashcardCardImage({
        datasetId: summary.dataset_id,
        index: currentCard.index,
        profileFilter: currentProfileFilter,
        imageFile: customImageFile,
      });
      setSummary(payload.dataset);
      setCurrentCardWithCache(payload.card, summary.dataset_id, currentProfileFilter);
      setCustomImageFile(null);
      setActionMessage("Custom image uploaded.");
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsUploadingImage(false);
    }
  };

  const handleLoadSavedDataset = async () => {
    if (!selectedProfile) {
      setErrorMessage("Select a saved profile.");
      return;
    }
    if (!selectedFileName) {
      setErrorMessage("Select a saved CSV file.");
      return;
    }

    setIsLoading(true);
    setErrorMessage("");
    try {
      cardCacheRef.current.clear();
      inFlightCardRequestsRef.current.clear();
      const dataset = await createFlashcardDatasetFromSaved({
        profileId: selectedProfile,
        fileName: selectedFileName,
      });
      setSummary(dataset);
      setProfileFilter("All profiles");
      const firstCard = await getFlashcardCard({
        datasetId: dataset.dataset_id,
        index: 0,
      });
      setCurrentCardWithCache(firstCard, dataset.dataset_id, "");
      setIsEditMode(false);
      setCustomImageFile(null);
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsLoading(false);
    }
  };

  const handleLoadUploadDataset = async () => {
    if (!uploadFile) {
      setErrorMessage("Upload a CSV file first.");
      return;
    }

    setIsLoading(true);
    setErrorMessage("");
    try {
      cardCacheRef.current.clear();
      inFlightCardRequestsRef.current.clear();
      const dataset = await createFlashcardDatasetFromUpload(uploadFile);
      setSummary(dataset);
      setProfileFilter("All profiles");
      const firstCard = await getFlashcardCard({
        datasetId: dataset.dataset_id,
        index: 0,
      });
      setCurrentCardWithCache(firstCard, dataset.dataset_id, "");
      setIsEditMode(false);
      setCustomImageFile(null);
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsLoading(false);
    }
  };

  const handlePrevious = async () => {
    if (!currentCard) {
      return;
    }
    await loadCard(
      Math.max(0, currentBatchStart - REVIEW_BATCH_SIZE),
      profileFilter,
    );
  };

  const handleNext = async () => {
    if (!currentCard) {
      return;
    }
    await loadCard(
      Math.min(currentCard.total - 1, currentBatchStart + REVIEW_BATCH_SIZE),
      profileFilter,
    );
  };

  const handleFilterApply = async () => {
    await loadCard(0, profileFilter);
  };

  useEffect(() => {
    if (sourceMode !== "saved") {
      return;
    }
    if (summary || isLoading) {
      return;
    }
    if (!selectedProfile || !selectedFileName) {
      return;
    }
    if (hasAutoLoadedSavedDatasetRef.current) {
      return;
    }
    hasAutoLoadedSavedDatasetRef.current = true;
    void handleLoadSavedDataset();
  }, [
    sourceMode,
    summary,
    isLoading,
    selectedProfile,
    selectedFileName,
  ]);

  return (
    <div className="workspace-page single-column">
      <header className="page-header">
        <h1>Flashcard Reviewer</h1>
        <p>Review cards from saved pipeline CSVs or uploaded CSVs with front and back shown together.</p>
      </header>

      <section className="panel-block">
        <div className="inline-controls">
          <button
            type="button"
            className={sourceMode === "saved" ? "primary" : "secondary"}
            onClick={() => setSourceMode("saved")}
          >
            Saved Pipeline CSV
          </button>
          <button
            type="button"
            className={sourceMode === "upload" ? "primary" : "secondary"}
            onClick={() => setSourceMode("upload")}
          >
            Upload CSV
          </button>
        </div>

        {sourceMode === "saved" ? (
          <>
            <label className="field-label" htmlFor="review-profile">
              Profile
            </label>
            <select
              id="review-profile"
              value={selectedProfile}
              onChange={(event) => {
                setSelectedProfile(event.target.value);
                setSelectedFileName("");
              }}
              disabled={!hasSavedProfiles}
            >
              {hasSavedProfiles ? (
                profiles.map((profile) => (
                  <option key={profile} value={profile}>
                    {profile}
                  </option>
                ))
              ) : (
                <option value="">No saved profiles found</option>
              )}
            </select>

            <label className="field-label" htmlFor="review-file">
              Saved CSV
            </label>
            <select
              id="review-file"
              value={selectedFileName}
              onChange={(event) => setSelectedFileName(event.target.value)}
              disabled={!hasSavedProfiles || !hasSavedFiles}
            >
              {hasSavedFiles ? (
                savedFiles.map((file) => (
                  <option key={file.file_path} value={file.file_name}>
                    {file.file_name}
                  </option>
                ))
              ) : (
                <option value="">
                  {hasSavedProfiles ? "No CSV files found for selected profile" : "Select profile first"}
                </option>
              )}
            </select>
            <p className="muted small">
              Profiles: {profiles.length} | CSV files: {savedFiles.length}
            </p>

            <button
              type="button"
              className="primary"
              onClick={handleLoadSavedDataset}
              disabled={isLoading || !hasSavedProfiles || !selectedFileName}
            >
              {isLoading ? "Loading..." : "Load Reviewer Dataset"}
            </button>
          </>
        ) : (
          <>
            <label className="field-label" htmlFor="review-upload">
              CSV File
            </label>
            <input
              id="review-upload"
              type="file"
              accept=".csv"
              onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
            />
            <button type="button" className="primary" onClick={handleLoadUploadDataset} disabled={isLoading}>
              {isLoading ? "Loading..." : "Upload And Review"}
            </button>
          </>
        )}

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
      </section>

      {summary ? (
        <section className="panel-block">
          <p>
            Dataset: <strong>{summary.source_label}</strong> ({summary.total_cards} cards)
          </p>

          {summary.available_profiles.length > 0 ? (
            <div className="inline-controls">
              <select value={profileFilter} onChange={(event) => setProfileFilter(event.target.value)}>
                {availableFilters.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
              <button type="button" className="secondary" onClick={handleFilterApply}>
                Apply Profile Filter
              </button>
            </div>
          ) : null}

          {currentCard ? (
            <>
              <div className="inline-controls">
                <button
                  type="button"
                  className="secondary"
                  onClick={handlePrevious}
                  disabled={currentBatchStart <= 0}
                >
                  Previous 5
                </button>
                <span>
                  Cards {currentBatchStart + 1}-{currentBatchEnd + 1} / {currentCard.total} (selected{" "}
                  {currentCard.index + 1})
                </span>
              <button
                type="button"
                className="secondary"
                onClick={handleNext}
                disabled={currentBatchEnd >= currentCard.total - 1}
              >
                Next 5
              </button>
              <button
                type="button"
                className={isEditMode ? "primary" : "secondary"}
                onClick={() => setIsEditMode((previous) => !previous)}
              >
                {isEditMode ? "Disable Edit Mode" : "Enable Edit Mode"}
              </button>
            </div>

              <div className="review-card-grid">
                <div className="card-front">
                  <h2>{currentCard.front.word || "(no word)"}</h2>
                  <p>{currentCard.front.pronunciation}</p>
                  <p className="muted">
                    {currentCard.front.part_of_speech} {currentCard.front.register}
                  </p>
                  <p className="muted">Profile: {currentCard.front.profile_id}</p>
                  {currentCard.front.audio ? <audio controls src={currentCard.front.audio} /> : null}
                </div>

                <div className="card-back">
                  <h3>Meanings</h3>
                  <p>{currentCard.back.meaning_english}</p>
                  <p>{currentCard.back.meaning_spanish}</p>

                  {Object.keys(currentCard.back.details || {}).length > 0 ? (
                    <>
                      <h3>Details</h3>
                      <ul className="plain-list">
                        {Object.entries(currentCard.back.details).map(([key, value]) => (
                          <li key={key}>
                            <strong>{key}:</strong> {value}
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : null}

                  <h3>Relationships</h3>
                  <p>Synonyms: {currentCard.back.relationships.synonyms.join(" | ")}</p>
                  <p>Antonyms: {currentCard.back.relationships.antonyms.join(" | ")}</p>
                  <p>Collocations: {currentCard.back.relationships.collocations.join(" | ")}</p>

                  <h3>Sentences</h3>
                  {currentCard.back.sentences.length === 0 ? (
                    <p className="muted">No sentence data.</p>
                  ) : (
                    currentCard.back.sentences.map((sentence) => (
                      <div key={`s-${sentence.index}`} className="sentence-item">
                        <p>{sentence.sentence}</p>
                        <p className="muted">{sentence.translation_english}</p>
                        <p className="muted">{sentence.translation_spanish}</p>
                        {sentence.audio ? <audio controls src={sentence.audio} /> : null}
                      </div>
                    ))
                  )}

                  {currentCard.back.image.picture ? (
                    <div>
                      <h3>Image</h3>
                      <img
                        src={currentCard.back.image.picture_url || currentCard.back.image.picture}
                        alt="card visual"
                        className="review-image"
                      />
                      <p className="muted">
                        Render status: {currentCard.back.image.image_render_status || "unknown"}
                      </p>
                      {currentCard.back.image.image_term_type ? (
                        <p className="muted">Image term type: {currentCard.back.image.image_term_type}</p>
                      ) : null}
                      {currentCard.back.image.visual_description ? (
                        <p className="muted">Visual description: {currentCard.back.image.visual_description}</p>
                      ) : null}
                      {currentCard.back.image.master_image_prompt ? (
                        <p className="muted">Master prompt: {currentCard.back.image.master_image_prompt}</p>
                      ) : null}
                      {currentCard.back.image.image_generation_skip_reason ? (
                        <p className="muted">
                          Generation skip reason: {currentCard.back.image.image_generation_skip_reason}
                        </p>
                      ) : null}
                      {currentCard.back.image.image_render_skip_reason ? (
                        <p className="muted">
                          Render skip reason: {currentCard.back.image.image_render_skip_reason}
                        </p>
                      ) : null}
                    </div>
                  ) : null}

                  {isEditMode ? (
                    <>
                      <div className="panel-card">
                        <h3>Edit Generated Content</h3>
                        <label className="field-label" htmlFor="edit-meaning-english">
                          Meaning (English)
                        </label>
                        <textarea
                          id="edit-meaning-english"
                          value={editMeaningEnglish}
                          rows={2}
                          onChange={(event) => setEditMeaningEnglish(event.target.value)}
                        />

                        <label className="field-label" htmlFor="edit-meaning-spanish">
                          Meaning (Spanish)
                        </label>
                        <textarea
                          id="edit-meaning-spanish"
                          value={editMeaningSpanish}
                          rows={2}
                          onChange={(event) => setEditMeaningSpanish(event.target.value)}
                        />

                        <label className="field-label" htmlFor="edit-master-image-prompt">
                          Master Image Prompt
                        </label>
                        <textarea
                          id="edit-master-image-prompt"
                          value={editMasterImagePrompt}
                          rows={3}
                          onChange={(event) => setEditMasterImagePrompt(event.target.value)}
                        />

                        <label className="field-label" htmlFor="edit-visual-description">
                          Visual Description
                        </label>
                        <textarea
                          id="edit-visual-description"
                          value={editVisualDescription}
                          rows={2}
                          onChange={(event) => setEditVisualDescription(event.target.value)}
                        />

                        <div className="inline-controls wrap">
                          <button
                            type="button"
                            className="primary"
                            onClick={handleSaveEdits}
                            disabled={isSavingEdits}
                          >
                            {isSavingEdits ? "Saving..." : "Save Edits"}
                          </button>
                          <button
                            type="button"
                            className="secondary"
                            onClick={() => {
                              void handleRerunGeneration("full");
                            }}
                            disabled={isRerunning}
                          >
                            {isRerunning ? "Rerunning..." : "Rerun Full Generation"}
                          </button>
                          <button
                            type="button"
                            className="secondary"
                            onClick={() => {
                              void handleRerunGeneration("image");
                            }}
                            disabled={isRerunning}
                          >
                            {isRerunning ? "Rerunning..." : "Rerun Image"}
                          </button>
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
                    </>
                  ) : null}
                </div>
              </div>
            </>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
