import { ArrowLeftRight, ChevronDown, ClipboardList, History, LogOut } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { useSwitchOptions } from "../queries";
import AuditDrawer from "./AuditDrawer";
import PasswordModal from "./PasswordModal";
import ThemeToggle from "./ThemeToggle";
import { Avatar, roleLabel } from "./ui";

export default function Header() {
  const { currentUser, logout } = useAuth();
  const options = useSwitchOptions();
  const [menuOpen, setMenuOpen] = useState(false);
  const [target, setTarget] = useState(null); // account picked in the menu, awaiting its password
  const [activityOpen, setActivityOpen] = useState(false);
  const menuRef = useRef(null);

  // Close the menu on any click outside it.
  useEffect(() => {
    if (!menuOpen) return;
    const closeOnOutsideClick = (event) => !menuRef.current?.contains(event.target) && setMenuOpen(false);
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [menuOpen]);

  const cohortName = options.data?.find((o) => o.id === currentUser.id)?.cohort_name;
  const others = options.data?.filter((o) => o.id !== currentUser.id) ?? [];

  return (
    <header className="border-b border-slate-200 bg-surface">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2 font-semibold text-slate-800">
          <ClipboardList className="size-5 text-indigo-600 dark:text-indigo-400" aria-hidden />
          <span className="hidden sm:inline">NoticeBoardTracker</span>
        </div>

        <div className="flex items-center gap-2">
          {/* Current identity */}
          <div className="flex items-center gap-2.5 rounded-full border border-slate-200 py-1 pr-3 pl-1">
            <Avatar name={currentUser.name} role={currentUser.role} size="sm" />
            <div className="hidden leading-tight md:block">
              <p className="text-sm font-medium text-slate-900">{currentUser.name}</p>
              <p className="text-xs text-slate-500">{roleLabel(currentUser.role, cohortName)}</p>
            </div>
          </div>

          {/* Switch user menu */}
          <div className="relative" ref={menuRef}>
            <button
              onClick={() => setMenuOpen((open) => !open)}
              aria-expanded={menuOpen}
              aria-label="Switch user"
              className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              <ArrowLeftRight className="size-4" aria-hidden />
              <span className="hidden sm:inline">Switch user</span>
              <ChevronDown className="size-4 text-slate-400" aria-hidden />
            </button>

            {menuOpen && (
              <ul className="absolute right-0 z-40 mt-2 max-h-96 w-72 overflow-y-auto rounded-xl border border-slate-200 bg-surface p-1 shadow-lg">
                {others.map((option) => (
                  <li key={option.id}>
                    <button
                      onClick={() => {
                        setTarget(option);
                        setMenuOpen(false);
                      }}
                      className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left hover:bg-slate-50"
                    >
                      <Avatar name={option.name} role={option.role} size="sm" />
                      <span className="leading-tight">
                        <span className="block text-sm font-medium text-slate-900">{option.name}</span>
                        <span className="block text-xs text-slate-500">{roleLabel(option.role, option.cohort_name)}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {currentUser.role === "manager" && (
            <button
              onClick={() => setActivityOpen(true)}
              aria-label="Activity log"
              title="Activity log"
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
            >
              <History className="size-4" aria-hidden />
            </button>
          )}
          <ThemeToggle />
          <button
            onClick={logout}
            title="Log out"
            aria-label="Log out"
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-700"
          >
            <LogOut className="size-4" aria-hidden />
          </button>
        </div>
      </div>

      {target && <PasswordModal target={target} onClose={() => setTarget(null)} />}
      <AuditDrawer open={activityOpen} onClose={() => setActivityOpen(false)} />
    </header>
  );
}
