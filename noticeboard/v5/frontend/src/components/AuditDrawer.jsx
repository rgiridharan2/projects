import {
  BellRing,
  CalendarPlus,
  CircleCheck,
  FileUp,
  History,
  Megaphone,
  PencilLine,
  Send,
  Siren,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import { useEffect, useId } from "react";
import { clockTime, sameDay, timeAgo } from "../lib/format";
import { useAuditLog } from "../queries";
import { Spinner } from "./ui";

// Icon and colour per action. Unknown actions fall back to a pencil.
const ACTIONS = {
  "submission.signed_off": [CircleCheck, "bg-emerald-100 text-emerald-700"],
  "submission.status_changed": [PencilLine, "bg-sky-100 text-sky-700"],
  "notice.posted": [Megaphone, "bg-indigo-100 text-indigo-700"],
  "milestone.dispatched": [Send, "bg-violet-100 text-violet-700"],
  "reminder.sent": [BellRing, "bg-amber-100 text-amber-800"],
  "reminder.bulk_sent": [BellRing, "bg-amber-100 text-amber-800"],
  "escalation.raised": [Siren, "bg-red-100 text-red-700"],
  "trainees.imported": [FileUp, "bg-teal-100 text-teal-700"],
  "trainee.onboarded": [UserPlus, "bg-teal-100 text-teal-700"],
  "cohort.created": [Users, "bg-teal-100 text-teal-700"],
  "schedule.created": [CalendarPlus, "bg-fuchsia-100 text-fuchsia-700"],
};

function dayHeading(date) {
  const today = new Date();
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
  if (sameDay(date, today)) return "Today";
  if (sameDay(date, yesterday)) return "Yesterday";
  return date.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

/** Slide-out panel listing administrative actions, newest first, grouped by day. Managers only. */
export default function AuditDrawer({ open, onClose }) {
  const log = useAuditLog({ enabled: open });
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open, onClose]);

  if (!open) return null;
  const entries = log.data?.pages.flat() ?? [];

  // Group consecutive entries by calendar day for the section headings.
  const groups = [];
  for (const entry of entries) {
    const heading = dayHeading(new Date(entry.created_at));
    if (groups.at(-1)?.heading !== heading) groups.push({ heading, entries: [] });
    groups.at(-1).entries.push(entry);
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside role="dialog" aria-modal="true" aria-labelledby={titleId} className="slide-in-right flex h-full w-full max-w-md flex-col bg-surface shadow-2xl">
        <header className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <h2 id={titleId} className="flex items-center gap-2 font-semibold text-slate-900">
            <History className="size-5 text-slate-500" aria-hidden /> Activity log
          </h2>
          <button onClick={onClose} aria-label="Close activity log" className="rounded p-1 text-slate-400 hover:text-slate-600">
            <X className="size-5" aria-hidden />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {log.isPending ? (
            <Spinner />
          ) : entries.length === 0 ? (
            <p className="text-sm text-slate-500">No activity yet.</p>
          ) : (
            groups.map((group) => (
              <section key={group.heading} className="mb-5">
                <h3 className="mb-2 text-xs font-semibold tracking-wide text-slate-400 uppercase">{group.heading}</h3>
                <ol className="space-y-3">
                  {group.entries.map((entry) => {
                    const [Icon, tone] = ACTIONS[entry.action] ?? [PencilLine, "bg-slate-100 text-slate-600"];
                    return (
                      <li key={entry.id} className="flex gap-3">
                        <span className={`mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-full ${tone}`}>
                          <Icon className="size-4" aria-hidden />
                        </span>
                        <div className="min-w-0 text-sm">
                          <p className="text-slate-800">{entry.summary}</p>
                          <p className="text-xs text-slate-500" title={new Date(entry.created_at).toLocaleString()}>
                            {entry.actor_name ?? "System"} · {clockTime(entry.created_at)} · {timeAgo(entry.created_at)}
                          </p>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </section>
            ))
          )}
          {log.hasNextPage && (
            <button
              onClick={() => log.fetchNextPage()}
              disabled={log.isFetchingNextPage}
              className="mt-2 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              {log.isFetchingNextPage && <Spinner />} Load older activity
            </button>
          )}
        </div>
      </aside>
    </div>
  );
}
