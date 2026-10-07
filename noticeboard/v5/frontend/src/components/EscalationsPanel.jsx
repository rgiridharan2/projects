import { RefreshCw, Siren } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "../api";
import { shortDate, timeAgo } from "../lib/format";
import { useEscalations, useRunEscalations } from "../queries";
import { Avatar, Card, Spinner } from "./ui";

/** Tasks the 48-hour check has flagged. The server runs the check every 15 min; the button runs it now. */
export default function EscalationsPanel() {
  const escalations = useEscalations();
  const run = useRunEscalations();
  const [result, setResult] = useState(null);

  return (
    <Card
      title="Escalations"
      icon={Siren}
      action={
        <button
          onClick={() => run.mutate(undefined, { onSuccess: (r) => setResult(r) })}
          disabled={run.isPending}
          className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          {run.isPending ? <Spinner /> : <RefreshCw className="size-4" aria-hidden />} Run check now
        </button>
      }
    >
      <p className="mb-3 text-xs text-slate-500">
        Tasks more than 48 hours past their deadline with nothing submitted. Checked automatically every 15 minutes; a
        flag clears when the trainee hands the task in.
      </p>
      {result && (
        <p className="mb-3 text-sm text-emerald-700">
          Check complete: {result.created} new, {result.active} open.
        </p>
      )}
      {run.isError && <p className="mb-3 text-sm text-red-600 dark:text-red-400">{errorMessage(run.error)}</p>}

      {!escalations.data ? (
        <Spinner />
      ) : escalations.data.length === 0 ? (
        <p className="py-4 text-center text-sm text-slate-500">Nothing escalated. Everyone is within 48 hours of their deadlines.</p>
      ) : (
        <ul className="grid max-h-72 gap-x-6 overflow-y-auto sm:grid-cols-2">
          {escalations.data.map((e) => (
            <li key={e.id} className="flex items-center gap-3 border-b border-slate-100 py-2.5">
              <Avatar name={e.trainee_name} role="trainee" size="sm" />
              <div className="min-w-0 flex-1 text-sm">
                <p className="truncate text-slate-900">
                  <span className="font-medium">{e.trainee_name}</span> · {e.milestone_title}
                </p>
                <p className="text-xs text-slate-500">
                  {e.cohort_name} · due {shortDate(e.due_date)} ({timeAgo(e.due_date)})
                </p>
              </div>
              <span className="shrink-0 rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-800" title={`Escalated ${new Date(e.escalated_at).toLocaleString()}`}>
                48h+ late
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
