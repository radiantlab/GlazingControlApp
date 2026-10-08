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
                            <strong>Development vs. Production:</strong>
                            <br />
                            Development uses simulated panels and sensors by default. The research trailer uses production with Halio and physical sensors. If the dashboard cannot reach the backend, it switches to in-browser mock data and shows a <strong>MOCK MODE</strong> badge next to the system status. Commands made in mock mode do not reach the panels.
                        </li>
                        <li style={{ marginBottom: "12px" }}>
                            <strong>Clear All:</strong> Sets every panel to 0%.
                        </li>
                        <li style={{ marginBottom: "12px" }}>
                            <strong>Logs:</strong> Opens the log viewer with three tabs.
                            <ul style={{ marginTop: "8px", paddingLeft: "20px" }}>
                                <li style={{ marginBottom: "6px" }}><strong>Audit log:</strong> Lists every change so far in the levels of each panel or group. Sort by date range, panels/group, and filter by specific panel ID or title. Export as CSV to keep all audits listed in their visible order.</li>
                                <li style={{ marginBottom: "6px" }}><strong>Sensor log:</strong> Tracks live and historical environment measurements (such as illuminance, solar irradiance, GPS status, colorimetry, and spectral data). You can view individual log entries in detail (including historical spectral graphs for JETI devices) and export all logged data as CSV.</li>
                                <li><strong>Routine log:</strong> Lists finished routines (done, stopped, or error) with their mode, status, run time, and a summary of their console output.</li>
                            </ul>
                        </li>
                        <li style={{ marginBottom: "12px" }}>
                            <strong>Groups:</strong> Opens the side panel to view groups of panels. Creating, editing, and deleting groups is available only in development; in production, groups come from the Halio controller.
                        </li>
                        <li style={{ marginBottom: "12px" }}>
                            <strong>Routines:</strong> Opens the side panel to write Python routines that run once, on an interval, or at a scheduled time. See the Routine Developer Docs.
                        </li>
                        <li>
                            <strong>Docs:</strong> General Docs (this page), Sensor Setup &amp; Quickstart, and Routine Developer Docs.
                        </li>
                    </ol>
                </div>

                {/* Section 3 */}
                <div className="room-section">
                    <h2 className="room-header">Group Control</h2>
                    <p>
                        The group control card at the top of the Control tab sets one tint level for every panel in the selected group. Dwell rules prevent rapid transitions between tint states, maximizing glass longevity.
                    </p>
                </div>

                {/* Section 4 */}
                <div className="room-section">
                    <h2 className="room-header">Windows</h2>
                    <p>
                        Each window tile shows the panel's current tint level. In development, panels are named <code>P01</code> to <code>P18</code> plus skylights <code>SK1</code> and <code>SK2</code>. In production, panels carry their Halio names, such as <code>DR-1.1</code> (room 1, driver 1). To change a single panel, drag the tile's slider or pick a preset (0, 25, 50, 75, 100), then click <strong>Apply</strong>. The tile controls are hidden while the side panel is open.
                    </p>
                </div>

                {/* Section 5 */}
                <div className="room-section">
                    <h2 className="room-header">Sensors</h2>
                    <p>
                        The Sensors tab shows a card per sensor with live readings and a graph. T-10A heads and bodies can be relabeled from the HMI: click the pencil button next to a T-10A sensor name, enter a <strong>Head Label</strong> and <strong>Body Label</strong>, and click <strong>Save</strong>. The original sensor ID stays visible in parentheses.
                    </p>
                </div>
            </main>
        </>
    );
}
