import { CircleCheck, Clock, LoaderCircle, OctagonAlert } from "lucide-react";
import { initials } from "../lib/format";

const STATUS = {
  on_track: { label: "On track", Icon: CircleCheck, classes: "bg-emerald-50 text-emerald-700 ring-emerald-600/20" },
  needs_review: { label: "Needs review", Icon: Clock, classes: "bg-amber-50 text-amber-800 ring-amber-600/20" },
  stalled: { label: "Stalled", Icon: OctagonAlert, classes: "bg-red-50 text-red-700 ring-red-600/20" },
};

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

export function Avatar({ name, role, size = "md" }) {
  const sizes = { sm: "size-8 text-xs", md: "size-9 text-sm", lg: "size-12 text-base" };
  const colors = role === "manager" ? "bg-indigo-600 text-white" : "bg-teal-600 text-white";
  return (
    <span className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold ${sizes[size]} ${colors}`}>
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
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
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
  if (query.isError) return <p className="py-6 text-sm text-red-600">Couldn't load this. {query.error.message}</p>;
  if (query.data.length === 0) return <p className="py-6 text-center text-sm text-slate-500">{empty}</p>;
  return children;
}
