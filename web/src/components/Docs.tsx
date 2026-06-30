import React from "react";
import { Link } from "react-router-dom";

export default function Docs() {
    return (
        <>
            {/* Header matches AppHMI.tsx with clean, placeholder-free status layout */}
            <header className="hmi-header">
                <div className="hmi-header-inner">
                    <div className="hmi-brand">
                        <div className="hmi-logo"></div>
                        <div className="hmi-brand-text">
                            <h1>DIAL Control Center</h1>
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
                        <h1 className="room-title">Documentation Page</h1>
                    </div>
                    <p style={{ color: "var(--hmi-text-muted)", margin: "8px 0 0 0", fontSize: "14px" }}>
                        General system overview, layout information, and operational guide
                    </p>
                </div>

                {/* Section 1 */}
                <div className="room-section">
                    <h2 className="room-header">What is the purpose of each menu?</h2>
                    <p>
                        This HMI panel manages electrochromic glazing segments for solar control and visual comfort. Use the top navigation bar and side panel shortcuts to command individual zones, schedule daily tint routines, or monitor live environment measurements.
                    </p>
                </div>

                {/* Section 2 */}
                <div className="room-section">
                    <h2 className="room-header">Nav Bar Info</h2>
                    <ol style={{ lineHeight: "1.6", paddingLeft: "20px", margin: 0 }}>
                        <li style={{ marginBottom: "12px" }}>
                            <strong>Sim vs. Real:</strong>
                            <br />
                            We have a simulator option and a real option, the simulator being the default. When in the trailer and connected to Wi-Fi, switch to real.
                        </li>
                        <li style={{ marginBottom: "12px" }}>
                            <strong>Logs:</strong>
                            <ul style={{ marginTop: "8px", paddingLeft: "20px" }}>
                                <li style={{ marginBottom: "6px" }}><strong>Audit Log:</strong> Lists every change so far in the levels of each panel or group. Sort by date range, panels/group, and filter by specific panel ID or title. Export as CSV to keep all audits listed in their visible order.</li>
                                <li><strong>Sensor Log:</strong> Tracks live and historical environment measurements (such as illuminance, solar irradiance, GPS status, colorimetry, and spectral data). You can view individual log entries in detail (including historical spectral graphs for JETI devices) and export all logged data as CSV.</li>
                            </ul>
                        </li>
                        <li>
                            <strong>Manage:</strong>
                            <ul style={{ marginTop: "8px", paddingLeft: "20px" }}>
                                <li style={{ marginBottom: "6px" }}><strong>Groups:</strong> Allows managing and configuring panel zones dynamically.</li>
                                <li><strong>Routines:</strong> Allows scripting routines to execute on specific intervals or schedules.</li>
                            </ul>
                        </li>
                    </ol>
                </div>

                {/* Section 3 */}
                <div className="room-section">
                    <h2 className="room-header">Group Control</h2>
                    <p>
                        Group controls allow overriding target levels for entire facades or multiple sensors simultaneously. Dwell rules prevent rapid transitions between tint states, maximizing glass longevity.
                    </p>
                </div>

                {/* Section 4 */}
                <div className="room-section">
                    <h2 className="room-header">Windows</h2>
                    <p>
                        Individual electrochromic panels are labeled by their sector code (e.g. <code>P01</code>, <code>P02</code>). Clicking any window tile opens the manual command dialog to override its tint level.
                    </p>
                </div>
            </main>
        </>
    );
}