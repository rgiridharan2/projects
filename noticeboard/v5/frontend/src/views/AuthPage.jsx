import { BellRing, ClipboardList, Flag, LayoutDashboard, LogIn, UserPlus } from "lucide-react";
import { useState } from "react";
import { errorMessage } from "../api";
import { parseDay } from "../lib/format";
import { useAuth } from "../auth/AuthContext";
import HeroShowcase from "../components/HeroShowcase";
import ThemeToggle from "../components/ThemeToggle";
import { Spinner, inputClasses } from "../components/ui";
import { usePublicCohorts } from "../queries";

// To use a real screen recording instead of the drawn animation, put e.g. hero-loop.mp4 in
// frontend/public/media/ and set this to "/media/hero-loop.mp4".
const HERO_VIDEO_SRC = null;

// Shown only by `npm run dev`, never in a production build (import.meta.env.DEV is false there).
const DEMO_ACCOUNTS = [
  { label: "Elrond · manager", email: "manager@edtech.com" },
  { label: "Frodo · trainee", email: "frodo.baggins@example.com" },
  { label: "Gollum · trainee", email: "gollum.smeagol@example.com" },
];
const DEMO_PASSWORD = "password123";

/** Logged-out landing page: looping hero on the left, sign in / join cohort card on the right. */
export default function AuthPage() {
  return (
    <div className="relative grid min-h-screen lg:grid-cols-2">
      {/* positioned by a wrapper: the switch is itself position:relative for its icons */}
      <div className="absolute top-4 right-4 z-10">
        <ThemeToggle />
      </div>
      <HeroPane />
      <main className="flex items-center justify-center p-4 sm:p-8">
        <div className="w-full max-w-md">
          <p className="mb-6 flex items-center gap-2 text-lg font-semibold text-slate-800 lg:hidden">
            <ClipboardList className="size-5 text-indigo-600 dark:text-indigo-400" aria-hidden /> NoticeBoardTracker
          </p>
          <AuthCard />
        </div>
      </main>
    </div>
  );
}

