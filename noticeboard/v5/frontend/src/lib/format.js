const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

const UNITS = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];

/** "3 days ago", "yesterday", "just now". */
export function timeAgo(iso) {
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000;
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "just now";
}

/** "Oct 4, 2026, 2:05 PM", for tooltips next to a timeAgo(). */
export function fullDate(iso) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function initials(name) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

/**
 * Parse a date-only string like "2026-10-05" as a *local* date.
 * new Date("2026-10-05") would mean midnight UTC, which shows as Oct 4 anywhere west of UTC.
 */
export function parseDay(isoDay) {
  const [year, month, day] = isoDay.split("-").map(Number);
  return new Date(year, month - 1, day);
}

/** True when two moments fall on the same calendar day in the viewer's timezone. */
export function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** "05/10/2026" for a timestamp, in the viewer's locale order (day/month in the UK, month/day in the US). */
export function shortDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { day: "2-digit", month: "2-digit", year: "numeric" });
}

/** "23:59" (or "11:59 PM" where that's the local habit). */
export function clockTime(iso) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** "Good morning" before noon, "Good afternoon" until 5 pm, then "Good evening", by the viewer's clock. */
export function greeting(now = new Date()) {
  const hour = now.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}
