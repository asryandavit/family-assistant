import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Built on the PC (scheduler/register-miniapp.ps1) and served by miniapp/server.py from dist/.
// No inline scripts: the server's Content-Security-Policy allows only 'self' and telegram.org.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    modulePreload: { polyfill: false },
    assetsInlineLimit: 0,
  },
});
