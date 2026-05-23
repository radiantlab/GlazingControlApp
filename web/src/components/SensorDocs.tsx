import React from "react";
import { Link } from "react-router-dom";

export default function SensorDocs() {
    return (
        <>
            {/* Header matches Docs.tsx and AppHMI.tsx with clean status layout */}
            <header className="hmi-header">
                <div className="hmi-header-inner">
                    <div className="hmi-brand">
                        <div className="hmi-logo"></div>
                        <div className="hmi-brand-text">
                            <h1>Glazing Control System</h1>
                            <p>Electrochromic Panel Management</p>
                        </div>
                    </div>
                    <div className="hmi-status">
                        <Link to="/">
                            <button className="hmi-manage-btn" title="Back to Home">
                                Back to Home
                            </button>
                        </Link>
                    </div>
                </div>
            </header>

            <main className="hmi-main docs-layout">
                {/* Title Card */}
                <div className="room-section">
                    <div className="room-header">
                        <h1 className="room-title">Sensor Setup & Quickstart Guide</h1>
                    </div>
                    <p style={{ color: "var(--hmi-text-muted)", margin: "8px 0 0 0", fontSize: "14px" }}>
                        Site calibration and physical hardware deployment runbook
                    </p>
                </div>

                {/* Quick Overview Callout */}
                <div className="room-section" style={{ 
                    background: "linear-gradient(135deg, rgba(37, 99, 235, 0.1) 0%, rgba(15, 23, 42, 0.4) 100%)", 
                    border: "1px solid rgba(37, 99, 235, 0.3)",
                    boxShadow: "var(--hmi-shadow)"
                }}>
                    <h2 className="room-header" style={{ color: "#93c5fd", margin: "0 0 10px 0", fontSize: "18px", display: "flex", alignItems: "center", gap: "8px" }}>
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" style={{ width: "20px", height: "20px" }}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
                        </svg>
                        Quickstart Checklist (SVC_MODE = real)
                    </h2>
                    <p style={{ margin: 0, fontSize: "14px", lineHeight: "1.6", color: "var(--hmi-text-muted)" }}>
                        When operating in the research trailer/site PC, the service runs in <strong>real mode</strong> to pull actual sensor instruments. Use this guide to ensure all physical USB/Ethernet links are connected, drivers are verified, and the local software exports are properly configured.
                    </p>
                </div>

                {/* Section 1: Konica Minolta T-10A */}
                <div className="room-section">
                    <h2 className="room-header">1. Konica Minolta T-10A Setup</h2>
                    <p style={{ lineHeight: "1.6" }}>
                        The system supports single-head and multi-head daisy-chained illuminance configurations via USB/virtual COM port.
                    </p>
                    
                    <h3 style={{ color: "var(--hmi-text-bright)", fontSize: "15px", margin: "16px 0 8px 0" }}>Physical Connection Steps:</h3>
                    <ul style={{ lineHeight: "1.6", paddingLeft: "20px", margin: "0 0 20px 0" }}>
                        <li style={{ marginBottom: "8px" }}>
                            <strong>Single-Head Setup:</strong> Connect the receptor head to the T-10A body using Konica Minolta head adapter hardware. Use straight CAT5 patch cables for segments (<strong>do not use crossover Ethernet cables</strong>). Connect the body to the PC using a USB cable.
                        </li>
                        <li style={{ marginBottom: "8px" }}>
                            <strong>Multi-Head Setup:</strong> Chain the receptor heads together using <code>T-A20</code> / <code>T-A21</code> multi-point adapters and straight CAT5 cables. Connect the <code>AC-A412</code> external power supply (required for multi-head). Set a unique physical ID (00–29) on each head. Connect the main body to the PC via USB.
                        </li>
                    </ul>

                    <h3 style={{ color: "var(--hmi-text-bright)", fontSize: "15px", margin: "16px 0 8px 0" }}>Configuration:</h3>
                    <div style={{ backgroundColor: "var(--hmi-panel-bg)", padding: "16px", borderRadius: "8px", border: "1px solid var(--hmi-border)" }}>
                        <ol style={{ lineHeight: "1.6", margin: 0, paddingLeft: "20px" }}>
                            <li>Power on the T-10A body. Open Device Manager on Windows and locate the virtual COM port (e.g. <code>COM3</code>).</li>
                            <li>
                                Update <code>svc/data/sensors_config.json</code> under the <code>t10a</code> array:
                                <pre style={{ backgroundColor: "#0d1117", padding: "10px", borderRadius: "6px", overflowX: "auto", margin: "8px 0", color: "#c9d1d9", fontSize: "12px" }}>
{`"t10a": [
  {
    "device_id": "T10A-00",
    "port": "COM3",
    "heads": [
      { "head_no": 1, "sensor_id": "T10A1-H1", "label": "Desk Lux", "location": "Desk" }
    ],
    "interval_s": 60
  }
]`}
                                </pre>
                            </li>
                        </ol>
                    </div>
                </div>

                {/* Section 2: JETI Spectraval / Specbos */}
                <div className="room-section">
                    <h2 className="room-header">2. JETI Spectraval & Specbos Setup</h2>
                    <p style={{ lineHeight: "1.6" }}>
                        The JETI instrument connects to the site PC using USB.
                    </p>

                    {/* Important Notice Callout */}
                    <div style={{ 
                        borderLeft: "4px solid var(--hmi-warning)", 
                        backgroundColor: "rgba(245, 158, 11, 0.08)", 
                        padding: "12px 16px", 
                        borderRadius: "0 8px 8px 0",
                        marginBottom: "20px"
                    }}>
                        <strong style={{ color: "#fbbf24", display: "block", marginBottom: "4px" }}>⚠️ Active Deployment Support</strong>
                        <span style={{ fontSize: "13px", lineHeight: "1.5", display: "block" }}>
                            Currently, <strong>only file-based .cap file reading is supported</strong> in the backend service. Direct SPECFIRM serial/virtual COM SCPI polling is not active in this app version and may be added in a future update.
                        </span>
                    </div>

                    <h3 style={{ color: "var(--hmi-text-bright)", fontSize: "15px", margin: "16px 0 8px 0" }}>Physical & Software Setup:</h3>
                    <ol style={{ lineHeight: "1.6", paddingLeft: "20px", margin: "0 0 20px 0" }}>
                        <li style={{ marginBottom: "8px" }}>Connect the JETI device to the PC using a USB cable. Install the official JETI USB drivers.</li>
                        <li style={{ marginBottom: "8px" }}>Open the JETI measurement suite software on the PC and verify connection to the instrument.</li>
                        <li style={{ marginBottom: "8px" }}>Configure the JETI software to automatically save or export new measurements as <strong>semicolon-delimited <code>.cap</code> files</strong>.</li>
                    </ol>

                    <h3 style={{ color: "var(--hmi-text-bright)", fontSize: "15px", margin: "16px 0 8px 0" }}>File Location & Naming Rules (CRITICAL):</h3>
                    <div style={{ backgroundColor: "var(--hmi-panel-bg)", padding: "16px", borderRadius: "8px", border: "1px solid var(--hmi-border)" }}>
                        <p style={{ margin: "0 0 12px 0", lineHeight: "1.5", fontSize: "13px" }}>
                            In <code>sensors_config.json</code>, set <code>"transport": "file"</code>. The behavior depends on the value of <code>"output_path"</code>:
                        </p>
                        <ul style={{ lineHeight: "1.6", margin: 0, paddingLeft: "20px" }}>
                            <li style={{ marginBottom: "8px" }}>
                                <strong>If <code>output_path</code> points to a File (e.g. <code>"data/live.cap"</code>):</strong>
                                <br />
                                Instruct the JETI software to continuously write/overwrite this exact file. The app reads this file directly.
                            </li>
                            <li style={{ marginBottom: "8px" }}>
                                <strong>If <code>output_path</code> points to a Directory (e.g. <code>"data/jeti_measurements/"</code>):</strong>
                                <br />
                                The JETI software can export rotating files with dynamic names (e.g. <code>jeti_2026_05_22_1500.cap</code>). The file watcher will scan the folder and automatically load the file ending in <code>.cap</code> that has the <strong>latest modification time (mtime)</strong> on disk.
                            </li>
                        </ul>
                    </div>
                </div>

                {/* Section 3: EKO MS-90+ / C-BOX */}
                <div className="room-section">
                    <h2 className="room-header">3. EKO MS-90+ & C-BOX Setup</h2>
                    <p style={{ lineHeight: "1.6" }}>
                        The EKO sun tracker system feeds data to the PC network via Modbus TCP. The old RS485-to-USB serial path is deprecated.
                    </p>

                    <h3 style={{ color: "var(--hmi-text-bright)", fontSize: "15px", margin: "16px 0 8px 0" }}>Network & Hardware Setup:</h3>
                    <ol style={{ lineHeight: "1.6", paddingLeft: "20px", margin: "0 0 20px 0" }}>
                        <li style={{ marginBottom: "8px" }}>Verify the EKO sensors are wired into the C-BOX and powered.</li>
                        <li style={{ marginBottom: "8px" }}>Connect the C-BOX Ethernet port to the local trailer network.</li>
                        <li style={{ marginBottom: "8px" }}>Open a web browser on the PC and visit the C-BOX Web UI (default IP: <code>http://192.168.2.20/</code>). Confirm live values appear.</li>
                        <li style={{ marginBottom: "8px" }}>Go to <code>Modbus {"->"} Setup</code> and verify <strong>Modbus TCP Access</strong> is enabled (allow access from any IP address).</li>
                    </ol>

                    <h3 style={{ color: "var(--hmi-text-bright)", fontSize: "15px", margin: "16px 0 8px 0" }}>Configuration:</h3>
                    <div style={{ backgroundColor: "var(--hmi-panel-bg)", padding: "16px", borderRadius: "8px", border: "1px solid var(--hmi-border)" }}>
                        <p style={{ margin: "0 0 8px 0", fontSize: "13px" }}>
                            Configure the EKO tracker in <code>sensors_config.json</code> under the <code>eko_ms90_plus</code> array:
                        </p>
                        <pre style={{ backgroundColor: "#0d1117", padding: "10px", borderRadius: "6px", overflowX: "auto", margin: 0, color: "#c9d1d9", fontSize: "12px" }}>
{`"eko_ms90_plus": [
  {
    "sensor_id": "EKO-00",
    "device_id": "EKO-CBOX-01",
    "host": "192.168.2.20",
    "port": 502,
    "slave_address": 1,
    "float_byte_order": "ABCD",
    "interval_s": 5,
    "timeout_s": 3.0
  }
]`}
                        </pre>
                    </div>
                </div>

                {/* Section 4: Verification */}
                <div className="room-section">
                    <h2 className="room-header">4. Troubleshooting & Verification</h2>
                    
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
                        <div style={{ backgroundColor: "var(--hmi-panel-bg)", padding: "16px", borderRadius: "8px", border: "1px solid var(--hmi-border)" }}>
                            <h4 style={{ color: "var(--hmi-text-bright)", margin: "0 0 8px 0", fontSize: "14px" }}>Start Backend in Real Mode</h4>
                            <pre style={{ backgroundColor: "#0d1117", padding: "10px", borderRadius: "6px", color: "#c9d1d9", fontSize: "11px", margin: 0, overflowX: "auto" }}>
{`cd svc
$env:SVC_MODE = "real"
uv run python main.py`}
                            </pre>
                        </div>

                        <div style={{ backgroundColor: "var(--hmi-panel-bg)", padding: "16px", borderRadius: "8px", border: "1px solid var(--hmi-border)" }}>
                            <h4 style={{ color: "var(--hmi-text-bright)", margin: "0 0 8px 0", fontSize: "14px" }}>Test Endpoints in PowerShell</h4>
                            <pre style={{ backgroundColor: "#0d1117", padding: "10px", borderRadius: "6px", color: "#c9d1d9", fontSize: "11px", margin: 0, overflowX: "auto" }}>
{`# Check registered sensors:
irm http://127.0.0.1:8000/sensors

# Check live values:
irm http://127.0.0.1:8000/metrics/latest`}
                            </pre>
                        </div>
                    </div>
                </div>
            </main>
        </>
    );
}
