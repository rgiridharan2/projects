import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { TASK_STATUSES, monthCounts } from "../lib/tasks";
import { Card, TASK_STATUS, TONE_CLASSES } from "./ui";

const firstOfThisMonth = () => new Date(new Date().getFullYear(), new Date().getMonth(), 1);

/** Four stat cards counting the tasks due in one month, with arrows to step between months. */
export default function MonthlyReview({ milestones, isError }) {
  const [month, setMonth] = useState(firstOfThisMonth);
  const shift = (by) => setMonth((m) => new Date(m.getFullYear(), m.getMonth() + by, 1));
  const counts = milestones ? monthCounts(milestones, month) : null;
  const label = month.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const isThisMonth = month.getTime() === firstOfThisMonth().getTime();

  return (
    <Card
      title="Monthly review"
      icon={CalendarDays}
      action={
        <div className="flex items-center gap-1 text-sm">
          <button onClick={() => shift(-1)} aria-label="Previous month" className="rounded p-1 hover:bg-slate-100">
            <ChevronLeft className="size-4" aria-hidden />
          </button>
          <span className="min-w-28 text-center font-medium text-slate-700">{label}</span>
          <button onClick={() => shift(1)} aria-label="Next month" className="rounded p-1 hover:bg-slate-100">
            <ChevronRight className="size-4" aria-hidden />
          </button>
          {!isThisMonth && (
            <button onClick={() => setMonth(firstOfThisMonth())} className="ml-1 text-xs text-indigo-600 dark:text-indigo-400 hover:underline">
              Today
            </button>
          )}
        </div>
      }
    >
      {isError && <p className="mb-3 text-sm text-red-600 dark:text-red-400">Couldn't load your tasks.</p>}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {TASK_STATUSES.map((status) => {
          const { label: statusLabel, hint, Icon, tone } = TASK_STATUS[status];
          return (
            <div key={status} className={`rounded-2xl p-4 ${TONE_CLASSES[tone].card}`}>
              <span className={`inline-flex rounded-full p-2 ${TONE_CLASSES[tone].icon}`}>
                <Icon className="size-4" aria-hidden />
              </span>
              <p className="mt-3 text-3xl font-semibold">{counts ? counts[status] : "–"}</p>
              <p className="text-sm font-medium">{statusLabel}</p>
              <p className="mt-0.5 text-xs opacity-75">{hint}</p>
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-slate-500">Your tasks due in {label}, by where each one stands.</p>
    </Card>
  );
}
