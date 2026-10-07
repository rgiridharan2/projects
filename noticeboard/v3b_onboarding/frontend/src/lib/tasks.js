// Pure helpers for the trainee dashboard. Milestones come from GET /api/milestones/mine,
// already sorted by due date, each with status: pending | in_progress | under_review | completed.
import { daysUntil, parseDay } from "./format";

export const TASK_STATUSES = ["completed", "pending", "in_progress", "under_review"];

/** Counts per status for milestones due in the given month (any Date inside that month). */
export function monthCounts(milestones, month) {
  const counts = Object.fromEntries(TASK_STATUSES.map((status) => [status, 0]));
  for (const milestone of milestones) {
    const due = parseDay(milestone.due_date);
    if (due.getFullYear() === month.getFullYear() && due.getMonth() === month.getMonth()) {
      counts[milestone.status] += 1;
    }
  }
  return counts;
}

/** Not yet submitted and due within the next 7 days (or already overdue): what needs doing now. */
export function pendingNow(milestones) {
  return milestones.filter((m) => m.status === "pending" && daysUntil(m.due_date) <= 7);
}

/** The next task needing the trainee's action: the soonest one not submitted yet or sent back. */
export function activeMilestone(milestones) {
  return milestones.find((m) => m.status === "pending" || m.status === "in_progress") ?? null;
}
