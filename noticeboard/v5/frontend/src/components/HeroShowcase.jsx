import { Check, ClipboardList, MousePointer2, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";

const FRAME_MS = 5000;

const FRAMES = [
  { title: "Acknowledge urgent notices", Scene: NoticeScene },
  { title: "Log progress on milestones", Scene: ProgressScene },
  { title: "Keep the whole cohort in sync", Scene: CohortScene },
];

const prefersReducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

/**
 * Three-frame product tour for the sign-in page. Each frame plays a short one-shot animation (CSS in
 * index.css); the carousel moves on every 5 s, pauses while hovered or focused, and can be driven
 * with the dots. With reduced motion it never auto-advances and shows each frame's finished state.
 */
export default function HeroShowcase() {
  const [frame, setFrame] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused || prefersReducedMotion()) return;
    const timer = setTimeout(() => setFrame((f) => (f + 1) % FRAMES.length), FRAME_MS);
    return () => clearTimeout(timer);
  }, [frame, paused]);

  const { title, Scene } = FRAMES[frame];
  return (
    <div
      className="mx-auto w-[360px] select-none"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <div className="overflow-hidden rounded-2xl bg-surface text-slate-800 shadow-2xl shadow-black/30" aria-hidden>
        <div className="flex items-center gap-1.5 border-b border-slate-100 px-4 py-2.5">
          {["bg-red-400", "bg-amber-400", "bg-emerald-400"].map((color) => (
            <span key={color} className={`size-2.5 rounded-full ${color}`} />
          ))}
          <span className="ml-2 inline-flex items-center gap-1 text-xs font-semibold text-slate-500">
            <ClipboardList className="size-3.5 text-indigo-500" /> NoticeBoardTracker
          </span>
        </div>
        {/* key={frame} remounts the scene, which restarts its CSS animations */}
        <div key={frame} className="hero-frame h-[220px] p-4">
          <Scene />
        </div>
      </div>

      <div className="mt-5 flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-white" aria-live="polite">
          <span className="mr-2 text-white/60 tabular-nums">{frame + 1}/3</span>
          {title}
        </p>
        <div className="flex gap-1.5" role="tablist" aria-label="Product tour">
          {FRAMES.map((f, i) => (
            <button
              key={f.title}
              role="tab"
              aria-selected={i === frame}
              aria-label={`Show: ${f.title}`}
              onClick={() => setFrame(i)}
              className={`h-2 rounded-full transition-all ${i === frame ? "w-6 bg-white" : "w-2 bg-white/40 hover:bg-white/70"}`}
            >
              {i === frame && !paused && <span className="hero-dot-timer block h-full rounded-full bg-white/50" />}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Frame 1: an urgent notice arrives, the cursor clicks Acknowledge, the badge turns green. */
function NoticeScene() {
  return (
    <div className="hero-pop rounded-xl border border-red-200 bg-red-50 p-3">
      <div className="flex items-start gap-2">
        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-red-600 dark:text-red-400" />
        <div>
          <p className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            Lab cluster maintenance
            <span className="rounded bg-red-600 px-1.5 text-[10px] font-semibold tracking-wide text-white uppercase">Urgent</span>
          </p>
          <p className="text-xs text-slate-500">The shared k8s cluster is offline Saturday 08:00–12:00.</p>
        </div>
      </div>
      <div className="relative mt-4 ml-6 h-8 w-36">
        <span className="hero-ack-before absolute inset-0 inline-flex items-center justify-center gap-1 rounded-lg bg-red-600 text-xs font-semibold text-white">
          <Check className="size-3.5" /> Acknowledge
        </span>
        <span className="hero-ack-after absolute inset-0 inline-flex items-center justify-center gap-1 rounded-lg bg-emerald-100 text-xs font-semibold text-emerald-700">
          <Check className="size-3.5" /> Acknowledged
        </span>
        <MousePointer2 className="hero-cursor absolute top-4 left-24 size-5 fill-slate-900 text-white drop-shadow" />
      </div>
      <p className="hero-late mt-4 text-[11px] text-slate-500">Read receipts go straight to your manager's dashboard.</p>
    </div>
  );
}

/** Frame 2: a milestone report's progress bar fills to 100% and its status flips to On track. */
function ProgressScene() {
  return (
    <div className="hero-pop space-y-3 rounded-xl border border-slate-200 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-semibold text-slate-900">Week 3: Kubernetes</p>
        <span className="relative h-5 w-24">
          <span className="hero-pill-before absolute inset-0 inline-flex items-center justify-center rounded-full bg-amber-100 text-[11px] font-semibold text-amber-800">
            Needs review
          </span>
          <span className="hero-pill-after absolute inset-0 inline-flex items-center justify-center rounded-full bg-emerald-100 text-[11px] font-semibold text-emerald-700">
            On track ✓
          </span>
        </span>
      </div>
      <div>
        <div className="flex justify-between text-[11px] text-slate-500">
          <span>Milestone progress</span>
          <span className="hero-percent tabular-nums" />
        </div>
        <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-slate-100">
          <div className="hero-fill h-full rounded-full bg-gradient-to-r from-indigo-500 to-emerald-500" />
        </div>
      </div>
      <ul className="space-y-1.5 text-xs text-slate-600">
        {["Deployed the app to the lab cluster", "Wrote a Helm chart", "Added liveness probes"].map((item, i) => (
          <li key={item} className="hero-tick flex items-center gap-2" style={{ animationDelay: `${0.6 + i * 0.45}s` }}>
            <span className="inline-flex size-4 items-center justify-center rounded-full bg-emerald-500 text-white">
              <Check className="size-3" />
            </span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Frame 3: the cohort's avatars gather and its health metrics count up. */
function CohortScene() {
  const people = [
    ["JD", "bg-teal-500"],
    ["MC", "bg-indigo-500"],
    ["PP", "bg-fuchsia-500"],
    ["TO", "bg-amber-500"],
    ["SR", "bg-sky-500"],
    ["LM", "bg-emerald-500"],
  ];
  const metrics = [
    ["On time", "92%"],
    ["Notices read", "88%"],
    ["Overdue", "1"],
  ];
  return (
    <div className="hero-pop rounded-xl border border-slate-200 p-3">
      <div className="flex items-center gap-4">
        {/* health ring: the stroke draws itself from 0 to 86% */}
        <svg viewBox="0 0 44 44" className="size-20 shrink-0 -rotate-90">
          <circle cx="22" cy="22" r="18" fill="none" strokeWidth="5" className="stroke-slate-100" />
          <circle cx="22" cy="22" r="18" fill="none" strokeWidth="5" strokeLinecap="round" pathLength="100" className="hero-ring stroke-emerald-500" />
          <text x="22" y="22" className="hero-ring-label rotate-90 fill-slate-900 text-[11px] font-semibold" style={{ transformOrigin: "22px 22px" }} textAnchor="middle" dominantBaseline="central">
            86
          </text>
        </svg>
        <div>
          <p className="text-sm font-semibold text-slate-900">Your cohort, in sync</p>
          <p className="text-[11px] text-slate-500">Cloud Native Q4 · health score</p>
          <div className="mt-2 flex">
            {people.map(([initials, color], i) => (
              <span
                key={initials}
                className={`hero-avatar inline-flex size-7 items-center justify-center rounded-full text-[10px] font-semibold text-white ring-2 ring-surface ${color} ${i ? "-ml-2" : ""}`}
                style={{ animationDelay: `${0.2 + i * 0.15}s` }}
              >
                {initials}
              </span>
            ))}
          </div>
        </div>
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-2">
        {metrics.map(([label, value], i) => (
          <div key={label} className="hero-tick rounded-lg bg-slate-50 px-2 py-1.5 text-center" style={{ animationDelay: `${1.2 + i * 0.3}s` }}>
            <dd className="text-sm font-semibold text-slate-900">{value}</dd>
            <dt className="text-[10px] text-slate-500">{label}</dt>
          </div>
        ))}
      </dl>
    </div>
  );
}
