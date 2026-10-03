// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, type InputHTMLAttributes, type KeyboardEvent } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "defaultValue" | "onChange" | "onBlur" | "onKeyDown"> & {
  value: string;
  onCommit: (value: string) => void;
  validate?: (value: string) => string | null | undefined;
};

const guidance = "Edit identifier; Enter or leaving the field applies it. Escape cancels.";

export default function TableIdentityInput({ value, onCommit, validate, title, ...inputProps }: Props) {
  const [draft, setDraft] = useState(value);
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft(value);
    setError("");
  }, [value]);

  const commit = () => {
    const validationError = validate?.(draft) ?? "";
    if (validationError) {
      setError(validationError);
      return;
    }
    setError("");
    if (draft !== value) onCommit(draft);
  };
  const keyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "Enter") {
      event.preventDefault();
      commit();
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      setDraft(value);
      setError("");
    }
  };

  return <span className="table-identity-input" data-search-text={value}>
    <input {...inputProps} value={draft} title={title ?? guidance} aria-invalid={error ? true : undefined}
      onChange={event => { setDraft(event.target.value); if (error) setError(""); }} onBlur={commit} onKeyDown={keyDown} />
    {error && <small className="table-identity-error" role="alert">{error}</small>}
  </span>;
}
