import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import workExampleManifest from "../examples/catalog/work-examples.json";

const exampleFiles = [...new Set(workExampleManifest.examples.flatMap(example => example.assets))];
const exampleDirectories = [...new Set(exampleFiles.map(path => path.slice(0, path.lastIndexOf("/"))))];

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { host: "127.0.0.1", port: 1420, strictPort: true,
    fs: { allow: [".", "../examples/emerge/gallery", "../examples/upstream-emerge/studies", "../examples/catalog", ...exampleDirectories.map(path => `../${path}`)].map(path => fileURLToPath(new URL(path, import.meta.url))) },
  },
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          three: ["three"],
          react: ["react", "react-dom"],
          icons: ["lucide-react"]
        }
      }
    }
  }
});
