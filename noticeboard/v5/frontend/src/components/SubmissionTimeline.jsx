import { ExternalLink, History } from "lucide-react";
import { fullDate, timeAgo } from "../lib/format";
import { useMySubmissions } from "../queries";
import { Card, QueryState, Spinner, StatusPill } from "./ui";

const DOT = { on_track: "bg-emerald-500", needs_review: "bg-amber-400", stalled: "bg-red-500" };

export default function SubmissionTimeline() {
  const submissions = useMySubmissions(); // refetches every 15 s, so a manager's review shows up on its own

  return (
    <Card
      title="My submissions"
      icon={History}
      action={submissions.isFetching && !submissions.isPending && <Spinner className="size-4 text-slate-400" />}
    >
      <QueryState query={submissions} empty="No reports yet. Submit one from your active task.">
        <ol className="relative ml-1.5 border-l border-slate-200">
          {submissions.data?.map((s) => (
            <li key={s.id} className="relative pb-5 pl-5 last:pb-0">
              <span
                className={`absolute top-1.5 -left-[5px] size-2.5 rounded-full ring-4 ring-surface ${DOT[s.status]}`}
                aria-hidden
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium text-slate-900">{s.milestone_name}</p>
                <StatusPill status={s.status} />
              </div>
              <p className="text-xs text-slate-400" title={fullDate(s.submitted_at)}>
                {timeAgo(s.submitted_at)}
              </p>
              {s.notes && <p className="mt-1 line-clamp-2 text-sm text-slate-600">{s.notes}</p>}
              {s.asset_url && (
                <a
                  href={s.asset_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-1 inline-flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
                >
                  <ExternalLink className="size-3.5" aria-hidden /> {s.asset_url.replace(/^https?:\/\//, "")}
                </a>
              )}
            </li>
          ))}
        </ol>
      </QueryState>
    </Card>
  );
}
