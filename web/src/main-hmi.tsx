import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppHMI from "./AppHMI";
import RoutineDocs from "./components/RoutineDocs";
import { ToastProvider } from "./utils/toast";
import "./styles-hmi.css";

import Docs from "./components/Docs";
import SensorDocs from "./components/SensorDocs";

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Root element #root not found");

ReactDOM.createRoot(rootElement).render(
    <React.StrictMode>
        <ToastProvider>
            <BrowserRouter>
                <Routes>
                    <Route path="/" element={<AppHMI />} />
                    <Route path="/docs" element={<Docs />} />
                    <Route path="/docs/routines" element={<RoutineDocs />} />
                    <Route path="/docs/sensors" element={<SensorDocs />} />
                </Routes>
            </BrowserRouter>
        </ToastProvider>
    </React.StrictMode>,
);
