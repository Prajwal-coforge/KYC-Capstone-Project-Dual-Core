import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const uiDir = path.dirname(fileURLToPath(import.meta.url));
const resultsFile = path.resolve(uiDir, "../submissions/results.json");
const demoFile = path.resolve(uiDir, "demo/synthetic-results.json");

function readPackets(file) {
  if (!fs.existsSync(file)) return [];
  const body = JSON.parse(fs.readFileSync(file, "utf8"));
  if (!Array.isArray(body)) {
    throw new Error(`${path.basename(file)} is not a list of reviews.`);
  }
  return body;
}

function sendResults(req, res, next) {
  if (req.url.split("?")[0] !== "/api/results") {
    next();
    return;
  }
  res.setHeader("Content-Type", "application/json");
  try {
    const merged = new Map();
    for (const packet of readPackets(resultsFile)) {
      if (packet?.case_id) merged.set(packet.case_id, packet);
    }
    for (const packet of readPackets(demoFile)) {
      if (packet?.case_id && !merged.has(packet.case_id)) merged.set(packet.case_id, packet);
    }
    if (merged.size === 0) {
      res.statusCode = 404;
      res.end(JSON.stringify({ error: "No review drafts are available yet." }));
      return;
    }
    res.end(JSON.stringify([...merged.values()]));
  } catch (error) {
    res.statusCode = 500;
    res.end(JSON.stringify({ error: error.message }));
  }
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
