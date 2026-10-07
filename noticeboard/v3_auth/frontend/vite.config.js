import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // The browser calls /api/... on this dev server, which forwards to FastAPI. Same origin, so no CORS setup.
    // 127.0.0.1 rather than localhost: Node may resolve localhost to IPv6 (::1), where uvicorn isn't listening.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
