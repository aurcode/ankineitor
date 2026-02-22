import { useState } from "react";

import { AnkiDeckPage } from "./pages/AnkiDeckPage";
import { FlashcardReviewerPage } from "./pages/FlashcardReviewerPage";
import { PipelinePage } from "./pages/PipelinePage";
import { WordExtractorPage } from "./pages/WordExtractorPage";

type WorkspaceTab = "pipeline" | "anki" | "reviewer" | "extractor";

const TAB_OPTIONS: Array<{ key: WorkspaceTab; label: string }> = [
  { key: "pipeline", label: "Pipeline" },
  { key: "anki", label: "Anki Deck Generator" },
  { key: "reviewer", label: "Flashcard Reviewer" },
  { key: "extractor", label: "Word Extractor" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("pipeline");

  return (
    <div className="app-shell">
      <nav className="top-tabs" aria-label="Workspace tabs">
        {TAB_OPTIONS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            className={activeTab === tab.key ? "tab-button active" : "tab-button"}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "pipeline" ? <PipelinePage /> : null}
      {activeTab === "anki" ? <AnkiDeckPage /> : null}
      {activeTab === "reviewer" ? <FlashcardReviewerPage /> : null}
      {activeTab === "extractor" ? <WordExtractorPage /> : null}
    </div>
  );
}
