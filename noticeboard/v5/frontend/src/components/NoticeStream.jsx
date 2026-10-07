import { Check, CircleCheck, Megaphone, TriangleAlert } from "lucide-react";
import { errorMessage } from "../api";
import { fullDate, timeAgo } from "../lib/format";
import { useAcknowledgeNotice, useMyNotices } from "../queries";
import { Card, QueryState } from "./ui";

export default function NoticeStream() {
  const notices = useMyNotices();
  const acknowledge = useAcknowledgeNotice();
  const unread = notices.data?.filter((n) => !n.read_at).length ?? 0;

  return (
    <Card
      title="Notices"
      icon={Megaphone}
      action={
        unread > 0 && (
          <span className="rounded-full bg-indigo-600 px-2 py-0.5 text-xs font-semibold text-white">{unread} new</span>
        )
      }
    >
      {acknowledge.isError && (
        <p className="mb-3 text-sm text-red-600 dark:text-red-400">Couldn't acknowledge: {errorMessage(acknowledge.error)}</p>
      )}
      <QueryState query={notices} empty="No notices yet.">
        <ul className="space-y-3">
          {notices.data?.map((notice) => (
            <NoticeCard key={notice.id} notice={notice} onAcknowledge={() => acknowledge.mutate(notice.id)} />
          ))}
        </ul>
      </QueryState>
    </Card>
  );
}

function NoticeCard({ notice, onAcknowledge }) {
  const urgent = notice.priority === "urgent";
  const read = Boolean(notice.read_at);

  // Unread urgent notices are red; once acknowledged they calm down to amber.
  const tone = urgent
    ? read
      ? "border-amber-200 bg-amber-50/60"
      : "border-red-300 bg-red-50 ring-1 ring-red-200"
    : read
      ? "border-slate-200 bg-slate-50/60"
      : "border-slate-200 bg-surface";

  return (
    <li className={`rounded-lg border p-4 ${tone}`}>
      {/* Phones: the button sits under the text. sm and up: it gets its own column on the right. */}
      <div className="grid grid-cols-[auto_1fr] items-start gap-3 sm:grid-cols-[auto_1fr_auto]">
        {urgent ? (
          <TriangleAlert className={`mt-0.5 size-5 shrink-0 ${read ? "text-amber-500" : "text-red-600 dark:text-red-400"}`} aria-hidden />
        ) : (
          <Megaphone className="mt-0.5 size-5 shrink-0 text-slate-400" aria-hidden />
        )}

        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className={`font-medium ${read ? "text-slate-600" : "text-slate-900"}`}>{notice.title}</h3>
            {urgent && (
              <span
                className={`rounded px-1.5 py-0.5 text-[11px] font-semibold tracking-wide uppercase ${
                  read ? "bg-amber-100 text-amber-800" : "bg-red-600 text-white"
                }`}
              >
                Urgent
              </span>
            )}
          </div>
          <p className={`mt-1 text-sm ${read ? "text-slate-500" : "text-slate-700"}`}>{notice.body}</p>
          <p className="mt-2 text-xs text-slate-400" title={fullDate(notice.created_at)}>
            {notice.target_cohort_id ? "Your cohort" : "All trainees"} · {timeAgo(notice.created_at)}
          </p>
        </div>

        <div className="col-start-2 sm:col-start-auto">
          {read ? (
            <span
              className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700"
              title={fullDate(notice.read_at)}
            >
              <CircleCheck className="size-4" aria-hidden /> Acknowledged
            </span>
          ) : (
            <button
              onClick={onAcknowledge}
              className={`inline-flex items-center gap-1 rounded-lg px-3 py-1.5 text-sm font-medium text-white ${
                urgent ? "bg-red-600 hover:bg-red-500" : "bg-indigo-600 hover:bg-indigo-500"
              }`}
            >
              <Check className="size-4" aria-hidden /> Acknowledge
            </button>
          )}
        </div>
      </div>
    </li>
  );
}
