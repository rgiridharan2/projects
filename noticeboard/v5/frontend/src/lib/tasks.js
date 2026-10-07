// Pure helpers for the trainee pages. Milestones come from GET /api/milestones/mine in sequence order,
// each with status (pending | in_progress | under_review | completed), overdue, and due_date (ISO timestamp).
import { sameDay } from "./format";

export const TASK_STATUSES = ["completed", "pending", "in_progress", "under_review"];

/** Counts per status for milestones due in the given month (any Date inside that month). */
export function monthCounts(milestones, month) {
  const counts = Object.fromEntries(TASK_STATUSES.map((status) => [status, 0]));
  for (const milestone of milestones) {
    const due = new Date(milestone.due_date);
    if (due.getFullYear() === month.getFullYear() && due.getMonth() === month.getMonth()) {
      counts[milestone.status] += 1;
    }
  }
  return counts;
}

/**
 * Not yet submitted and due by the end of the 7th day from today (or already overdue): what needs
 * doing now. Counted in calendar days, so "next Monday 23:59" counts on a Monday afternoon.
 */
export function pendingNow(milestones, now = new Date()) {
  const horizon = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 8); // midnight after day 7
  return milestones.filter((m) => m.status === "pending" && new Date(m.due_date) < horizon);
}

/** The next task needing the trainee's action: the first in sequence not submitted yet or sent back. */
export function activeMilestone(milestones) {
  return milestones.find((m) => m.status === "pending" || m.status === "in_progress") ?? null;
}

/**
 * Which due-date badge a task gets (Phase 4 brief): "overdue" (red), "today" (amber), "later" (green),
 * or "submitted" (neutral) once it's handed in. "overdue" comes from the server, which uses the same
 * rule as the manager's matrix: deadline passed and nothing submitted.
 */
export function dueState(milestone, now = new Date()) {
  if (milestone.overdue) return "overdue";
  if (milestone.status === "completed" || milestone.status === "under_review") return "submitted";
  const due = new Date(milestone.due_date);
  if (sameDay(due, now)) return "today";
  return due > now ? "later" : "past"; // "past": deadline gone but work is in progress (stalled), so not "overdue"
}
