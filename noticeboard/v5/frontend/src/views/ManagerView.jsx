import { Clock, Grid3x3, LayoutDashboard, MailOpen, Megaphone, Send, TriangleAlert, Users } from "lucide-react";
import { useState } from "react";
import CohortHealthPanel from "../components/CohortHealthPanel";
import CohortMatrix from "../components/CohortMatrix";
import EscalationsPanel from "../components/EscalationsPanel";
import NoticeComposer from "../components/NoticeComposer";
import TaskDispatcher from "../components/TaskDispatcher";
import { Card, Spinner, Tabs } from "../components/ui";
import { useDashboardStats } from "../queries";

const TILES = [
  { key: "total_active", label: "Active trainees", Icon: Users, tone: "text-indigo-600 dark:text-indigo-400 bg-indigo-50" },
  { key: "at_risk", label: "At risk (stalled)", Icon: TriangleAlert, tone: "text-amber-600 dark:text-amber-400 bg-amber-50" },
  { key: "overdue_submissions", label: "Overdue tasks", Icon: Clock, tone: "text-red-600 dark:text-red-400 bg-red-50" },
  { key: "read_rates", label: "Notice read rate", Icon: MailOpen, tone: "text-emerald-600 dark:text-emerald-400 bg-emerald-50", percent: true },
];

const TABS = [
  { id: "matrix", label: "Cohort matrix", Icon: Grid3x3 },
  { id: "dispatch", label: "Dispatch tasks", Icon: Send },
  { id: "notices", label: "Broadcast notice", Icon: Megaphone },
];

const PANELS = { matrix: CohortMatrix, dispatch: TaskDispatcher, notices: NoticeComposer };

/** Manager home: headline numbers, cohort health and escalations, then the matrix / dispatcher / notices tabs. */
export default function ManagerView() {
  const stats = useDashboardStats();
  const [tab, setTab] = useState("matrix");
  const Panel = PANELS[tab];

  return (
    <div className="space-y-6">
      <Card title="Manager dashboard" icon={LayoutDashboard}>
        {stats.isPending && <Spinner />}
        {stats.isError && <p className="text-sm text-red-600 dark:text-red-400">Couldn't load stats. {stats.error.message}</p>}
        {stats.data && (
          <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {TILES.map(({ key, label, Icon, tone, percent }) => (
              <div key={key} className="rounded-xl border border-slate-200 p-4">
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
      </Card>

      <CohortHealthPanel />
      <EscalationsPanel />

      <Tabs tabs={TABS} active={tab} onChange={setTab} label="Manager tools" />
      <Panel />
    </div>
  );
}
