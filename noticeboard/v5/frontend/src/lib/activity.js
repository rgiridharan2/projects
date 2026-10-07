// Activity heatmap and streak maths for the trainee overview. Pure functions, no React.
import { sameDay } from "./format";

export const WEEKS_SHOWN = 12;

/** Monday 00:00 of the week containing `date` (local time). */
export function startOfWeek(date) {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); // getDay(): Sunday = 0, so shift to Monday = 0
  return d;
}

const addDays = (date, days) => new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);

/**
 * The last 12 weeks as columns of 7 days (Mon..Sun), oldest first, each day with how many reports
 * were submitted on it. Days after today are marked `future` so they render empty.
 */
export function heatmapWeeks(submissions, today = new Date()) {
  const counts = new Map();
  for (const s of submissions) {
    const d = new Date(s.submitted_at);
    const key = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const firstMonday = addDays(startOfWeek(today), -7 * (WEEKS_SHOWN - 1));
  return Array.from({ length: WEEKS_SHOWN }, (_, w) =>
    Array.from({ length: 7 }, (_, d) => {
      const date = addDays(firstMonday, w * 7 + d);
      return { date, count: counts.get(date.getTime()) ?? 0, future: date > today && !sameDay(date, today) };
    }),
  );
}

/**
 * Weekly streaks: consecutive calendar weeks with at least one report. The current streak counts back
 * from this week, or from last week if nothing has been sent yet this week (the streak isn't broken
 * until this week ends empty).
 */
export function weeklyStreaks(submissions, today = new Date()) {
  const weeks = new Set(submissions.map((s) => startOfWeek(new Date(s.submitted_at)).getTime()));
  const weekBefore = (t) => addDays(new Date(t), -7).getTime();

  let cursor = startOfWeek(today).getTime();
  if (!weeks.has(cursor)) cursor = weekBefore(cursor);
  let current = 0;
  while (weeks.has(cursor)) {
    current += 1;
    cursor = weekBefore(cursor);
  }

  let longest = 0;
  for (const week of weeks) {
    if (weeks.has(weekBefore(week))) continue; // only count from the first week of each run
    let length = 0;
    for (let t = week; weeks.has(t); t = addDays(new Date(t), 7).getTime()) length += 1;
    longest = Math.max(longest, length);
  }
  return { current, longest };
}