function HeroPane() {
  const features = [
    { Icon: BellRing, text: "Urgent notices nobody can miss" },
    { Icon: Flag, text: "Milestones with real due dates" },
    { Icon: LayoutDashboard, text: "Progress your manager sees live" },
  ];
  return (
    <section className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-500 p-10 text-white lg:flex">
      {/* soft background blobs */}
      <div className="absolute -top-24 -left-24 size-80 rounded-full bg-white/10 blur-3xl" aria-hidden />
      <div className="absolute -right-16 -bottom-32 size-96 rounded-full bg-fuchsia-300/20 blur-3xl" aria-hidden />

      <p className="relative flex items-center gap-2 text-lg font-semibold">
        <ClipboardList className="size-5" aria-hidden /> NoticeBoardTracker
      </p>

      <div className="relative py-12">
        {HERO_VIDEO_SRC ? (
          <video
            src={HERO_VIDEO_SRC}
            autoPlay
            loop
            muted
            playsInline
            className="mx-auto w-full max-w-md rounded-2xl shadow-2xl"
          />
        ) : (
          <HeroShowcase />
        )}
      </div>

      <div className="relative">
        <h1 className="text-3xl leading-tight font-semibold">Every notice seen. Every milestone on track.</h1>
        <ul className="mt-5 space-y-2.5 text-white/90">
          {features.map(({ Icon, text }) => (
            <li key={text} className="flex items-center gap-2.5">
              <span className="rounded-lg bg-white/15 p-1.5">
                <Icon className="size-4" aria-hidden />
              </span>
              {text}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function AuthCard() {
  const [tab, setTab] = useState("signin");
  const tabs = [
    { id: "signin", label: "Sign in", Icon: LogIn },
    { id: "signup", label: "Join cohort", Icon: UserPlus },
  ];

  return (
    <div className="rounded-2xl border border-slate-200 bg-surface p-6 shadow-xl shadow-slate-200/60 sm:p-8">
      <div role="tablist" aria-label="Sign in or sign up" className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
        {tabs.map(({ id, label, Icon }) => (
          <button
            key={id}
            role="tab"
            id={`tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`panel-${id}`}
            onClick={() => setTab(id)}
            className={`inline-flex items-center justify-center gap-2 rounded-lg py-2 text-sm font-medium transition ${
              tab === id ? "bg-surface text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            <Icon className="size-4" aria-hidden /> {label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="mt-6">
        {tab === "signin" ? <SignInForm /> : <SignUpForm />}
      </div>
    </div>
  );
}

function SubmitButton({ busy, children }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
    >
      {busy && <Spinner />} {children}
    </button>
  );
}

/** Wraps login/signup so both forms get the same busy and error handling. */
function useSubmit(action) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  async function submit(event, ...args) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await action(...args); // on success AuthContext swaps this page for the dashboard
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }
  return { busy, error, submit };
}

function SignInForm() {
  const { login } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, submit } = useSubmit(login);

  return (
    <form onSubmit={(event) => submit(event, identifier, password)} className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Welcome back</h2>
        <p className="text-sm text-slate-500">Sign in to see your notices and tasks.</p>
      </div>
      <label className="block text-sm font-medium text-slate-700">
        Email or user ID
        <input
          required
          autoComplete="username"
          value={identifier}
          onChange={(event) => setIdentifier(event.target.value)}
          className={inputClasses}
        />
      </label>
      <label className="block text-sm font-medium text-slate-700">
        Password
        <input
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className={inputClasses}
        />
      </label>
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      <SubmitButton busy={busy}>Sign in</SubmitButton>

      {import.meta.env.DEV && (
        <div className="border-t border-slate-100 pt-4">
          <p className="text-xs text-slate-400">Demo accounts (dev builds only): fills in the form</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {DEMO_ACCOUNTS.map((account) => (
              <button
                key={account.email}
                type="button"
                onClick={() => {
                  setIdentifier(account.email);
                  setPassword(DEMO_PASSWORD);
                }}
                className="rounded-full border border-slate-200 px-3 py-1 text-xs font-medium text-slate-600 hover:border-indigo-300 hover:text-indigo-700"
              >
                {account.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </form>
  );
}

function SignUpForm() {
  const { signup } = useAuth();
  const cohorts = usePublicCohorts();
  const [form, setForm] = useState({ name: "", email: "", password: "", cohort_id: "" });
  const update = (field) => (event) => setForm((current) => ({ ...current, [field]: event.target.value }));
  const { busy, error, submit } = useSubmit(signup);

  return (
    <form onSubmit={(event) => submit(event, { ...form, cohort_id: form.cohort_id || null })} className="space-y-4">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">Join your cohort</h2>
        <p className="text-sm text-slate-500">Create a trainee account. Managers are set up by your organisation.</p>
      </div>
      <label className="block text-sm font-medium text-slate-700">
        Full name
        <input required maxLength={100} autoComplete="name" value={form.name} onChange={update("name")} className={inputClasses} />
      </label>
      <label className="block text-sm font-medium text-slate-700">
        Email
        <input
          type="email"
          required
          autoComplete="email"
          value={form.email}
          onChange={update("email")}
          className={inputClasses}
        />
      </label>
      <label className="block text-sm font-medium text-slate-700">
        Password
        <input
          type="password"
          required
          minLength={8}
          maxLength={72}
          autoComplete="new-password"
          value={form.password}
          onChange={update("password")}
          className={inputClasses}
        />
        <span className="mt-1 block text-xs font-normal text-slate-400">At least 8 characters.</span>
      </label>
      <label className="block text-sm font-medium text-slate-700">
        Cohort
        <select value={form.cohort_id} onChange={update("cohort_id")} className={inputClasses}>
          <option value="">I'll be assigned one later</option>
          {cohorts.data?.map((cohort) => (
            <option key={cohort.id} value={cohort.id}>
              {cohort.name} · {cohort.track_type === "solo" ? "solo track" : "group"} · started{" "}
              {parseDay(cohort.start_date).toLocaleDateString(undefined, { day: "numeric", month: "short" })}
            </option>
          ))}
        </select>
        {cohorts.isError && (
          <span className="mt-1 block text-xs font-normal text-red-600 dark:text-red-400">{errorMessage(cohorts.error)}</span>
        )}
      </label>
      {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      <SubmitButton busy={busy}>Create account</SubmitButton>
    </form>
  );
}
