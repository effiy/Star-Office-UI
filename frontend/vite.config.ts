import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  root: ".",
  base: "/static/",
  build: { outDir: "dist", assetsDir: "assets" },
  server: {
    port: 5173,
    proxy: {
      "/state": "http://127.0.0.1:19001",
      "/ds-bot-states": "http://127.0.0.1:19001",
      "/agents": "http://127.0.0.1:19000",
    },
  },
});
