import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  return useQuery({ queryKey: keys.myNotices(currentUser.id), queryFn: get("/notices/mine") });
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
