import { Clock, LayoutDashboard, MailOpen, TriangleAlert, Users } from "lucide-react";
import { useDashboardStats } from "../queries";
import { Card, Spinner } from "../components/ui";

const TILES = [
  { key: "total_active", label: "Active trainees", Icon: Users, tone: "text-indigo-600 bg-indigo-50" },
  { key: "at_risk", label: "At risk", Icon: TriangleAlert, tone: "text-red-600 bg-red-50" },
  { key: "overdue_submissions", label: "Overdue reports", Icon: Clock, tone: "text-amber-600 bg-amber-50" },
  { key: "read_rates", label: "Notice read rate", Icon: MailOpen, tone: "text-emerald-600 bg-emerald-50", percent: true },
];

/** A minimal manager landing page: proves the role switch works. Full manager tools come in a later phase. */
export default function ManagerView() {
  const stats = useDashboardStats();

  return (
    <Card title="Manager dashboard" icon={LayoutDashboard}>
      {stats.isPending && <Spinner />}
      {stats.isError && <p className="text-sm text-red-600">Couldn't load stats. {stats.error.message}</p>}
      {stats.data && (
        <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {TILES.map(({ key, label, Icon, tone, percent }) => (
            <div key={key} className="rounded-lg border border-slate-200 p-4">
              <dt className="flex items-center gap-2 text-sm text-slate-500">
                <span className={`rounded-md p-1.5 ${tone}`}>
                  <Icon className="size-4" aria-hidden />
                </span>
                {label}
              </dt>
              <dd className="mt-2 text-3xl font-semibold text-slate-900">
                {percent ? `${Math.round(stats.data[key] * 100)}%` : stats.data[key]}
              </dd>
            </div>
          ))}
        </dl>
      )}
      <p className="mt-4 text-sm text-slate-500">
        Switch to a trainee account (top right) to see the trainee view. Manager tools for notices and reviews are the
        next phase.
      </p>
    </Card>
  );
}
