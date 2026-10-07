import { CircleCheck, Megaphone, Send, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "../api";
import { timeAgo } from "../lib/format";
import { useAllNotices, useCohorts, usePostNotice } from "../queries";
import { Card, Spinner, inputClasses } from "./ui";

const EMPTY = { title: "", body: "", priority: "standard", target_cohort_id: "" };

/** Broadcast a notice to one cohort or everyone. Urgent ones pop up live for trainees (NoticeTicker). */
export default function NoticeComposer() {
  const cohorts = useCohorts();
  const notices = useAllNotices();
  const post = usePostNotice();
  const [form, setForm] = useState(EMPTY);
  const update = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }));
  const cohortName = Object.fromEntries((cohorts.data ?? []).map((c) => [c.id, c.name]));

  function handleSubmit(event) {
    event.preventDefault();
    post.mutate({ ...form, target_cohort_id: form.target_cohort_id || null }, { onSuccess: () => setForm(EMPTY) });
  }

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <div className="lg:col-span-3">
        <Card title="Broadcast a notice" icon={Megaphone}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <label className="block text-sm font-medium text-slate-700">
              Title
              <input required maxLength={200} value={form.title} onChange={update("title")} className={inputClasses} />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Message
              <textarea required rows={3} value={form.body} onChange={update("body")} className={inputClasses} />
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <fieldset>
                <legend className="text-sm font-medium text-slate-700">Priority</legend>
                <div className="mt-1 grid grid-cols-2 gap-2">
                  {[
                    ["standard", "Standard", Megaphone],
                    ["urgent", "Urgent", TriangleAlert],
                  ].map(([value, label, Icon]) => (
                    <label
                      key={value}
                      className={`flex cursor-pointer items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium ${
                        form.priority === value
                          ? value === "urgent"
                            ? "border-red-500 bg-red-50 text-red-700"
                            : "border-indigo-500 bg-indigo-50 text-indigo-700"
                          : "border-slate-200 text-slate-600"
                      }`}
                    >
                      <input type="radio" name="priority" value={value} checked={form.priority === value} onChange={update("priority")} className="sr-only" />
                      <Icon className="size-4" aria-hidden /> {label}
                    </label>
                  ))}
                </div>
              </fieldset>
              <label className="block text-sm font-medium text-slate-700">
                Audience
                <select value={form.target_cohort_id} onChange={update("target_cohort_id")} className={inputClasses}>
                  <option value="">All trainees</option>
                  {cohorts.data?.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {form.priority === "urgent" && (
              <p className="text-xs text-slate-500">Trainees who have the app open get an urgent pop-up within about 20 seconds.</p>
            )}
            {post.isError && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage(post.error)}</p>}
            {post.isSuccess && (
              <p className="flex items-center gap-1.5 text-sm text-emerald-700">
                <CircleCheck className="size-4" aria-hidden /> Notice sent.
              </p>
            )}
            <button type="submit" disabled={post.isPending} className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50">
              {post.isPending ? <Spinner /> : <Send className="size-4" aria-hidden />} Send notice
            </button>
          </form>
        </Card>
      </div>

      <div className="lg:col-span-2">
        <Card title="Recent notices" icon={Megaphone}>
          {!notices.data ? (
            <Spinner />
          ) : (
            <ul className="max-h-96 space-y-2 overflow-y-auto">
              {[...notices.data]
                .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                .map((n) => (
                  <li key={n.id} className="rounded-lg border border-slate-200 px-3 py-2">
                    <p className="flex items-center gap-2 text-sm font-medium text-slate-900">
                      {n.priority === "urgent" && <TriangleAlert className="size-4 shrink-0 text-red-600 dark:text-red-400" aria-label="Urgent" />}
                      <span className="truncate">{n.title}</span>
                    </p>
                    <p className="text-xs text-slate-500">
                      {n.target_cohort_id ? cohortName[n.target_cohort_id] ?? n.target_cohort_id : "All trainees"} · {timeAgo(n.created_at)}
                    </p>
                  </li>
                ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
