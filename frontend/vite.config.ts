// Vite runs the page during development and builds it for production.
//
// The proxy: the page calls /api/questions, and Vite passes it on to the API at
// 127.0.0.1:8000 as /questions. The browser only ever sees one address (5173), so it needs
// no cross-site (CORS) setting. In production a proxy (Caddy) does the same job (§0).
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1", // this machine only
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
