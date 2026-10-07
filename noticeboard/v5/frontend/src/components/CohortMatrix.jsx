import { BellRing, Check, FileDown, FileUp, Grid3x3, Siren } from "lucide-react";
import { useEffect, useState } from "react";
import { errorMessage } from "../api";
import { shortDate, timeAgo } from "../lib/format";
import { downloadCohortReport, useCohortMatrix, useCohorts, useNudge, useNudgeAll } from "../queries";
import ImportWizard from "./ImportWizard";
import { Avatar, Card, Spinner, TASK_STATUS, TONE_CLASSES, inputClasses } from "./ui";

/**
 * Trainees x milestones for one cohort. Overdue cells (deadline passed, nothing submitted) are red
 * and carry a Nudge button; the server works out "overdue" from the current time and each due_date.
 */
export default function CohortMatrix() {
  const cohorts = useCohorts();
  const [cohortId, setCohortId] = useState("");
  const matrix = useCohortMatrix(cohortId);
  const nudge = useNudge();
  const nudgeAll = useNudgeAll();
  const [flash, setFlash] = useState(null);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(null);

  // Start on the first cohort once the list arrives.
  useEffect(() => {
    if (!cohortId && cohorts.data?.length) setCohortId(cohorts.data[0].id);
  }, [cohortId, cohorts.data]);

  const data = matrix.data;
  const unNudged = data?.rows.flatMap((r) => r.cells).filter((c) => c.overdue && !c.nudged_at).length ?? 0;
  const error = nudge.error ?? nudgeAll.error;

  async function exportCsv() {
    setExporting(true);
    setExportError(null);
    try {
      await downloadCohortReport(cohortId);
    } catch (err) {
      setExportError(errorMessage(err));
    } finally {
      setExporting(false);
    }
  }

  function sendAll() {
    nudgeAll.mutate(cohortId, {
      onSuccess: (result) => setFlash(`Sent ${result.created} reminder${result.created === 1 ? "" : "s"}.`),
    });
  }

  return (
    <Card
      title="Cohort matrix"
      icon={Grid3x3}
      action={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <select
            aria-label="Cohort"
            value={cohortId}
            onChange={(event) => {
              setCohortId(event.target.value);
              setFlash(null);
            }}
            className={`${inputClasses} mt-0 w-auto py-1.5`}
          >
            {cohorts.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.trainee_count})
              </option>
            ))}
          </select>
          <button
            onClick={exportCsv}
            disabled={!cohortId || exporting}
            title="Download this cohort's performance report as CSV"
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {exporting ? <Spinner /> : <FileDown className="size-4" aria-hidden />} Export CSV
          </button>
          <button
            onClick={() => setImporting(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <FileUp className="size-4" aria-hidden /> Import trainees
          </button>
        </div>
      }
    >
      {!data ? (
        matrix.isError ? <p className="text-sm text-red-600 dark:text-red-400">{errorMessage(matrix.error)}</p> : <Spinner />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-slate-600">
              {data.overdue_total === 0 ? (
                "Nobody is overdue in this cohort."
              ) : (
                <>
                  <span className="mr-2 inline-flex items-center gap-1 rounded-full bg-red-600 px-2.5 py-0.5 text-xs font-semibold text-white">
                    <Siren className="size-3.5" aria-hidden /> {data.overdue_total} overdue
                  </span>
                  past their deadline with nothing submitted
                </>
              )}
            </p>
            <button
              onClick={sendAll}
              disabled={unNudged === 0 || nudgeAll.isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500 disabled:bg-slate-300"
            >
              {nudgeAll.isPending ? <Spinner /> : <BellRing className="size-4" aria-hidden />} Nudge all overdue ({unNudged})
            </button>
          </div>
          {flash && <p className="mb-3 text-sm text-emerald-700">{flash}</p>}
          {exportError && <p className="mb-3 text-sm text-red-600 dark:text-red-400">Export failed: {exportError}</p>}
          {error && <p className="mb-3 text-sm text-red-600 dark:text-red-400">{errorMessage(error)}</p>}

          {data.rows.length === 0 || data.milestones.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-500">
              {data.rows.length === 0 ? "No trainees in this cohort yet." : "No tasks dispatched to this cohort yet."}
            </p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-200">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="bg-slate-50 text-left">
                    <th scope="col" className="sticky left-0 z-10 bg-slate-50 px-3 py-2 font-medium text-slate-600">
                      Trainee
                    </th>
                    {data.milestones.map((m, i) => {
                      const overdueHere = data.rows.filter((r) => r.cells[i].overdue).length;
                      return (
                        <th key={m.id} scope="col" title={m.title} className="min-w-24 px-2 py-2 text-center font-medium text-slate-600">
                          <span className="block">#{m.milestone_order}</span>
                          <span className="block text-[11px] font-normal text-slate-400">{shortDate(m.due_date)}</span>
                          {overdueHere > 0 && <span className="block text-[11px] font-semibold text-red-600 dark:text-red-400">{overdueHere} late</span>}
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.trainee.id} className="border-t border-slate-100">
                      <th scope="row" className="sticky left-0 z-10 bg-surface px-3 py-2 text-left font-normal whitespace-nowrap">
                        <span className="flex items-center gap-2">
                          <Avatar name={row.trainee.name} role="trainee" size="xs" />
                          <span className="text-slate-800">{row.trainee.name}</span>
                          {row.overdue_count > 0 && (
                            <span className="rounded-full bg-red-100 px-1.5 text-[11px] font-semibold text-red-700">{row.overdue_count}</span>
                          )}
                        </span>
                      </th>
                      {row.cells.map((cell, i) => (
                        <td key={cell.milestone_id} className="px-1.5 py-1.5 text-center">
                          <MatrixCell
                            cell={cell}
                            label={`${row.trainee.name}, ${data.milestones[i].title}`}
                            nudging={nudge.isPending && nudge.variables?.milestone_id === cell.milestone_id && nudge.variables?.trainee_id === row.trainee.id}
                            onNudge={() => nudge.mutate({ trainee_id: row.trainee.id, milestone_id: cell.milestone_id })}
                          />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Legend />
        </>
      )}
      {importing && <ImportWizard onClose={() => setImporting(false)} />}
    </Card>
  );
}

function MatrixCell({ cell, label, nudging, onNudge }) {
  if (cell.overdue) {
    return (
      <span className="relative block">
        <OverdueCell cell={cell} label={label} nudging={nudging} onNudge={onNudge} />
        {cell.escalated && (
          <span
            title="Escalated: more than 48 hours past the deadline"
            className="absolute -top-1.5 -right-1 rounded-full bg-amber-400 px-1 text-[9px] leading-4 font-bold text-amber-950 ring-2 ring-surface"
          >
            48h
          </span>
        )}
      </span>
    );
  }
  const { label: statusLabel, Icon, tone } = TASK_STATUS[cell.status];
  const pending = cell.status === "pending";
  return (
    <span
      title={`${label}: ${statusLabel}${pending ? " (not due yet)" : ""}`}
      className={`inline-flex size-8 items-center justify-center rounded-lg ${pending ? "bg-slate-50 text-slate-300" : TONE_CLASSES[tone].icon}`}
    >
      <Icon className="size-4" aria-label={statusLabel} />
    </span>
  );
}

function OverdueCell({ cell, label, nudging, onNudge }) {
  return cell.nudged_at ? (
    <span
      title={`${label}: overdue, nudged ${timeAgo(cell.nudged_at)}`}
      className="inline-flex w-full flex-col items-center rounded-lg bg-red-50 px-1 py-1 text-[11px] font-medium text-red-700 ring-1 ring-red-200"
    >
      <Check className="size-3.5" aria-hidden /> Nudged
    </span>
  ) : (
    <button
      onClick={onNudge}
      disabled={nudging}
      title={`${label}: overdue. Send a reminder`}
      className="inline-flex w-full flex-col items-center rounded-lg bg-red-600 px-1 py-1 text-[11px] font-semibold text-white hover:bg-red-500 disabled:opacity-60"
    >
      {nudging ? <Spinner className="size-3.5" /> : <BellRing className="size-3.5" aria-hidden />} Nudge
    </button>
  );
}

function Legend() {
  return (
    <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
      {Object.entries(TASK_STATUS).map(([key, { label, Icon, tone }]) => (
        <li key={key} className="inline-flex items-center gap-1.5">
          <span className={`inline-flex rounded p-0.5 ${key === "pending" ? "bg-slate-50 text-slate-300" : TONE_CLASSES[tone].icon}`}>
            <Icon className="size-3" aria-hidden />
          </span>
          {key === "pending" ? "Not due yet" : label}
        </li>
      ))}
      <li className="inline-flex items-center gap-1.5">
        <span className="inline-flex rounded bg-red-600 p-0.5 text-white">
          <BellRing className="size-3" aria-hidden />
        </span>
        Overdue (click to nudge)
      </li>
    </ul>
  );
}
