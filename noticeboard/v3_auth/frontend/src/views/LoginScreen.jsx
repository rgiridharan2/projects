import { ClipboardList } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "../api";
import PasswordModal from "../components/PasswordModal";
import { Avatar, Spinner, roleLabel } from "../components/ui";
import { useSwitchOptions } from "../queries";

/** First screen when nobody is logged in: pick an account, then confirm its password. */
export default function LoginScreen() {
  const options = useSwitchOptions();
  const [target, setTarget] = useState(null);

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center gap-2 text-lg font-semibold text-slate-800">
          <ClipboardList className="size-5 text-indigo-600" aria-hidden /> NoticeBoardTracker
        </div>
        <p className="mt-1 text-sm text-slate-500">Choose your account to sign in.</p>

        <div className="mt-5">
          {options.isPending && (
            <p className="flex items-center gap-2 text-sm text-slate-500">
              <Spinner /> Loading accounts…
            </p>
          )}
          {options.isError && <p className="text-sm text-red-600">{errorMessage(options.error)}</p>}
          {options.data && (
            <ul className="max-h-[60vh] space-y-1 overflow-y-auto">
              {options.data.map((option) => (
                <li key={option.id}>
                  <button
                    onClick={() => setTarget(option)}
                    className="flex w-full items-center gap-3 rounded-lg border border-transparent px-3 py-2 text-left hover:border-slate-200 hover:bg-slate-50"
                  >
                    <Avatar name={option.name} role={option.role} />
                    <span>
                      <span className="block text-sm font-medium text-slate-900">{option.name}</span>
                      <span className="block text-xs text-slate-500">{roleLabel(option.role, option.cohort_name)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <p className="mt-5 border-t border-slate-100 pt-4 text-xs text-slate-400">
          Demo accounts all use the password <code className="text-slate-500">password123</code>.
        </p>
      </div>

      {target && <PasswordModal target={target} onClose={() => setTarget(null)} />}
    </div>
  );
}
