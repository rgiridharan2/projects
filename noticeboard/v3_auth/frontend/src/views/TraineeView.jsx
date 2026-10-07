import MilestoneForm from "../components/MilestoneForm";
import NoticeStream from "../components/NoticeStream";
import SubmissionTimeline from "../components/SubmissionTimeline";

export default function TraineeView() {
  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <div className="lg:col-span-3">
        <NoticeStream />
      </div>
      <div className="space-y-6 lg:col-span-2">
        <MilestoneForm />
        <SubmissionTimeline />
      </div>
    </div>
  );
}
