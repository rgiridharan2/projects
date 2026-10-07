import { CircleCheck, Flag, Send } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "../api";
import { useCreateSubmission } from "../queries";
import { Card, STATUS_OPTIONS, Spinner } from "./ui";

const EMPTY = { milestone_name: "", status: "needs_review", asset_url: "", notes: "" };

const inputClasses =
  "mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30 focus:outline-none";

export default function MilestoneForm() {
  const [form, setForm] = useState(EMPTY);
  const create = useCreateSubmission();
  const update = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }));

  function handleSubmit(event) {
    event.preventDefault();
    // trainee_id is added in useCreateSubmission from the logged-in user; blank optional fields become null.
    create.mutate(
      { ...form, asset_url: form.asset_url || null, notes: form.notes || null },
      { onSuccess: () => setForm(EMPTY) },
    );
  }

  return (
    <Card title="Log progress" icon={Flag}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <label className="block text-sm font-medium text-slate-700">
          Milestone name
          <input
            required
            maxLength={200}
            placeholder="Week 3: Kubernetes fundamentals"
            value={form.milestone_name}
            onChange={update("milestone_name")}
            className={inputClasses}
          />
        </label>

        <label className="block text-sm font-medium text-slate-700">
          Status
          <select value={form.status} onChange={update("status")} className={inputClasses}>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="block text-sm font-medium text-slate-700">
          Resource link <span className="font-normal text-slate-400">(optional)</span>
          <input
            type="url"
            placeholder="https://github.com/you/project"
            value={form.asset_url}
            onChange={update("asset_url")}
            className={inputClasses}
          />
        </label>

        <label className="block text-sm font-medium text-slate-700">
          Reflection notes <span className="font-normal text-slate-400">(optional)</span>
          <textarea
            rows={3}
            maxLength={2000}
            placeholder="What went well, what's blocking you…"
            value={form.notes}
            onChange={update("notes")}
            className={inputClasses}
          />
          <span className="mt-1 block text-right text-xs font-normal text-slate-400">{form.notes.length}/2000</span>
        </label>

        {create.isError && <p className="text-sm text-red-600">{errorMessage(create.error)}</p>}
        {create.isSuccess && (
          <p className="flex items-center gap-1.5 text-sm text-emerald-700">
            <CircleCheck className="size-4" aria-hidden /> Submitted. It's now in your timeline.
          </p>
        )}

        <button
          type="submit"
          disabled={create.isPending}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {create.isPending ? <Spinner /> : <Send className="size-4" aria-hidden />} Submit report
        </button>
      </form>
    </Card>
  );
}
