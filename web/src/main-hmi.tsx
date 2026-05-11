import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppHMI from "./AppHMI";
import RoutineDocs from "./components/RoutineDocs";
import { ToastProvider } from "./utils/toast";
import "./styles-hmi.css";

import Docs from "./components/Docs";

ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
        <ToastProvider>
            <BrowserRouter>
                <Routes>
                    <Route path="/" element={<AppHMI />} />
                    <Route path="/docs" element={<Docs />} />
                    <Route path="/routine-docs" element={<RoutineDocs />} />
                </Routes>
            </BrowserRouter>
        </ToastProvider>
    </React.StrictMode>
);


