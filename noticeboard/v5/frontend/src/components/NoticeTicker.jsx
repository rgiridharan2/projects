import { Check, Siren, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAcknowledgeNotice, useMyNotices } from "../queries";

const MAX_TOASTS = 3;

/**
 * Live alerts for urgent notices. useMyNotices polls every 20 s; anything urgent and unread that wasn't
 * in the feed before pops up as a toast in the corner. Notices already there when the page loads don't
 * pop up (they're in the notice stream), only ones that arrive while you're here.
 */
export default function NoticeTicker() {
  const notices = useMyNotices();
  const acknowledge = useAcknowledgeNotice();
  const seen = useRef(null); // ids we've already accounted for; null until the first load
  const [toasts, setToasts] = useState([]);

  useEffect(() => {
    if (!notices.data) return;
    if (seen.current === null) {
      seen.current = new Set(notices.data.map((n) => n.id)); // first load: remember, don't alert
      return;
    }
    const fresh = notices.data.filter((n) => !seen.current.has(n.id));
    fresh.forEach((n) => seen.current.add(n.id));
    const urgent = fresh.filter((n) => n.priority === "urgent" && !n.read_at);
    if (urgent.length) setToasts((current) => [...urgent, ...current].slice(0, MAX_TOASTS));
  }, [notices.data]);

  const close = (id) => setToasts((current) => current.filter((t) => t.id !== id));

  return (
    <div aria-live="assertive" className="pointer-events-none fixed right-4 bottom-4 z-40 flex w-[calc(100%-2rem)] max-w-sm flex-col gap-3">
      {toasts.map((notice) => (
        <div key={notice.id} role="alert" className="slide-in-right pointer-events-auto rounded-xl border border-red-200 bg-surface p-4 shadow-xl ring-1 ring-red-100">
          <div className="flex items-start gap-3">
            <span className="rounded-full bg-red-100 p-2 text-red-600 dark:text-red-400">
              <Siren className="size-4" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold tracking-wide text-red-600 dark:text-red-400 uppercase">Urgent notice</p>
              <p className="font-semibold text-slate-900">{notice.title}</p>
              <p className="mt-0.5 line-clamp-2 text-sm text-slate-600">{notice.body}</p>
              <button
                onClick={() => {
                  acknowledge.mutate(notice.id);
                  close(notice.id);
                }}
                className="mt-2 inline-flex items-center gap-1 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-500"
              >
                <Check className="size-3.5" aria-hidden /> Acknowledge
              </button>
            </div>
            <button onClick={() => close(notice.id)} aria-label="Dismiss" className="rounded p-1 text-slate-400 hover:text-slate-600">
              <X className="size-4" aria-hidden />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
