import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// @types/node を入れずに環境変数だけ読むための宣言
declare const process: { env: Record<string, string | undefined> };

// /api はバックエンド（FastAPI, 既定 port 8000。API_TARGET で変更可）へプロキシする
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
