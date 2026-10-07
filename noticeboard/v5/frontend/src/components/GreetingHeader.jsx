import { BellRing, CircleCheck } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { greeting } from "../lib/format";
import { pendingNow } from "../lib/tasks";
import { Avatar } from "./ui";

/** "Good afternoon, Jane" by the viewer's own clock, plus how many tasks need doing now. */
export default function GreetingHeader({ milestones }) {
  const { currentUser } = useAuth();
  const firstName = currentUser.name.split(" ")[0];
  const today = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });

  return (
    <section className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-gradient-to-r from-indigo-600 to-violet-600 p-6 text-white shadow-sm">
      <div className="flex items-center gap-4">
        <Avatar name={currentUser.name} role={currentUser.role} size="lg" className="ring-4 ring-white/25" />
        <div>
          <p className="text-sm text-white/80">{today}</p>
          <h1 className="text-2xl font-semibold">
            {greeting()}, {firstName}
          </h1>
        </div>
      </div>
      {milestones && <PendingAlert milestones={milestones} />}
    </section>
  );
}

function PendingAlert({ milestones }) {
  const pending = pendingNow(milestones);
  const overdue = pending.filter((m) => m.overdue).length;

  if (pending.length === 0) {
    return (
      <p className="inline-flex items-center gap-2 rounded-full bg-white/15 px-4 py-2 text-sm font-medium">
        <CircleCheck className="size-4" aria-hidden /> You're all caught up
      </p>
    );
  }
  return (
    <p className="inline-flex items-center gap-2 rounded-full bg-amber-300 px-4 py-2 text-sm font-semibold text-amber-950">
      <BellRing className="size-4" aria-hidden />
      {pending.length} {pending.length === 1 ? "task is" : "tasks are"} pending now
      {overdue > 0 && <span className="font-normal">· {overdue} overdue</span>}
    </p>
  );
}
