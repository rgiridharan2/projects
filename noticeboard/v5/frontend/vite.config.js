import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Where FastAPI is running. Override to run next to another copy, e.g. API_URL=http://127.0.0.1:8001
// 127.0.0.1 rather than localhost: Node may resolve localhost to IPv6 (::1), where uvicorn isn't listening.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // The browser calls /api/... on this dev server, which forwards to FastAPI. Same origin, so no CORS setup.
    proxy: { "/api": API_URL },
  },
});
