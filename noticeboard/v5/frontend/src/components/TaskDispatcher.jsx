import { CircleCheck, Send } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "../api";
import { useAllMilestones, useCohorts, useDispatchMilestone } from "../queries";
import { Card, Spinner, inputClasses } from "./ui";

/** "2026-10-12T23:59" for an <input type="datetime-local">, which works in local time. */
function toLocalInput(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function defaultDue() {
  const due = new Date();
  due.setDate(due.getDate() + 7);
  due.setHours(23, 59, 0, 0);
  return toLocalInput(due);
}

/**
 * Manager task dispatcher: one task title, sent to any number of cohorts, each with its own deadline.
 * Each copy is appended to its cohort's sequence (milestone_order), which the form previews.
 */
export default function TaskDispatcher() {
  const cohorts = useCohorts();
  const milestones = useAllMilestones();
  const dispatch = useDispatchMilestone();
  const [title, setTitle] = useState("");
  const [picked, setPicked] = useState({}); // cohort_id -> "YYYY-MM-DDTHH:MM" (local)
  const [sent, setSent] = useState(null);

  // Where the task will land in each cohort: one after its current highest milestone_order.
  const nextOrder = (cohortId) =>
    1 + Math.max(0, ...(milestones.data ?? []).filter((m) => m.cohort_id === cohortId).map((m) => m.milestone_order));

  const toggle = (cohortId) =>
    setPicked(({ [cohortId]: existing, ...rest }) => (existing === undefined ? { ...rest, [cohortId]: defaultDue() } : rest));

  function handleSubmit(event) {
    event.preventDefault();
    const assignments = Object.entries(picked).map(([cohort_id, local]) => ({
      cohort_id,
      due_date: new Date(local).toISOString(), // the browser reads datetime-local as local time; send it as UTC
    }));
    dispatch.mutate(
      { title, assignments },
      {
        onSuccess: (created) => {
          setSent({ title, count: created.length });
          setTitle("");
          setPicked({});
        },
      },
    );
  }

  const count = Object.keys(picked).length;

  return (
    <Card title="Dispatch a task" icon={Send}>
      <form onSubmit={handleSubmit} className="space-y-5">
        <label className="block text-sm font-medium text-slate-700">
          Task title
          <input
            required
            maxLength={200}
            placeholder="Week 9: Capstone demo"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            className={inputClasses}
          />
        </label>

        <fieldset>
          <legend className="text-sm font-medium text-slate-700">Cohorts and deadlines</legend>
          <p className="text-xs text-slate-500">Tick each cohort that should get this task and set its own due date and time.</p>
          {cohorts.isPending ? (
            <Spinner />
          ) : (
            <ul className="mt-3 divide-y divide-slate-100 rounded-xl border border-slate-200">
              {cohorts.data?.map((cohort) => {
                const checked = picked[cohort.id] !== undefined;
                return (
                  <li key={cohort.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    <label className="flex min-w-48 flex-1 items-center gap-3 text-sm">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggle(cohort.id)}
                        aria-label={`Send to ${cohort.name}`}
                        className="size-4 rounded accent-indigo-600"
                      />
                      <span>
                        <span className="block font-medium text-slate-900">{cohort.name}</span>
                        <span className="block text-xs text-slate-500">
                          {cohort.trainee_count} trainee{cohort.trainee_count === 1 ? "" : "s"} · becomes task #
                          {nextOrder(cohort.id)}
                        </span>
                      </span>
                    </label>
                    <input
                      type="datetime-local"
                      aria-label={`Due date for ${cohort.name}`}
                      disabled={!checked}
                      required={checked}
                      value={picked[cohort.id] ?? ""}
                      onChange={(event) => setPicked((current) => ({ ...current, [cohort.id]: event.target.value }))}
                      className={`${inputClasses} mt-0 w-auto disabled:bg-slate-50 disabled:text-slate-400`}
                    />
                  </li>
                );
              })}
            </ul>
          )}
        </fieldset>

        {dispatch.isError && <p className="text-sm text-red-600 dark:text-red-400">{errorMessage(dispatch.error)}</p>}
        {sent && (
          <p className="flex items-center gap-1.5 text-sm text-emerald-700">
            <CircleCheck className="size-4" aria-hidden /> Sent "{sent.title}" to {sent.count} cohort{sent.count === 1 ? "" : "s"}.
          </p>
        )}

        <button
          type="submit"
          disabled={count === 0 || dispatch.isPending}
          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {dispatch.isPending ? <Spinner /> : <Send className="size-4" aria-hidden />}
          Dispatch to {count} cohort{count === 1 ? "" : "s"}
        </button>
      </form>
    </Card>
  );
}
