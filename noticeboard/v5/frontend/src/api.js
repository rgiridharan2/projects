import axios from "axios";

// Every request goes to /api/..., which Vite proxies to FastAPI (see vite.config.js).
export const api = axios.create({ baseURL: "/api" });

// The current JWT. AuthContext owns it and keeps this copy in sync via setAuthToken().
let authToken = null;
let handleUnauthorized = () => {};

export function setAuthToken(token) {
  authToken = token;
}

export function setUnauthorizedHandler(handler) {
  handleUnauthorized = handler;
}

// Attach "Authorization: Bearer <token>" to every outgoing request.
api.interceptors.request.use((config) => {
  if (authToken) config.headers.Authorization = `Bearer ${authToken}`;
  return config;
});

// A 401 from anything except the login call means the token expired or is invalid: log out.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const isLoginAttempt = ["/auth/login", "/auth/signup"].includes(error.config?.url);
    if (error.response?.status === 401 && !isLoginAttempt) handleUnauthorized();
    return Promise.reject(error);
  },
);

/** Turn an Axios error into one readable line, including FastAPI's 422 validation details. */
export function errorMessage(error) {
  const detail = error.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc.at(-1)}: ${d.msg}`).join("; ");
  if (typeof detail === "string") return detail;
  if (!error.response) return "Can't reach the API. Is the backend running on port 8000?";
  return error.message;
}
