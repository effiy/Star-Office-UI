import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  root: ".",
  base: "./",
  build: {
    outDir: "dist",
    assetsDir: "assets",
    rollupOptions: {
      output: {
        manualChunks: {
          "vendor-vue": ["vue", "pinia"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/agents": "http://127.0.0.1:19000",
      "/state": "http://127.0.0.1:19001",
      "/ds-bot-states": "http://127.0.0.1:19001",
      "/static": "http://127.0.0.1:5173",
    },
  },
});
