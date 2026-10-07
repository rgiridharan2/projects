import { CalendarDays, ChevronLeft, ChevronRight, Clock, ListChecks } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Card, DueBadge, Spinner, TaskStatusPill } from "../components/ui";
import { clockTime, sameDay } from "../lib/format";
import { assignLanes, minutesIntoDay, visibleHours } from "../lib/timeline";
import { useMyMilestones, useMySchedule } from "../queries";

const HOUR_PX = 56; // height of one hour on the timeline

// One colour per module, picked by its milestone_order, so a week's sessions share a colour.
const MODULE_COLOURS = [
  "border-indigo-400 bg-indigo-50 text-indigo-950",
  "border-teal-400 bg-teal-50 text-teal-950",
  "border-amber-400 bg-amber-50 text-amber-950",
  "border-fuchsia-400 bg-fuchsia-50 text-fuchsia-950",
  "border-sky-400 bg-sky-50 text-sky-950",
  "border-lime-500 bg-lime-50 text-lime-950",
];

const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const firstOfMonth = (d, shift = 0) => new Date(d.getFullYear(), d.getMonth() + shift, 1);
const monthName = (d, style) => d.toLocaleDateString(undefined, { month: style });

/** Agenda: a month header with a scrollable day strip, then the chosen day's hourly timeline. */
export default function AgendaView({ onSubmit }) {
  const [selected, setSelected] = useState(() => startOfDay(new Date()));
  const month = firstOfMonth(selected);
  const schedule = useMySchedule(month, firstOfMonth(selected, 1)); // one month of sessions at a time
  const milestones = useMyMilestones();

  // Everything the strip and timeline need, with ISO strings turned into Dates once.
  const blocks = useMemo(
    () => (schedule.data ?? []).map((b) => ({ ...b, start: new Date(b.starts_at), end: new Date(b.ends_at) })),
    [schedule.data],
  );
  const moduleOrder = Object.fromEntries((milestones.data ?? []).map((m) => [m.id, m]));

  const goToMonth = (shift) => setSelected(firstOfMonth(selected, shift));

  return (
    // min-w-0: grid items won't shrink below their content by default, and the 31-day strip is wide.
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="min-w-0 space-y-4 lg:col-span-2">
        <Card title="Agenda" icon={CalendarDays}>
          {/* Day selector header: previous / current / next month, then the day carousel */}
          <div className="flex items-center justify-between gap-2">
            <button onClick={() => goToMonth(-1)} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-slate-500 hover:bg-slate-100">
              <ChevronLeft className="size-4" aria-hidden /> {monthName(firstOfMonth(selected, -1), "short")}
            </button>
            <h2 className="text-lg font-semibold text-slate-900">
              {monthName(month, "long")} {month.getFullYear()}
            </h2>
            <button onClick={() => goToMonth(1)} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-slate-500 hover:bg-slate-100">
              {monthName(firstOfMonth(selected, 1), "short")} <ChevronRight className="size-4" aria-hidden />
            </button>
          </div>
          <DayStrip month={month} selected={selected} onSelect={setSelected} blocks={blocks} milestones={milestones.data ?? []} />
        </Card>

        <DayTimeline
          day={selected}
          loading={schedule.isPending}
          blocks={blocks.filter((b) => sameDay(b.start, selected))}
          deadlines={(milestones.data ?? []).filter((m) => sameDay(new Date(m.due_date), selected))}
          moduleOrder={moduleOrder}
        />
      </div>

      <TaskList milestones={milestones.data} onPick={(m) => setSelected(startOfDay(new Date(m.due_date)))} onSubmit={onSubmit} />
    </div>
  );
}

