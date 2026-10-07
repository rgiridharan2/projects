import { CircleAlert, CircleCheck, Download, FileUp, Upload } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "../api";
import { useImportTrainees } from "../queries";
import Modal from "./Modal";
import { Spinner, inputClasses } from "./ui";

const STEPS = ["Upload", "Review", "Done"];
const TEMPLATE = "name,email,cohort_id\nSam Lee,sam.lee@example.com,c1\nAna Ruiz,ana.ruiz@example.com,c3\n";

/**
 * Bulk trainee import in three steps:
 *   1. Upload a CSV (or paste it).
 *   2. Review: the server validates every row (dry run, nothing saved): bad emails, emails that already
 *      have an account, duplicates in the file, unknown cohorts. Then set one initial password.
 *   3. Import: the server validates again and saves the valid rows in one transaction.
 */
export default function ImportWizard({ onClose }) {
  const [step, setStep] = useState(0);
  const [csv, setCsv] = useState("");
  const [fileName, setFileName] = useState(null);
  const [password, setPassword] = useState("");
  const preview = useImportTrainees();
  const commit = useImportTrainees();
  const report = preview.data;

  async function chooseFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    setCsv(await file.text());
  }

  function review(event) {
    event.preventDefault();
    preview.mutate({ csv, dry_run: true }, { onSuccess: () => setStep(1) });
  }

  function importRows(event) {
    event.preventDefault();
    commit.mutate(
      { csv, dry_run: false, initial_password: password, skip_invalid: report.invalid_count > 0 },
      { onSuccess: () => setStep(2) },
    );
  }

  return (
    <Modal title="Import trainees from CSV" icon={FileUp} onClose={onClose} width="max-w-2xl">
      <ol className="mt-4 flex items-center gap-2 text-xs font-medium">
        {STEPS.map((label, i) => (
          <li key={label} className="flex items-center gap-2">
            <span
              className={`inline-flex size-6 items-center justify-center rounded-full ${
                i < step ? "bg-emerald-500 text-white" : i === step ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-500"
              }`}
            >
              {i < step ? "✓" : i + 1}
            </span>
            <span className={i === step ? "text-slate-900" : "text-slate-500"}>{label}</span>
            {i < STEPS.length - 1 && <span className="h-px w-8 bg-slate-200" />}
          </li>
        ))}
      </ol>

      {step === 0 && (
        <form onSubmit={review} className="mt-5 space-y-4">
          <p className="text-sm text-slate-600">
            Columns: <code className="rounded bg-slate-100 px-1">name,email,cohort_id</code>. Leave cohort_id blank to
            assign later. Up to 500 rows. Nothing is saved until the last step.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-dashed border-slate-300 px-4 py-3 text-sm font-medium text-slate-700 hover:border-indigo-400">
              <Upload className="size-4" aria-hidden /> {fileName ?? "Choose a .csv file"}
              <input type="file" accept=".csv,text/csv" onChange={chooseFile} className="sr-only" />
            </label>
            <a
              href={`data:text/csv;charset=utf-8,${encodeURIComponent(TEMPLATE)}`}
              download="trainees-template.csv"
              className="inline-flex items-center gap-1.5 text-sm text-indigo-600 dark:text-indigo-400 hover:underline"
            >
              <Download className="size-4" aria-hidden /> Template
            </a>
          </div>
          <label className="block text-sm font-medium text-slate-700">
            …or paste it
            <textarea rows={6} value={csv} onChange={(e) => setCsv(e.target.value)} placeholder={TEMPLATE} className={`${inputClasses} font-mono text-xs`} />
          </label>
          {preview.isError && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage(preview.error)}</p>}
          <div className="flex justify-end">
            <button type="submit" disabled={!csv.trim() || preview.isPending} className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50">
              {preview.isPending && <Spinner />} Check rows
            </button>
          </div>
        </form>
      )}

      {step === 1 && report && (
        <form onSubmit={importRows} className="mt-5 space-y-4">
          <p className="flex flex-wrap gap-2 text-sm">
            <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 font-medium text-emerald-800">{report.valid_count} ready</span>
            {report.invalid_count > 0 && (
              <span className="rounded-full bg-red-100 px-2.5 py-0.5 font-medium text-red-800">{report.invalid_count} with errors (will be skipped)</span>
            )}
          </p>
          <div className="max-h-64 overflow-auto rounded-xl border border-slate-200">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-3 py-2 font-medium">Line</th>
                  <th className="px-3 py-2 font-medium">Name</th>
                  <th className="px-3 py-2 font-medium">Email</th>
                  <th className="px-3 py-2 font-medium">Cohort</th>
                  <th className="px-3 py-2 font-medium">Check</th>
                </tr>
              </thead>
              <tbody>
                {report.rows.map((row) => (
                  <tr key={row.line} className={`border-t border-slate-100 ${row.errors.length ? "bg-red-50/60" : ""}`}>
                    <td className="px-3 py-1.5 text-slate-400 tabular-nums">{row.line}</td>
                    <td className="px-3 py-1.5 text-slate-800">{row.name || "–"}</td>
                    <td className="px-3 py-1.5 text-slate-800">{row.email || "–"}</td>
                    <td className="px-3 py-1.5 text-slate-600">{row.cohort_id ?? "later"}</td>
                    <td className="px-3 py-1.5">
                      {row.errors.length ? (
                        <span className="inline-flex items-start gap-1 text-xs text-red-700">
                          <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {row.errors.join("; ")}
                        </span>
                      ) : (
                        <CircleCheck className="size-4 text-emerald-600 dark:text-emerald-400" aria-label="OK" />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {report.valid_count > 0 ? (
            <label className="block text-sm font-medium text-slate-700">
              Initial password for the imported trainees
              <input type="password" required minLength={8} maxLength={72} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputClasses} />
              <span className="mt-1 block text-xs font-normal text-slate-500">Share it with them securely; they all start with the same one.</span>
            </label>
          ) : (
            <p className="text-sm text-slate-600">No row can be imported. Go back, fix the file and check again.</p>
          )}
          {commit.isError && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage(commit.error)}</p>}
          <div className="flex justify-between">
            <button type="button" onClick={() => setStep(0)} className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100">
              Back
            </button>
            <button type="submit" disabled={report.valid_count === 0 || commit.isPending} className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50">
              {commit.isPending && <Spinner />} Import {report.valid_count} trainee{report.valid_count === 1 ? "" : "s"}
            </button>
          </div>
        </form>
      )}

      {step === 2 && commit.data && (
        <div className="mt-6 space-y-4 text-center">
          <CircleCheck className="mx-auto size-10 text-emerald-600 dark:text-emerald-400" aria-hidden />
          <p className="font-medium text-slate-900">
            Imported {commit.data.created.length} trainee{commit.data.created.length === 1 ? "" : "s"}
            {commit.data.invalid_count > 0 && `, skipped ${commit.data.invalid_count}`}.
          </p>
          <p className="text-sm text-slate-500">They can sign in now with the password you set. The import is in the activity log.</p>
          <button onClick={onClose} className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500">
            Done
          </button>
        </div>
      )}
    </Modal>
  );
}
