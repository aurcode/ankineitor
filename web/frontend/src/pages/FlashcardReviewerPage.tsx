import { useEffect, useMemo, useState } from "react";

import {
  createFlashcardDatasetFromSaved,
  createFlashcardDatasetFromUpload,
  getFlashcardCard,
  getFlashcardSavedFiles,
  getFlashcardSavedProfiles,
} from "../api/pipeline";
import {
  FlashcardCardResponse,
  FlashcardDatasetSummary,
  FlashcardSavedFile,
} from "../types/pipeline";

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
  const [showBack, setShowBack] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

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

  const loadCard = async (index: number, selectedFilter: string): Promise<void> => {
    if (!summary) {
      return;
    }
    const payload = await getFlashcardCard({
      datasetId: summary.dataset_id,
      index,
      profileFilter: selectedFilter === "All profiles" ? "" : selectedFilter,
    });
    setCurrentCard(payload);
  };

  const handleLoadSavedDataset = async () => {
    if (!selectedProfile) {
      setErrorMessage("Select a saved profile.");
      return;
    }

    setIsLoading(true);
    setErrorMessage("");
    try {
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
      setCurrentCard(firstCard);
      setShowBack(false);
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
      const dataset = await createFlashcardDatasetFromUpload(uploadFile);
      setSummary(dataset);
      setProfileFilter("All profiles");
      const firstCard = await getFlashcardCard({
        datasetId: dataset.dataset_id,
        index: 0,
      });
      setCurrentCard(firstCard);
      setShowBack(false);
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
    await loadCard(Math.max(0, currentCard.index - 1), profileFilter);
    setShowBack(false);
  };

  const handleNext = async () => {
    if (!currentCard) {
      return;
    }
    await loadCard(Math.min(currentCard.total - 1, currentCard.index + 1), profileFilter);
    setShowBack(false);
  };

  const handleFilterApply = async () => {
    await loadCard(0, profileFilter);
    setShowBack(false);
  };

  return (
    <div className="workspace-page single-column">
      <header className="page-header">
        <h1>Flashcard Reviewer</h1>
        <p>Review cards from saved pipeline CSVs or uploaded CSVs with front/back card flipping.</p>
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
              onChange={(event) => setSelectedProfile(event.target.value)}
            >
              {profiles.map((profile) => (
                <option key={profile} value={profile}>
                  {profile}
                </option>
              ))}
            </select>

            <label className="field-label" htmlFor="review-file">
              Saved CSV
            </label>
            <select
              id="review-file"
              value={selectedFileName}
              onChange={(event) => setSelectedFileName(event.target.value)}
            >
              {savedFiles.map((file) => (
                <option key={file.file_path} value={file.file_name}>
                  {file.file_name}
                </option>
              ))}
            </select>

            <button type="button" className="primary" onClick={handleLoadSavedDataset} disabled={isLoading}>
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

        {errorMessage ? <p className="error-message">{errorMessage}</p> : null}
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
                  disabled={currentCard.index <= 0}
                >
                  Previous
                </button>
                <span>
                  Card {currentCard.index + 1} / {currentCard.total}
                </span>
                <button
                  type="button"
                  className="secondary"
                  onClick={handleNext}
                  disabled={currentCard.index >= currentCard.total - 1}
                >
                  Next
                </button>
                <button type="button" className="primary" onClick={() => setShowBack((prev) => !prev)}>
                  {showBack ? "Show Front" : "Flip Card"}
                </button>
              </div>

              {!showBack ? (
                <div className="card-front">
                  <h2>{currentCard.front.word || "(no word)"}</h2>
                  <p>{currentCard.front.pronunciation}</p>
                  <p className="muted">
                    {currentCard.front.part_of_speech} {currentCard.front.register}
                  </p>
                  <p className="muted">Profile: {currentCard.front.profile_id}</p>
                  {currentCard.front.audio ? <audio controls src={currentCard.front.audio} /> : null}
                </div>
              ) : (
                <div className="card-back">
                  <h3>Meanings</h3>
                  <p>{currentCard.back.meaning_english}</p>
                  <p>{currentCard.back.meaning_spanish}</p>

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
                      <img src={currentCard.back.image.picture} alt="card visual" className="review-image" />
                    </div>
                  ) : null}
                </div>
              )}
            </>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
