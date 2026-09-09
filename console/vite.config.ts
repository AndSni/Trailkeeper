import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built bundle is written straight into the backend package so the same
// rsync that deploys the API ships the console. It is a build artifact -
// gitignored, rebuilt on every deploy (see scripts/deploy_backend.sh).
const API = "http://127.0.0.1:9110";

export default defineConfig({
  plugins: [react()],
  base: "/console/",
  build: {
    outDir: "../backend/app/web/static/console",
    emptyOutDir: true,
  },
  server: {
    proxy: Object.fromEntries(
      ["/auth", "/projects", "/sync", "/trails", "/tasks", "/structures", "/inspections",
       "/inspection-forms", "/job-types", "/segment-work"].map((p) => [p, API]),
    ),
  },
});
