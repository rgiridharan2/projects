import { CalendarCheck, CalendarClock, CircleCheck, Clock, Eye, Hourglass, LoaderCircle, OctagonAlert, RotateCw, Siren } from "lucide-react";
import { clockTime, initials, shortDate } from "../lib/format";
import { dueState } from "../lib/tasks";

const STATUS = {
  on_track: { label: "On track", Icon: CircleCheck, classes: "bg-emerald-50 text-emerald-700 ring-emerald-600/20" },
  needs_review: { label: "Needs review", Icon: Clock, classes: "bg-amber-50 text-amber-800 ring-amber-600/20" },
  stalled: { label: "Stalled", Icon: OctagonAlert, classes: "bg-red-50 text-red-700 ring-red-600/20" },
};

export const inputClasses =
  "mt-1 block w-full rounded-lg border border-slate-300 bg-surface px-3 py-2 text-sm text-slate-900 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/30 focus:outline-none";

export const STATUS_OPTIONS = [
  { value: "needs_review", label: "Ready for review" },
  { value: "on_track", label: "On track" },
  { value: "stalled", label: "Stalled / blocked" },
];

export function StatusPill({ status }) {
  const { label, Icon, classes } = STATUS[status];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${classes}`}>
      <Icon className="size-3.5" aria-hidden />
      {label}
    </span>
  );
}

// Task (milestone) statuses as a trainee sees them. One colour per status, used by pills and stat cards.
export const TASK_STATUS = {
  completed: { label: "Completed", hint: "Signed off", Icon: CircleCheck, tone: "emerald" },
  pending: { label: "Pending", hint: "Not submitted yet", Icon: Hourglass, tone: "amber" },
  in_progress: { label: "In progress", hint: "Blocked or sent back: continue", Icon: RotateCw, tone: "sky" },
  under_review: { label: "Under review", hint: "Waiting for your manager", Icon: Eye, tone: "violet" },
};

// Full class names (not built from the tone string) so Tailwind can find them when it scans the source.
export const TONE_CLASSES = {
  emerald: { pill: "bg-emerald-50 text-emerald-700 ring-emerald-600/20", card: "bg-emerald-50 text-emerald-700", icon: "bg-emerald-100 text-emerald-700" },
  amber: { pill: "bg-amber-50 text-amber-800 ring-amber-600/20", card: "bg-amber-50 text-amber-800", icon: "bg-amber-100 text-amber-700" },
  sky: { pill: "bg-sky-50 text-sky-700 ring-sky-600/20", card: "bg-sky-50 text-sky-800", icon: "bg-sky-100 text-sky-700" },
  violet: { pill: "bg-violet-50 text-violet-700 ring-violet-600/20", card: "bg-violet-50 text-violet-800", icon: "bg-violet-100 text-violet-700" },
};

export function TaskStatusPill({ status }) {
  const { label, Icon, tone } = TASK_STATUS[status];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${TONE_CLASSES[tone].pill}`}>
      <Icon className="size-3.5" aria-hidden />
      {label}
    </span>
  );
}

// Due-date badge colours from the Phase 4 brief: green = due later, amber = due today, red = overdue.
const DUE_BADGE = {
  overdue: { Icon: Siren, classes: "bg-red-50 text-red-700 ring-red-600/25", text: (m) => `Overdue · ${shortDate(m.due_date)}` },
  today: { Icon: CalendarClock, classes: "bg-amber-50 text-amber-800 ring-amber-600/25", text: (m) => `Due today · ${clockTime(m.due_date)}` },
  later: { Icon: CalendarClock, classes: "bg-emerald-50 text-emerald-700 ring-emerald-600/25", text: (m) => `Due ${shortDate(m.due_date)}` },
  past: { Icon: CalendarClock, classes: "bg-slate-50 text-slate-600 ring-slate-500/20", text: (m) => `Was due ${shortDate(m.due_date)}` },
  submitted: { Icon: CalendarCheck, classes: "bg-slate-50 text-slate-500 ring-slate-500/20", text: () => "Submitted" },
};

/** A task's deadline, coloured by urgency. Takes a milestone from /api/milestones/mine. */
export function DueBadge({ milestone }) {
  const { Icon, classes, text } = DUE_BADGE[dueState(milestone)];
  return (
    <span
      title={`Due ${new Date(milestone.due_date).toLocaleString()}`}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ${classes}`}
    >
      <Icon className="size-3.5" aria-hidden /> {text(milestone)}
    </span>
  );
}

export function Avatar({ name, role, size = "md", className = "" }) {
  const sizes = { xs: "size-7 text-[10px]", sm: "size-8 text-xs", md: "size-9 text-sm", lg: "size-12 text-base" };
  const colors = role === "manager" ? "bg-indigo-600 text-white" : "bg-teal-600 text-white";
  return (
    <span
      title={name}
      className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ${sizes[size]} ${colors} ${className}`}
    >
      {initials(name)}
    </span>
  );
}

/** "Manager" or "Trainee · Cloud Native Q4". */
export function roleLabel(role, cohortName) {
  return role === "manager" ? "Manager" : `Trainee${cohortName ? ` · ${cohortName}` : ""}`;
}

export function Card({ title, icon: Icon, action, children }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-surface shadow-sm">
      <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-3.5">
        <h2 className="flex items-center gap-2 font-semibold text-slate-800">
          {Icon && <Icon className="size-4.5 text-slate-500" aria-hidden />}
          {title}
        </h2>
        {action}
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Spinner({ className = "size-4" }) {
  return <LoaderCircle className={`animate-spin ${className}`} aria-hidden />;
}

/** Loading / error / empty states shared by the lists. */
export function QueryState({ query, empty, children }) {
  if (query.isPending)
    return (
      <p className="flex items-center gap-2 py-6 text-sm text-slate-500">
        <Spinner /> Loading…
      </p>
    );
  if (query.isError) return <p className="py-6 text-sm text-red-600 dark:text-red-400">Couldn't load this. {query.error.message}</p>;
  if (query.data.length === 0) return <p className="py-6 text-center text-sm text-slate-500">{empty}</p>;
  return children;
}

/** A row of page-level tabs (segmented control). tabs: [{ id, label, Icon }]. */
export function Tabs({ tabs, active, onChange, label }) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex gap-1 rounded-xl bg-slate-200/70 p-1">
      {tabs.map(({ id, label: tabLabel, Icon }) => (
        <button
          key={id}
          role="tab"
          aria-selected={active === id}
          onClick={() => onChange(id)}
          className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-sm font-medium transition ${
            active === id ? "bg-surface text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <Icon className="size-4" aria-hidden /> {tabLabel}
        </button>
      ))}
    </div>
  );
}
