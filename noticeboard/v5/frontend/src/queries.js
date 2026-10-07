import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { useAuth } from "./auth/AuthContext";

// Cache keys include the user id, so one person's data is never shown under another's login.
const keys = {
  publicCohorts: ["cohorts", "public"],
  switchOptions: (userId) => ["switch-options", userId],
  myCohort: (userId) => ["cohorts", "mine", userId],
  myMilestones: (userId) => ["milestones", "mine", userId],
  myNotices: (userId) => ["notices", "mine", userId],
  mySubmissions: (userId) => ["submissions", "mine", userId],
  dashboard: (userId) => ["dashboard", userId],
  mySchedule: (userId, start, end) => ["schedule", "mine", userId, start, end],
  myReminders: (userId) => ["reminders", "mine", userId],
  cohorts: (userId) => ["cohorts", "all", userId],
  matrix: (userId, cohortId) => ["matrix", userId, cohortId],
  allMilestones: (userId) => ["milestones", "all", userId],
  health: (userId) => ["health", userId],
  escalations: (userId) => ["escalations", userId],
  audit: (userId) => ["audit", userId],
  notices: (userId) => ["notices", "all", userId],
};

const get = (url) => () => api.get(url).then((response) => response.data);

/** Cohorts open for sign-up, for the "Join cohort" dropdown (public endpoint). */
export function usePublicCohorts() {
  return useQuery({ queryKey: keys.publicCohorts, queryFn: get("/cohorts/public-list") });
}

/** Accounts for the navbar's "Switch user" menu (needs a login since v3b). */
export function useSwitchOptions() {
  const { currentUser } = useAuth();
  return useQuery({ queryKey: keys.switchOptions(currentUser.id), queryFn: get("/users/switch-options") });
}

/** The trainee's cohort and the other trainees in it: { cohort, peers }. */
export function useMyCohort() {
  const { currentUser } = useAuth();
  return useQuery({ queryKey: keys.myCohort(currentUser.id), queryFn: get("/cohorts/mine") });
}

/** The trainee's tasks with due dates and a status each: pending / in_progress / under_review / completed. */
export function useMyMilestones() {
  const { currentUser } = useAuth();
  return useQuery({
    queryKey: keys.myMilestones(currentUser.id),
    queryFn: get("/milestones/mine"),
    refetchInterval: 15_000, // a manager's sign-off moves a task to "completed" without a reload
  });
}

export function useMyNotices() {
  const { currentUser } = useAuth();
  return useQuery({
    queryKey: keys.myNotices(currentUser.id),
    queryFn: get("/notices/mine"),
    refetchInterval: 20_000, // the live ticker (NoticeTicker) toasts any new urgent notice this brings in
    // Keep polling while the tab is in the background, so an urgent alert is already waiting when you come back.
    refetchIntervalInBackground: true,
  });
}

/** Acknowledge a notice. Updates the card instantly, then confirms with the server. */
export function useAcknowledgeNotice() {
  const { currentUser } = useAuth();
  const queryClient = useQueryClient();
  const key = keys.myNotices(currentUser.id);

  return useMutation({
    mutationFn: (noticeId) => api.post(`/notices/${noticeId}/read`).then((response) => response.data),
    onMutate: async (noticeId) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData(key);
      const now = new Date().toISOString();
      queryClient.setQueryData(key, (notices = []) =>
        notices.map((n) => (n.id === noticeId ? { ...n, read_at: n.read_at ?? now } : n)),
      );
      return { previous };
    },
    onError: (_error, _noticeId, context) => queryClient.setQueryData(key, context.previous), // roll back
    onSettled: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}

export function useMySubmissions() {
  const { currentUser } = useAuth();
  return useQuery({
    queryKey: keys.mySubmissions(currentUser.id),
    queryFn: get("/submissions/mine"),
    refetchInterval: 15_000, // pick up a manager's review without a page reload
  });
}

/** Log a milestone report. trainee_id always comes from the logged-in user. */
export function useCreateSubmission() {
  const { currentUser } = useAuth();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (form) =>
      api.post("/submissions", { ...form, trainee_id: currentUser.id }).then((response) => response.data),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.mySubmissions(currentUser.id) }),
        queryClient.invalidateQueries({ queryKey: keys.myMilestones(currentUser.id) }),
        queryClient.invalidateQueries({ queryKey: keys.myReminders(currentUser.id) }),
      ]),
  });
}

export function useDashboardStats() {
  const { currentUser } = useAuth();
  return useQuery({
    queryKey: keys.dashboard(currentUser.id),
    queryFn: get("/dashboard/stats"),
    refetchInterval: 30_000,
  });
}

// --- Phase 4: agenda and reminders (trainee) --------------------------------------------------

/** The cohort's timetable between two Dates (the agenda loads a month at a time). */
export function useMySchedule(start, end) {
  const { currentUser } = useAuth();
  const [from, to] = [start.toISOString(), end.toISOString()];
  return useQuery({
    queryKey: keys.mySchedule(currentUser.id, from, to),
    queryFn: () => api.get("/schedule/mine", { params: { start: from, end: to } }).then((r) => r.data),
  });
}

/** Unread nudges from managers about overdue tasks. */
export function useMyReminders() {
  const { currentUser } = useAuth();
  return useQuery({ queryKey: keys.myReminders(currentUser.id), queryFn: get("/reminders/mine"), refetchInterval: 30_000 });
}

export function useDismissReminder() {
  const { currentUser } = useAuth();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (reminderId) => api.post(`/reminders/${reminderId}/dismiss`).then((r) => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.myReminders(currentUser.id) }),
  });
}

