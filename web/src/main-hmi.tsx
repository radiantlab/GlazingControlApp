import React from "react";
import ReactDOM from "react-dom/client";
import AppHMI from "./AppHMI";
import { ToastProvider } from "./utils/toast";
import "./styles-hmi.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
        <ToastProvider>
            <AppHMI />
        </ToastProvider>
    </React.StrictMode>
);


