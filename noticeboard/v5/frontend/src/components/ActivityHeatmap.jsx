import { Flame } from "lucide-react";
import { heatmapWeeks, weeklyStreaks } from "../lib/activity";
import { useMySubmissions } from "../queries";
import { Card, Spinner } from "./ui";

// Intensity levels use emerald-500 at different opacities: 500 is the same in both themes (see
// theme-dark.css), so "more" always looks stronger, on white or on navy.
const LEVELS = ["bg-slate-100", "bg-emerald-500/30", "bg-emerald-500/60", "bg-emerald-500"];
const level = (count) => Math.min(count, LEVELS.length - 1);
const DAY_LABELS = ["Mon", "", "Wed", "", "Fri", "", ""];

/** The trainee's last 12 weeks of reports as a GitHub-style grid, plus their weekly streak. */
export default function ActivityHeatmap() {
  const submissions = useMySubmissions();

  return (
    <Card title="Your activity" icon={Flame}>
      {!submissions.data ? (
        <Spinner />
      ) : (
        <ActivityBody submissions={submissions.data} />
      )}
    </Card>
  );
}

function ActivityBody({ submissions }) {
  const weeks = heatmapWeeks(submissions);
  const { current, longest } = weeklyStreaks(submissions);
  const inWindow = weeks.flat().reduce((sum, day) => sum + day.count, 0);

  return (
    <div className="flex flex-wrap items-start gap-6">
      <div className="min-w-32">
        <p className="flex items-baseline gap-1.5">
          <span className={`text-4xl font-bold tabular-nums ${current > 0 ? "text-orange-500" : "text-slate-400"}`}>{current}</span>
          <span className="text-sm font-medium text-slate-700">week{current === 1 ? "" : "s"}</span>
        </p>
        <p className="text-sm text-slate-500">{current > 0 ? "reporting streak" : "No streak yet: send a report this week"}</p>
        <dl className="mt-3 space-y-0.5 text-xs text-slate-500">
          <div className="flex justify-between gap-4">
            <dt>Longest streak</dt>
            <dd className="font-medium text-slate-800">{longest} wk</dd>
          </div>
          <div className="flex justify-between gap-4">
            <dt>Reports, last 12 weeks</dt>
            <dd className="font-medium text-slate-800">{inWindow}</dd>
          </div>
        </dl>
      </div>

      <div className="min-w-0 flex-1 overflow-x-auto">
        <div className="flex gap-1" role="img" aria-label={`${inWindow} reports in the last 12 weeks; current streak ${current} weeks`}>
          <div className="mr-1 grid grid-rows-7 gap-1 pt-5 text-[10px] leading-3 text-slate-400">
            {DAY_LABELS.map((label, i) => (
              <span key={i} className="h-3">
                {label}
              </span>
            ))}
          </div>
          {weeks.map((week, w) => {
            const first = week[0].date;
            const showMonth = w === 0 || first.getDate() <= 7; // label the first week of each month
            return (
              <div key={first.getTime()} className="flex flex-col gap-1">
                <span className="h-4 text-[10px] whitespace-nowrap text-slate-400">
                  {showMonth ? first.toLocaleDateString(undefined, { month: "short" }) : ""}
                </span>
                {week.map((day) => (
                  <span
                    key={day.date.getTime()}
                    title={`${day.date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}: ${day.count} report${day.count === 1 ? "" : "s"}`}
                    className={`size-3 rounded-sm ${day.future ? "bg-transparent" : LEVELS[level(day.count)]}`}
                  />
                ))}
              </div>
            );
          })}
        </div>
        <p className="mt-2 flex items-center justify-end gap-1 text-[10px] text-slate-400">
          Less
          {LEVELS.map((cls) => (
            <span key={cls} className={`size-3 rounded-sm ${cls}`} />
          ))}
          More
        </p>
      </div>
    </div>
  );
}
