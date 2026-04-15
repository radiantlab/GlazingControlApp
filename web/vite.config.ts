import { defineConfig } from "vitest/config";

export default defineConfig({
    server: {
        port: 5173
    },
    build: {
        rollupOptions: {
            input: {
                main: "./index.html"
            }
        }
    },
    test: {
        environment: "jsdom",
        setupFiles: "./src/test/setup.ts",
        clearMocks: true,
        restoreMocks: true
    }
});
