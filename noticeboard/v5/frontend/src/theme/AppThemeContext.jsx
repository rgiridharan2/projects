import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "noticeboard.theme";
const AppThemeContext = createContext(null);

function readStoredTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY); // "light", "dark" or null (never chosen)
  } catch {
    return null; // private windows can block storage; just don't remember the choice
  }
}

/**
 * Light/dark theme. Dark mode is the `dark` class on <html> (Tailwind's class strategy); index.html sets
 * it before first paint, and this context keeps it in sync with the toggle and with localStorage.
 */
export function AppThemeProvider({ children }) {
  const [theme, setThemeState] = useState(() =>
    document.documentElement.classList.contains("dark") ? "dark" : "light",
  );
  const [hasChoice, setHasChoice] = useState(() => readStoredTheme() !== null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  // Until the user picks a theme, follow the operating system as it changes (e.g. at sunset).
  useEffect(() => {
    if (hasChoice) return;
    const query = matchMedia("(prefers-color-scheme: dark)");
    const follow = (event) => setThemeState(event.matches ? "dark" : "light");
    query.addEventListener("change", follow);
    return () => query.removeEventListener("change", follow);
  }, [hasChoice]);

  const setTheme = useCallback((next) => {
    setThemeState(next);
    setHasChoice(true);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // storage unavailable: the theme still applies for this visit
    }
  }, []);

  const value = useMemo(
    () => ({ theme, setTheme, toggleTheme: () => setTheme(theme === "dark" ? "light" : "dark") }),
    [theme, setTheme],
  );
  return <AppThemeContext.Provider value={value}>{children}</AppThemeContext.Provider>;
}

export function useAppTheme() {
  const context = useContext(AppThemeContext);
  if (!context) throw new Error("useAppTheme must be used inside <AppThemeProvider>");
  return context;
}
