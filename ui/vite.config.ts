import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    proxy: {
      // Brain runs locally; keeps live mode same-origin so there's no CORS to debug on demo day.
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
