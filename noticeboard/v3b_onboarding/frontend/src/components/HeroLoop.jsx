import { CalendarClock, Check, ClipboardList, MousePointer2, Sparkles, TriangleAlert } from "lucide-react";

/**
 * A 9-second looping "screen recording" of the core flow, drawn in HTML and animated with CSS
 * (keyframes in index.css): an urgent notice arrives, gets acknowledged, then a progress report
 * is signed off. No video file or animation library to download, it stays sharp at any size,
 * and it holds still for people who've asked their OS for reduced motion.
 */
export default function HeroLoop() {
  return (
    <div className="hero-loop relative mx-auto w-[340px] select-none" aria-hidden>
      {/* floating friendly bits around the window */}
      <span className="hero-bob absolute -top-5 -right-6 z-10 inline-flex items-center gap-1 rounded-full bg-white px-3 py-1 text-xs font-semibold text-indigo-700 shadow-lg">
        <CalendarClock className="size-3.5" /> Due Friday
      </span>
      <span className="hero-bob hero-bob-slow absolute -bottom-6 -left-8 z-10 inline-flex items-center gap-2 rounded-full bg-white py-1 pr-3 pl-1 text-xs font-medium text-slate-600 shadow-lg">
        <span className="flex">
          {["bg-teal-500", "bg-amber-400", "bg-fuchsia-500"].map((color, i) => (
            <span key={color} className={`size-6 rounded-full ring-2 ring-white ${color} ${i ? "-ml-2" : ""}`} />
          ))}
        </span>
        Your cohort, in sync
      </span>
      <Sparkles className="hero-twinkle absolute top-24 -left-10 size-6 text-amber-200" />

      {/* the app window */}
      <div className="overflow-hidden rounded-2xl bg-white text-slate-800 shadow-2xl shadow-indigo-950/30">
        <div className="flex items-center gap-1.5 border-b border-slate-100 px-4 py-2.5">
          {["bg-red-300", "bg-amber-300", "bg-emerald-300"].map((color) => (
            <span key={color} className={`size-2.5 rounded-full ${color}`} />
          ))}
          <span className="ml-2 inline-flex items-center gap-1 text-xs font-semibold text-slate-500">
            <ClipboardList className="size-3.5 text-indigo-600" /> NoticeBoardTracker
          </span>
        </div>

        <div className="space-y-3 p-4">
          {/* 1. an urgent notice arrives and gets acknowledged */}
          <div className="hero-notice relative rounded-xl border border-red-200 bg-red-50 p-3">
            <div className="flex items-start gap-2">
              <TriangleAlert className="mt-0.5 size-4 shrink-0 text-red-600" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold">Lab cluster maintenance</p>
                <p className="text-xs text-slate-500">Offline Saturday, 08:00 to 12:00</p>
              </div>
            </div>
            <div className="relative mt-2 ml-6 h-7 w-32">
              <span className="hero-ack-before absolute inset-0 inline-flex items-center justify-center gap-1 rounded-lg bg-red-600 text-xs font-semibold text-white">
                <Check className="size-3.5" /> Acknowledge
              </span>
              <span className="hero-ack-after absolute inset-0 inline-flex items-center justify-center gap-1 rounded-lg bg-emerald-100 text-xs font-semibold text-emerald-700">
                <Check className="size-3.5" /> Acknowledged
              </span>
              <MousePointer2 className="hero-cursor absolute top-3 left-20 size-5 fill-slate-900 text-white drop-shadow" />
            </div>
          </div>

          {/* 2. a progress report goes from "needs review" to signed off */}
          <div className="hero-report rounded-xl border border-slate-200 p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold">Week 3: Kubernetes</p>
              <span className="relative h-5 w-24">
                <span className="hero-pill-before absolute inset-0 inline-flex items-center justify-center rounded-full bg-amber-100 text-[11px] font-semibold text-amber-800">
                  Needs review
                </span>
                <span className="hero-pill-after absolute inset-0 inline-flex items-center justify-center rounded-full bg-emerald-100 text-[11px] font-semibold text-emerald-700">
                  On track ✓
                </span>
              </span>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="hero-progress h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500" />
            </div>
            <p className="mt-1.5 text-[11px] text-slate-400">Milestone progress</p>
          </div>
        </div>
      </div>
    </div>
  );
}
