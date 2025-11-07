import React, { createContext, useContext, useState, useCallback } from "react";

type ToastType = "success" | "error" | "info" | "warning";

interface Toast {
    id: string;
    message: string;
    type: ToastType;
}

interface ToastContextType {
    toasts: Toast[];
    showToast: (message: string, type?: ToastType) => void;
    removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const showToast = useCallback((message: string, type: ToastType = "info") => {
        const id = Math.random().toString(36).substring(7);
        setToasts((prev) => [...prev, { id, message, type }]);
    }, []);

    const removeToast = useCallback((id: string) => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
    }, []);

    return (
        <ToastContext.Provider value={{ toasts, showToast, removeToast }}>
            {children}
            <ToastContainer toasts={toasts} removeToast={removeToast} />
        </ToastContext.Provider>
    );
}

export function useToast() {
    const context = useContext(ToastContext);
    if (!context) {
        throw new Error("useToast must be used within ToastProvider");
    }
    return context;
}

function ToastContainer({ toasts, removeToast }: { toasts: Toast[]; removeToast: (id: string) => void }) {
    return (
        <div className="toast-container">
            {toasts.map((toast) => (
                <ToastItem key={toast.id} toast={toast} onClose={() => removeToast(toast.id)} />
            ))}
        </div>
    );
}

function ToastItem({ toast, onClose }: { toast: Toast; onClose: () => void }) {
    React.useEffect(() => {
        // Different durations based on toast type
        // Warnings and errors stay longer since they contain important information
        const duration = 
            toast.type === "success" ? 3000 :  // Quick feedback for success
            toast.type === "info" ? 4000 :      // Standard duration
            toast.type === "warning" ? 8000 :  // Longer for warnings (like dwell time)
            toast.type === "error" ? 10000 :   // Longest for errors
            4000;                               // Default fallback
        
        const timer = setTimeout(onClose, duration);
        return () => clearTimeout(timer);
    }, [onClose, toast.type]);

    return (
        <div className={`toast toast-${toast.type}`} onClick={onClose}>
            <div className="toast-icon">
                {toast.type === "success" && "✓"}
                {toast.type === "error" && "✕"}
                {toast.type === "warning" && "⚠"}
                {toast.type === "info" && "ℹ"}
            </div>
            <div className="toast-message">{toast.message}</div>
            <button className="toast-close" onClick={onClose} aria-label="Close">×</button>
        </div>
    );
}

