import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { AppThemeProvider } from "./theme/AppThemeContext";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Retry network blips and 5xx, but not 4xx: a 403 or 404 won't fix itself.
      retry: (failureCount, error) => failureCount < 2 && (!error.response || error.response.status >= 500),
    },
  },
});

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <AppThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </QueryClientProvider>
    </AppThemeProvider>
  </StrictMode>,
);
