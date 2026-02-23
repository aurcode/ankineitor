import { FormEvent, useState } from "react";

import {
  clearAuthSession,
  createAuthToken,
  getAuthToken,
  getAuthUsername,
  saveAuthSession,
} from "./api/pipeline";
import { AnkiDeckPage } from "./pages/AnkiDeckPage";
import { AdminQueueMonitorPage } from "./pages/AdminQueueMonitorPage";
import { FlashcardReviewerPage } from "./pages/FlashcardReviewerPage";
import { GeneratedLibraryPage } from "./pages/GeneratedLibraryPage";
import { PipelinePage } from "./pages/PipelinePage";
import { WordExtractorPage } from "./pages/WordExtractorPage";

type WorkspaceTab =
  | "pipeline"
  | "anki"
  | "reviewer"
  | "generated-library"
  | "extractor"
  | "admin-monitor";

const TAB_OPTIONS: Array<{ key: WorkspaceTab; label: string }> = [
  { key: "pipeline", label: "Pipeline" },
  { key: "anki", label: "Anki Deck Generator" },
  { key: "reviewer", label: "Flashcard Reviewer" },
  { key: "generated-library", label: "Generated Library" },
  { key: "extractor", label: "Word Extractor" },
  { key: "admin-monitor", label: "Admin Queue Monitor" },
];

function LoginPanel(props: { onAuthenticated: (username: string, token: string) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErrorMessage("");

    if (!username.trim() || !password.trim()) {
      setErrorMessage("Username and password are required.");
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = await createAuthToken({ username, password });
      saveAuthSession(payload);
      props.onAuthenticated(payload.user.username, payload.token);
    } catch (error) {
      setErrorMessage(String(error));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="app-shell">
      <section className="panel-block login-panel">
        <h1>Sign In</h1>
        <p className="muted">Use your Django user credentials to access the migrated workspace tabs.</p>
        <form onSubmit={handleSubmit} className="single-column-form">
          <label className="field-label" htmlFor="login-username">
            Username
          </label>
          <input
            id="login-username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
          />

          <label className="field-label" htmlFor="login-password">
            Password
          </label>
          <input
            id="login-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />

          {errorMessage ? (
            <p className="error-message" role="alert">
              {errorMessage}
            </p>
          ) : null}
          <button type="submit" className="primary" disabled={isSubmitting}>
            {isSubmitting ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </section>
    </div>
  );
}

export default function App() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("pipeline");
  const [authToken, setAuthToken] = useState<string | null>(() => getAuthToken());
  const [authUsername, setAuthUsername] = useState<string | null>(() => getAuthUsername());

  if (!authToken) {
    return (
      <LoginPanel
        onAuthenticated={(username, token) => {
          setAuthUsername(username);
          setAuthToken(token);
        }}
      />
    );
  }

  const handleSignOut = () => {
    clearAuthSession();
    setAuthToken(null);
    setAuthUsername(null);
    setActiveTab("pipeline");
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-nav-block">
          <div className="app-brand" aria-hidden="true">
            <span className="app-brand-kicker">Ankineitor</span>
            <span className="app-brand-subtitle">AI language operations workspace</span>
          </div>
          <nav className="top-tabs" aria-label="Workspace tabs">
            {TAB_OPTIONS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                className={activeTab === tab.key ? "tab-button active" : "tab-button"}
                aria-pressed={activeTab === tab.key}
                onClick={() => setActiveTab(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>
        <div className="session-chip">
          <span className="muted">Signed in as {authUsername || "user"}</span>
          <button type="button" className="secondary" onClick={handleSignOut}>
            Sign Out
          </button>
        </div>
      </header>

      {activeTab === "pipeline" ? <PipelinePage /> : null}
      {activeTab === "anki" ? <AnkiDeckPage /> : null}
      {activeTab === "reviewer" ? <FlashcardReviewerPage /> : null}
      {activeTab === "generated-library" ? <GeneratedLibraryPage /> : null}
      {activeTab === "extractor" ? <WordExtractorPage /> : null}
      {activeTab === "admin-monitor" ? <AdminQueueMonitorPage /> : null}
    </div>
  );
}
