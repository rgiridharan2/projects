import { CalendarDays, LayoutGrid } from "lucide-react";
import { useState } from "react";
import ActiveTaskCard from "../components/ActiveTaskCard";
import ActivityHeatmap from "../components/ActivityHeatmap";
import GreetingHeader from "../components/GreetingHeader";
import MonthlyReview from "../components/MonthlyReview";
import NoticeStream from "../components/NoticeStream";
import ReminderBanner from "../components/ReminderBanner";
import SubmissionTimeline from "../components/SubmissionTimeline";
import SubmitReportModal from "../components/SubmitReportModal";
import { Tabs } from "../components/ui";
import { useMyMilestones } from "../queries";
import AgendaView from "./AgendaView";

const TABS = [
  { id: "overview", label: "Overview", Icon: LayoutGrid },
  { id: "agenda", label: "Agenda", Icon: CalendarDays },
];

export default function TraineeView() {
  const milestones = useMyMilestones(); // shared by the greeting, the monthly grid, the active task and the agenda
  const [tab, setTab] = useState("overview");
  const [reportFor, setReportFor] = useState(null); // milestone id while the submit dialog is open

  return (
    <div className="space-y-6">
      <GreetingHeader milestones={milestones.data} />
      <ReminderBanner onSubmit={setReportFor} />
      <Tabs tabs={TABS} active={tab} onChange={setTab} label="Trainee views" />

      {tab === "overview" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <MonthlyReview milestones={milestones.data} isError={milestones.isError} />
          </div>
          <ActiveTaskCard milestones={milestones.data} onSubmit={(task) => setReportFor(task.id)} />

          <div className="min-w-0 lg:col-span-3">
            <ActivityHeatmap />
          </div>

          <div className="lg:col-span-2">
            <NoticeStream />
          </div>
          <SubmissionTimeline />
        </div>
      ) : (
        <AgendaView onSubmit={setReportFor} />
      )}

      {reportFor && milestones.data && (
        <SubmitReportModal
          milestones={milestones.data}
          initialMilestoneId={reportFor}
          onClose={() => setReportFor(null)}
        />
      )}
    </div>
  );
}