/** Horizontal, scrollable row of date tabs ("Wed 2 Sep") for every day of the month. */
function DayStrip({ month, selected, onSelect, blocks, milestones }) {
  const stripRef = useRef(null);
  const today = new Date();
  const days = Array.from(
    { length: new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate() },
    (_, i) => new Date(month.getFullYear(), month.getMonth(), i + 1),
  );

  // Keep the selected day in view without scrolling the page itself.
  useEffect(() => {
    const chip = stripRef.current?.querySelector('[aria-selected="true"]');
    if (chip) stripRef.current.scrollTo({ left: chip.offsetLeft - stripRef.current.clientWidth / 2 + chip.clientWidth / 2, behavior: "smooth" });
  }, [selected]);

  return (
    <div ref={stripRef} role="tablist" aria-label="Day" className="-mx-1 mt-4 flex gap-2 overflow-x-auto px-1 pb-2">
      {days.map((day) => {
        const isSelected = sameDay(day, selected);
        const isToday = sameDay(day, today);
        const hasSessions = blocks.some((b) => sameDay(b.start, day));
        const hasDeadline = milestones.some((m) => sameDay(new Date(m.due_date), day));
        return (
          <button
            key={day.getDate()}
            role="tab"
            aria-selected={isSelected}
            onClick={() => onSelect(day)}
            className={`flex w-14 shrink-0 flex-col items-center rounded-xl border py-2 transition ${
              isSelected
                ? "border-indigo-600 bg-indigo-600 text-white shadow-sm"
                : `bg-surface text-slate-700 hover:border-indigo-300 ${isToday ? "border-indigo-400" : "border-slate-200"}`
            }`}
          >
            <span className={`text-[11px] font-medium uppercase ${isSelected ? "text-white/80" : "text-slate-400"}`}>
              {day.toLocaleDateString(undefined, { weekday: "short" })}
            </span>
            <span className="text-lg leading-tight font-semibold">{day.getDate()}</span>
            <span className={`text-[11px] ${isSelected ? "text-white/80" : "text-slate-400"}`}>{monthName(day, "short")}</span>
            {/* markers: a dot for sessions, a red dot for a deadline */}
            <span className="mt-1 flex h-1.5 gap-1">
              {hasSessions && <span className={`size-1.5 rounded-full ${isSelected ? "bg-surface" : "bg-indigo-400"}`} />}
              {hasDeadline && <span className="size-1.5 rounded-full bg-red-500" />}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** The chosen day: deadlines on top, then sessions laid out against the hours of the day. */
function DayTimeline({ day, loading, blocks, deadlines, moduleOrder }) {
  const now = new Date();
  const { start, end } = visibleHours(blocks);
  const laidOut = assignLanes(blocks);
  const title = day.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
  const nowOffset = (minutesIntoDay(now) - start * 60) * (HOUR_PX / 60);
  const showNow = sameDay(day, now) && nowOffset >= 0 && nowOffset <= (end - start) * HOUR_PX;

  return (
    <Card title={title} icon={Clock}>
      {deadlines.length > 0 && (
        <ul className="mb-4 space-y-2">
          {deadlines.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-dashed border-slate-300 px-3 py-2 text-sm">
              <span className="font-medium text-slate-800">Deadline: {m.title}</span>
              <DueBadge milestone={m} />
            </li>
          ))}
        </ul>
      )}

      {loading ? (
        <Spinner />
      ) : blocks.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-500">Nothing scheduled this day.</p>
      ) : (
        <div className="relative grid grid-cols-[3.5rem_1fr]" style={{ height: (end - start) * HOUR_PX }}>
          {/* hour labels and grid lines */}
          {Array.from({ length: end - start }, (_, i) => (
            <div key={i} className="col-span-2 grid grid-cols-subgrid border-t border-slate-100" style={{ height: HOUR_PX }}>
              <span className="-mt-2.5 bg-surface pr-2 text-right text-xs text-slate-400 tabular-nums">
                {String(start + i).padStart(2, "0")}:00
              </span>
            </div>
          ))}

          {/* sessions */}
          <div className="absolute inset-y-0 right-0 left-14">
            {laidOut.map((block) => {
              const top = (minutesIntoDay(block.start) - start * 60) * (HOUR_PX / 60);
              const height = Math.max(((block.end - block.start) / 60_000) * (HOUR_PX / 60), 24);
              const module = moduleOrder[block.milestone_id];
              const colour = MODULE_COLOURS[((module?.milestone_order ?? 1) - 1) % MODULE_COLOURS.length];
              const ongoing = block.start <= now && now < block.end;
              const past = block.end <= now;
              return (
                <div
                  key={block.id}
                  className={`absolute overflow-hidden rounded-lg border-l-4 px-2.5 py-1.5 text-xs shadow-sm ${colour} ${past ? "opacity-55" : ""} ${ongoing ? "ring-2 ring-indigo-500" : ""}`}
                  style={{
                    top,
                    height,
                    left: `calc(${(100 / block.lanes) * block.lane}% + 4px)`,
                    width: `calc(${100 / block.lanes}% - 8px)`,
                  }}
                >
                  <p className="flex items-center gap-1.5 font-semibold">
                    <span className="truncate">{block.title}</span>
                    {ongoing && <span className="shrink-0 rounded bg-indigo-600 px-1.5 text-[10px] text-white uppercase">Now</span>}
                  </p>
                  <p className="tabular-nums opacity-75">
                    {clockTime(block.starts_at)} – {clockTime(block.ends_at)}
                  </p>
                  {module && height > 48 && <p className="truncate opacity-75">{module.title}</p>}
                </div>
              );
            })}
          </div>

          {/* current time */}
          {showNow && (
            <div className="pointer-events-none absolute right-0 left-12 flex items-center" style={{ top: nowOffset }}>
              <span className="size-2.5 rounded-full bg-red-500" />
              <span className="h-px flex-1 bg-red-500" />
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

/** Every task with its due-date badge; clicking one jumps the agenda to its deadline. */
function TaskList({ milestones, onPick, onSubmit }) {
  return (
    <Card title="Your tasks" icon={ListChecks}>
      {!milestones ? (
        <Spinner />
      ) : milestones.length === 0 ? (
        <p className="text-sm text-slate-500">No tasks assigned yet.</p>
      ) : (
        <ol className="space-y-2">
          {milestones.map((m) => {
            const actionable = m.status === "pending" || m.status === "in_progress";
            return (
              <li key={m.id} className="rounded-xl border border-slate-200 p-3 hover:border-indigo-300">
                <button onClick={() => onPick(m)} className="w-full text-left">
                  <p className="text-sm font-medium text-slate-900">
                    <span className="mr-1.5 text-slate-400 tabular-nums">#{m.milestone_order}</span>
                    {m.title}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <DueBadge milestone={m} />
                    <TaskStatusPill status={m.status} />
                  </div>
                </button>
                {actionable && (
                  <button onClick={() => onSubmit(m.id)} className="mt-2 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline">
                    Submit report →
                  </button>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
