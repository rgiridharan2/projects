import { CalendarClock, CircleCheck, Send, Target, Users } from "lucide-react";
import { daysUntil, shortDay } from "../lib/format";
import { activeMilestone } from "../lib/tasks";
import { useMyCohort } from "../queries";
import { Avatar, Card, Spinner, TaskStatusPill } from "./ui";

const MAX_FACES = 5;

/** The next task needing action, its due date, who else in the cohort has it, and a submit button. */
export default function ActiveTaskCard({ milestones, onSubmit }) {
  const myCohort = useMyCohort();
  const task = milestones ? activeMilestone(milestones) : null;

  return (
    <Card title="Active task" icon={Target}>
      {!milestones || myCohort.isPending ? (
        <Spinner />
      ) : !myCohort.data?.cohort ? (
        <p className="text-sm text-slate-500">You're not in a cohort yet. A manager will assign you one and your tasks will appear here.</p>
      ) : !task ? (
        <p className="flex items-center gap-2 text-sm text-emerald-700">
          <CircleCheck className="size-4" aria-hidden /> All caught up: every task has been submitted.
        </p>
      ) : (
        <div className="space-y-4">
          <div>
            <p className="text-xs font-medium tracking-wide text-slate-400 uppercase">{myCohort.data.cohort.name}</p>
            <h3 className="mt-1 text-lg font-semibold text-slate-900">{task.title}</h3>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <DueTag due={task.due_date} />
              <TaskStatusPill status={task.status} />
            </div>
          </div>

          <Peers peers={myCohort.data.peers} />

          <button
            onClick={() => onSubmit(task)}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            <Send className="size-4" aria-hidden /> {task.status === "in_progress" ? "Submit an update" : "Submit report"}
          </button>
        </div>
      )}
    </Card>
  );
}

function DueTag({ due }) {
  const days = daysUntil(due);
  const [text, classes] =
    days < 0
      ? [`Overdue · ${shortDay(due)}`, "bg-red-50 text-red-700 ring-red-600/20"]
      : days === 0
        ? [`Due today · ${shortDay(due)}`, "bg-amber-50 text-amber-800 ring-amber-600/20"]
        : [`Due ${shortDay(due)}`, "bg-slate-50 text-slate-700 ring-slate-500/20"];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${classes}`}>
      <CalendarClock className="size-3.5" aria-hidden /> {text}
    </span>
  );
}

function Peers({ peers }) {
  if (peers.length === 0) {
    return <p className="text-sm text-slate-500">Solo track: this one's just you.</p>;
  }
  const extra = peers.length - MAX_FACES;
  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-slate-500">
        <Users className="size-3.5" aria-hidden /> Also working on this
      </p>
      <div className="flex items-center">
        {peers.slice(0, MAX_FACES).map((peer, i) => (
          <Avatar key={peer.id} name={peer.name} role="trainee" size="xs" className={`ring-2 ring-white ${i ? "-ml-2" : ""}`} />
        ))}
        {extra > 0 && (
          <span className="-ml-2 inline-flex size-7 items-center justify-center rounded-full bg-slate-200 text-[10px] font-semibold text-slate-600 ring-2 ring-white">
            +{extra}
          </span>
        )}
        <span className="ml-3 text-sm text-slate-600">
          {peers.length} {peers.length === 1 ? "peer" : "peers"}
        </span>
      </div>
    </div>
  );
}
