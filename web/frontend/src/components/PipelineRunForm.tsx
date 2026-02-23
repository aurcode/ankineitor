import { FormEvent } from "react";

import { ProfileOptions } from "../types/pipeline";

interface PipelineRunFormProps {
  profiles: ProfileOptions[];
  selectedProfileId: string;
  selectedTransforms: string[];
  wordsInput: string;
  isSubmitting: boolean;
  errorMessage: string;
  onProfileChange: (profileId: string) => void;
  onTransformsChange: (transforms: string[]) => void;
  onWordsInputChange: (value: string) => void;
  onSubmit: () => void;
}

export function PipelineRunForm(props: PipelineRunFormProps) {
  const selectedProfile = props.profiles.find(
    (profile) => profile.profile_id === props.selectedProfileId,
  );

  const availableTransforms = selectedProfile?.available_transform_names ?? [];

  const handleCheckboxChange = (name: string, checked: boolean) => {
    const current = new Set(props.selectedTransforms);
    if (checked) {
      current.add(name);
    } else {
      current.delete(name);
    }
    props.onTransformsChange(Array.from(current));
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    props.onSubmit();
  };

  return (
    <form className="run-form" onSubmit={handleSubmit}>
      <section>
        <h2>Run Pipeline</h2>
      </section>

      <label className="field-label" htmlFor="profile-select">
        Profile
      </label>
      <select
        id="profile-select"
        value={props.selectedProfileId}
        onChange={(event) => props.onProfileChange(event.target.value)}
      >
        {props.profiles.map((profile) => (
          <option key={profile.profile_id} value={profile.profile_id}>
            {profile.display_name}
          </option>
        ))}
      </select>
      <p className="profile-description">{selectedProfile?.description ?? ""}</p>

      <label className="field-label">Optional Transforms</label>
      <div className="transform-grid">
        {availableTransforms.map((name) => {
          const checked = props.selectedTransforms.includes(name);
          return (
            <label key={name} className="transform-option">
              <input
                type="checkbox"
                checked={checked}
                onChange={(event) => handleCheckboxChange(name, event.target.checked)}
              />
              <span>{name}</span>
            </label>
          );
        })}
      </div>

      {selectedProfile && selectedProfile.always_included_transform_names.length > 0 ? (
        <p className="muted small">
          Always included: {selectedProfile.always_included_transform_names.join(", ")}
        </p>
      ) : null}
      {selectedProfile &&
      Object.keys(selectedProfile.unavailable_transform_reasons).length > 0 ? (
        <details>
          <summary className="muted small">Hidden transforms for this profile</summary>
          <ul className="plain-list">
            {Object.entries(selectedProfile.unavailable_transform_reasons).map(
              ([name, reason]) => (
                <li key={name}>
                  {name}: {reason}
                </li>
              ),
            )}
          </ul>
        </details>
      ) : null}

      <label className="field-label" htmlFor="words-input">
        Words (one per line)
      </label>
      <textarea
        id="words-input"
        value={props.wordsInput}
        onChange={(event) => props.onWordsInputChange(event.target.value)}
        rows={8}
        placeholder={"你好\n谢谢\n苹果"}
      />

      {props.errorMessage ? (
        <p className="error-message" role="alert">
          {props.errorMessage}
        </p>
      ) : null}

      <button type="submit" className="primary" disabled={props.isSubmitting}>
        {props.isSubmitting ? "Submitting..." : "Run Pipeline"}
      </button>
    </form>
  );
}
