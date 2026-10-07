import { KeyRound } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "../api";
import { useAuth } from "../auth/AuthContext";
import Modal from "./Modal";
import { Avatar, Spinner, inputClasses, roleLabel } from "./ui";

/** The navbar quick-switcher: asks for the chosen account's password, then logs in as that account. */
export default function PasswordModal({ target, onClose }) {
  const { login } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

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
    <Modal title="Confirm it's you" icon={KeyRound} onClose={onClose}>
      <form onSubmit={handleSubmit}>
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
            className={inputClasses}
          />
        </label>
        {error && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>}

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
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {submitting && <Spinner />} Sign in as {target.name.split(" ")[0]}
          </button>
        </div>
      </form>
    </Modal>
  );
}
