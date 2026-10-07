import { AlarmClock, Send, X } from "lucide-react";
import { shortDate, timeAgo } from "../lib/format";
import { useDismissReminder, useMyReminders } from "../queries";

/** A manager's nudges about overdue tasks. Submitting the task (or dismissing) clears one. */
export default function ReminderBanner({ onSubmit }) {
  const reminders = useMyReminders();
  const dismiss = useDismissReminder();
  if (!reminders.data?.length) return null;

  return (
    <section aria-label="Reminders from your manager" className="space-y-2">
      {reminders.data.map((reminder) => (
        <div
          key={reminder.id}
          className="flex flex-wrap items-center gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3"
        >
          <span className="rounded-full bg-red-100 p-2 text-red-600 dark:text-red-400">
            <AlarmClock className="size-4" aria-hidden />
          </span>
          <p className="min-w-0 flex-1 text-sm text-red-900">
            <span className="font-semibold">{reminder.sender_name}</span> sent a reminder:{" "}
            <span className="font-semibold">{reminder.milestone_title}</span> was due {shortDate(reminder.due_date)} and
            hasn't been submitted yet.
            <span className="block text-xs text-red-700/80">Sent {timeAgo(reminder.created_at)}</span>
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => onSubmit(reminder.milestone_id)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-500"
            >
              <Send className="size-3.5" aria-hidden /> Submit now
            </button>
            <button
              onClick={() => dismiss.mutate(reminder.id)}
              aria-label={`Dismiss reminder about ${reminder.milestone_title}`}
              className="rounded-lg p-1.5 text-red-400 hover:bg-red-100 hover:text-red-700"
            >
              <X className="size-4" aria-hidden />
            </button>
          </div>
        </div>
      ))}
    </section>
  );
}
