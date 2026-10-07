import { HeartPulse, ShieldAlert } from "lucide-react";
import { useCohortHealth } from "../queries";
import { Card, Spinner } from "./ui";

// Full class names so Tailwind finds them. Ring colours use the stroke-* utilities.
const STATUS = {
  healthy: { label: "Healthy", badge: "bg-emerald-100 text-emerald-800", ring: "stroke-emerald-500" },
  watch: { label: "Watch", badge: "bg-amber-100 text-amber-800", ring: "stroke-amber-500" },
  at_risk: { label: "At risk", badge: "bg-red-100 text-red-800", ring: "stroke-red-500" },
  no_data: { label: "No data yet", badge: "bg-slate-100 text-slate-600", ring: "stroke-slate-300" },
};

const percent = (rate) => (rate === null ? "–" : `${Math.round(rate * 100)}%`);

/** One card per cohort: health score ring (60% on-time submissions + 40% notices read) and its parts. */
export default function CohortHealthPanel() {
  const health = useCohortHealth();
  const flagged = health.data?.filter((h) => h.status === "at_risk").length ?? 0;

  return (
    <Card
      title="Cohort health"
      icon={HeartPulse}
      action={
        flagged > 0 && (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-600 px-2.5 py-0.5 text-xs font-semibold text-white">
            <ShieldAlert className="size-3.5" aria-hidden /> {flagged} at risk
          </span>
        )
      }
    >
      {!health.data ? (
        <Spinner />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {health.data.map((h) => {
            const style = STATUS[h.status];
            return (
              <li
                key={h.cohort.id}
                className={`flex gap-4 rounded-xl border p-4 ${h.status === "at_risk" ? "border-red-300 bg-red-50/50" : "border-slate-200"}`}
              >
                <ScoreRing score={h.score} ringClass={style.ring} />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-slate-900">{h.cohort.name}</p>
                  <span className={`mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${style.badge}`}>{style.label}</span>
                  <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs text-slate-500">
                    <dt>On time</dt>
                    <dd className="text-right font-medium text-slate-800 tabular-nums">{percent(h.on_time_rate)}</dd>
                    <dt>Notices read</dt>
                    <dd className="text-right font-medium text-slate-800 tabular-nums">{percent(h.read_rate)}</dd>
                    <dt>Overdue · stalled</dt>
                    <dd className="text-right font-medium text-slate-800 tabular-nums">
                      {h.overdue} · {h.stalled}
                    </dd>
                  </dl>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-3 text-xs text-slate-500">
        Score = 60% on-time submissions + 40% notices read. Below 60 a cohort is flagged at risk; 60–74 is watch.
      </p>
    </Card>
  );
}

function ScoreRing({ score, ringClass }) {
  return (
    <svg viewBox="0 0 44 44" className="size-16 shrink-0 -rotate-90" role="img" aria-label={score === null ? "No score" : `Score ${score} of 100`}>
      <circle cx="22" cy="22" r="18" fill="none" strokeWidth="5" className="stroke-slate-100" />
      {score !== null && (
        <circle cx="22" cy="22" r="18" fill="none" strokeWidth="5" strokeLinecap="round" pathLength="100" strokeDasharray={`${score} 100`} className={ringClass} />
      )}
      <text x="22" y="22" textAnchor="middle" dominantBaseline="central" className="rotate-90 fill-slate-900 text-[12px] font-semibold" style={{ transformOrigin: "22px 22px" }}>
        {score ?? "–"}
      </text>
    </svg>
  );
}