// --- Phase 4: oversight and dispatch (manager) ------------------------------------------------

export function useCohorts() {
  const { currentUser } = useAuth();
  return useQuery({ queryKey: keys.cohorts(currentUser.id), queryFn: get("/cohorts") });
}

/** Every cohort's milestones (manager), so the dispatcher can preview each cohort's next position. */
export function useAllMilestones() {
  const { currentUser } = useAuth();
  return useQuery({ queryKey: keys.allMilestones(currentUser.id), queryFn: get("/milestones") });
}

/** Trainees x milestones for one cohort, with overdue flags and nudge state. */
export function useCohortMatrix(cohortId) {
  const { currentUser } = useAuth();
  return useQuery({
    queryKey: keys.matrix(currentUser.id, cohortId),
    queryFn: get(`/cohorts/${cohortId}/matrix`),
    enabled: Boolean(cohortId),
    refetchInterval: 30_000,
  });
}

/** After any nudge or dispatch: refresh the matrix and the dashboard numbers. */
function useRefreshOversight() {
  const { currentUser } = useAuth();
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["matrix", currentUser.id] }),
      queryClient.invalidateQueries({ queryKey: keys.dashboard(currentUser.id) }),
      queryClient.invalidateQueries({ queryKey: keys.allMilestones(currentUser.id) }),
      queryClient.invalidateQueries({ queryKey: keys.health(currentUser.id) }),
      queryClient.invalidateQueries({ queryKey: keys.escalations(currentUser.id) }),
      queryClient.invalidateQueries({ queryKey: keys.audit(currentUser.id) }),
    ]);
}

/** Nudge one trainee about one overdue task: { trainee_id, milestone_id }. */
export function useNudge() {
  const refresh = useRefreshOversight();
  return useMutation({ mutationFn: (body) => api.post("/reminders", body).then((r) => r.data), onSuccess: refresh });
}

/** Nudge every overdue task in a cohort that hasn't got an unread reminder yet. */
export function useNudgeAll() {
  const refresh = useRefreshOversight();
  return useMutation({
    mutationFn: (cohortId) => api.post(`/cohorts/${cohortId}/nudges`).then((r) => r.data),
    onSuccess: refresh,
  });
}

/** Send one task to several cohorts: { title, assignments: [{ cohort_id, due_date }] }. */
export function useDispatchMilestone() {
  const refresh = useRefreshOversight();
  return useMutation({
    mutationFn: (body) => api.post("/milestones/dispatch", body).then((r) => r.data),
    onSuccess: refresh,
  });
}

// --- Phase 5: health, escalations, audit, import, notices, reports (manager) ---------------------

/** Every cohort's health score, worst first. */
export function useCohortHealth() {
  const { currentUser } = useAuth();
  return useQuery({ queryKey: keys.health(currentUser.id), queryFn: get("/cohorts/health"), refetchInterval: 60_000 });
}

/** Unresolved escalations (tasks 48h+ past deadline with nothing submitted). */
export function useEscalations() {
  const { currentUser } = useAuth();
  return useQuery({ queryKey: keys.escalations(currentUser.id), queryFn: get("/escalations"), refetchInterval: 60_000 });
}

export function useRunEscalations() {
  const refresh = useRefreshOversight();
  return useMutation({ mutationFn: () => api.post("/escalations/run").then((r) => r.data), onSuccess: refresh });
}

/** The activity log, newest first, 25 at a time ("Load more" fetches older entries). */
export function useAuditLog({ enabled }) {
  const { currentUser } = useAuth();
  return useInfiniteQuery({
    queryKey: keys.audit(currentUser.id),
    queryFn: ({ pageParam }) =>
      api.get("/audit", { params: { limit: 25, ...(pageParam && { before: pageParam }) } }).then((r) => r.data),
    initialPageParam: null,
    getNextPageParam: (lastPage) => (lastPage.length === 25 ? lastPage.at(-1).created_at : undefined),
    enabled,
  });
}

/** CSV import: { csv, dry_run, initial_password?, skip_invalid? }. Dry runs change nothing. */
export function useImportTrainees() {
  const refresh = useRefreshOversight();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body) => api.post("/trainees/import", body).then((r) => r.data),
    onSuccess: (report) => {
      if (report.dry_run) return;
      refresh();
      queryClient.invalidateQueries({ queryKey: ["cohorts"] }); // trainee counts changed
    },
  });
}

export function useAllNotices() {
  const { currentUser } = useAuth();
  return useQuery({ queryKey: keys.notices(currentUser.id), queryFn: get("/notices") });
}

/** Broadcast a notice: { title, body, priority, target_cohort_id }. */
export function usePostNotice() {
  const { currentUser } = useAuth();
  const queryClient = useQueryClient();
  const refresh = useRefreshOversight();
  return useMutation({
    mutationFn: (body) => api.post("/notices", body).then((r) => r.data),
    onSuccess: () => Promise.all([queryClient.invalidateQueries({ queryKey: keys.notices(currentUser.id) }), refresh()]),
  });
}

/**
 * Download a cohort's performance report. The endpoint needs the Bearer token, so a plain <a href>
 * can't fetch it: fetch it through Axios as a blob and hand it to the browser as a file.
 */
export async function downloadCohortReport(cohortId) {
  const response = await api.get(`/cohorts/${cohortId}/report.csv`, { responseType: "blob" });
  const filename = /filename="([^"]+)"/.exec(response.headers["content-disposition"] ?? "")?.[1] ?? "report.csv";
  const url = URL.createObjectURL(response.data);
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
