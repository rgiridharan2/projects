import { useState } from "react";
import ActiveTaskCard from "../components/ActiveTaskCard";
import GreetingHeader from "../components/GreetingHeader";
import MonthlyReview from "../components/MonthlyReview";
import NoticeStream from "../components/NoticeStream";
import SubmissionTimeline from "../components/SubmissionTimeline";
import SubmitReportModal from "../components/SubmitReportModal";
import { useMyMilestones } from "../queries";

export default function TraineeView() {
  const milestones = useMyMilestones(); // shared by the greeting, the monthly grid and the active task
  const [reportFor, setReportFor] = useState(null); // milestone id while the submit dialog is open

  return (
    <div className="space-y-6">
      <GreetingHeader milestones={milestones.data} />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <MonthlyReview milestones={milestones.data} isError={milestones.isError} />
        </div>
        <ActiveTaskCard milestones={milestones.data} onSubmit={(task) => setReportFor(task.id)} />

        <div className="lg:col-span-2">
          <NoticeStream />
        </div>
        <SubmissionTimeline />
      </div>

      {reportFor && (
        <SubmitReportModal
          milestones={milestones.data}
          initialMilestoneId={reportFor}
          onClose={() => setReportFor(null)}
        />
      )}
    </div>
  );
}
