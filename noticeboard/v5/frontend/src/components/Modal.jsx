import { X } from "lucide-react";
import { useEffect, useId } from "react";

/** Centered dialog over a dimmed backdrop. Esc or a backdrop click calls onClose. */
export default function Modal({ title, icon: Icon, onClose, children, width = "max-w-sm" }) {
  const titleId = useId();

  useEffect(() => {
    const closeOnEscape = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`max-h-[90vh] w-full overflow-y-auto rounded-2xl bg-surface p-6 shadow-xl ${width}`}
      >
        <div className="flex items-start justify-between">
          <h2 id={titleId} className="flex items-center gap-2 font-semibold text-slate-800">
            {Icon && <Icon className="size-4.5 text-slate-500" aria-hidden />} {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-slate-400 hover:text-slate-600"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
