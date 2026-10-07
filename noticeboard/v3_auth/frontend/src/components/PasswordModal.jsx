import { KeyRound, X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { errorMessage } from "../api";
import { useAuth } from "../auth/AuthContext";
import { Avatar, Spinner, roleLabel } from "./ui";

/** Asks for the chosen account's password, then logs in as that account. */
export default function PasswordModal({ target, onClose }) {
  const { login } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const titleId = useId();

  useEffect(() => {
    const closeOnEscape = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(target.id, password); // POST /api/auth/login; AuthContext stores the new token
      onClose();
    } catch (err) {
      setError(errorMessage(err));
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl"
      >
        <div className="flex items-start justify-between">
          <h2 id={titleId} className="flex items-center gap-2 font-semibold text-slate-800">
            <KeyRound className="size-4.5 text-slate-500" aria-hidden /> Confirm it's you
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-slate-400 hover:text-slate-600"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>

        <div className="mt-4 flex items-center gap-3 rounded-lg bg-slate-50 p-3">
          <Avatar name={target.name} role={target.role} size="lg" />
          <div>
            <p className="font-medium text-slate-900">{target.name}</p>
            <p className="text-sm text-slate-500">{roleLabel(target.role, target.cohort_name)}</p>
          </div>
        </div>

        <label className="mt-4 block text-sm font-medium text-slate-700">
          Password
          <input
            type="password"
            autoFocus
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30 focus:outline-none"
          />
        </label>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || !password}
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {submitting && <Spinner />} Sign in as {target.name.split(" ")[0]}
          </button>
        </div>
      </form>
    </div>
  );
}
