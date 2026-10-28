import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const resultsFile = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../submissions/results.json",
);

function sendResults(req, res, next) {
  if (req.url.split("?")[0] !== "/api/results") {
    next();
    return;
  }
  res.setHeader("Content-Type", "application/json");
  if (!fs.existsSync(resultsFile)) {
    res.statusCode = 404;
    res.end(JSON.stringify({ error: "submissions/results.json is not there yet." }));
    return;
  }
  res.end(fs.readFileSync(resultsFile));
}

function resultsApi() {
  return {
    name: "kyc-results",
    configureServer(server) {
      server.middlewares.use(sendResults);
    },
    configurePreviewServer(server) {
      server.middlewares.use(sendResults);
    },
  };
}

export default defineConfig({
  plugins: [react(), resultsApi()],
  server: { port: 5173, strictPort: true },
});
