/// <reference types="vite/client" />

// Optional extra typing for known VITE_ env vars used by the app
interface ImportMetaEnv {
    readonly VITE_API_BASE?: string;
}
interface ImportMeta {
    readonly env: ImportMetaEnv;
}
