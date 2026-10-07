import { Moon, Sun } from "lucide-react";
import { useAppTheme } from "../theme/AppThemeContext";

/** A sun/moon switch. role="switch" + aria-checked so screen readers announce it as on/off. */
export default function ThemeToggle() {
  const { theme, toggleTheme } = useAppTheme();
  const dark = theme === "dark";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label="Dark mode"
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
      onClick={toggleTheme}
      className="relative inline-flex h-8 w-14 shrink-0 items-center rounded-full border border-slate-200 bg-slate-100 transition-colors"
    >
      <Sun className="absolute left-1.5 size-4 text-amber-500" aria-hidden />
      <Moon className="absolute right-1.5 size-4 text-indigo-400" aria-hidden />
      <span
        className={`relative z-10 inline-block size-6 rounded-full bg-surface shadow ring-1 ring-slate-200 transition-transform duration-200 ${
          dark ? "translate-x-7" : "translate-x-1"
        }`}
      />
    </button>
  );
}
