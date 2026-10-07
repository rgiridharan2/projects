import { Flag, Send } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "../api";
import { shortDate } from "../lib/format";
import { useCreateSubmission } from "../queries";
import Modal from "./Modal";
import { STATUS_OPTIONS, Spinner, TASK_STATUS, inputClasses } from "./ui";

/** The progress report form, opened from the active task card with that task preselected. */
export default function SubmitReportModal({ milestones, initialMilestoneId, onClose }) {
  const [form, setForm] = useState({ milestone_id: initialMilestoneId, status: "needs_review", asset_url: "", notes: "" });
  const create = useCreateSubmission();
  const update = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }));

  function handleSubmit(event) {
    event.preventDefault();
    // trainee_id is added in useCreateSubmission from the logged-in user; the task's title becomes the report's
    // name on the server. Blank optional fields are sent as null.
    create.mutate({ ...form, asset_url: form.asset_url || null, notes: form.notes || null }, { onSuccess: onClose });
  }

  return (
    <Modal title="Submit a progress report" icon={Flag} onClose={onClose} width="max-w-lg">
      <form onSubmit={handleSubmit} className="mt-4 space-y-4">
        <label className="block text-sm font-medium text-slate-700">
          Task
          <select required value={form.milestone_id} onChange={update("milestone_id")} className={inputClasses}>
            {milestones.map((m) => (
              <option key={m.id} value={m.id}>
                {m.title} · due {shortDate(m.due_date)} · {TASK_STATUS[m.status].label}
              </option>
            ))}
          </select>
        </label>

        <label className="block text-sm font-medium text-slate-700">
          How's it going?
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

        {create.isError && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage(create.error)}</p>}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={create.isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {create.isPending ? <Spinner /> : <Send className="size-4" aria-hidden />} Submit report
          </button>
        </div>
      </form>
    </Modal>
  );
}
