import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { useAuth } from "./auth/AuthContext";

// Cache keys include the user id, so one person's data is never shown under another's login.
const keys = {
  switchOptions: ["switch-options"],
  myNotices: (userId) => ["notices", "mine", userId],
  mySubmissions: (userId) => ["submissions", "mine", userId],
  dashboard: (userId) => ["dashboard", userId],
};

const get = (url) => () => api.get(url).then((response) => response.data);

/** Accounts for the login screen and the "Switch user" menu (public endpoint). */
export function useSwitchOptions() {
  return useQuery({ queryKey: keys.switchOptions, queryFn: get("/users/switch-options") });
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
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.mySubmissions(currentUser.id) }),
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
