import React from "react";

export default function RoutineDocs() {
    return (
        <div style={{ padding: "40px", maxWidth: "900px", margin: "0 auto", color: "var(--hmi-text)", fontFamily: "sans-serif" }}>
            <h1 style={{ color: "var(--hmi-text-bright)", marginBottom: "32px", borderBottom: "1px solid var(--hmi-border)", paddingBottom: "16px" }}>
                Routine Builder Documentation
            </h1>

            <section style={{ marginBottom: "40px" }}>
                <h2 style={{ color: "var(--hmi-text-bright)" }}>Overview</h2>
                <p style={{ lineHeight: "1.6" }}>
                    The Routine Builder allows you to write custom <strong>Python</strong> scripts that interact with the sensors, panels, and groups within the Glazing Control App. These routines are executed asynchronously on the backend server, allowing them to run independently of the browser dashboard.
                </p>
            </section>

            <section style={{ marginBottom: "40px" }}>
                <h2 style={{ color: "var(--hmi-text-bright)" }}>Execution Modes</h2>
                <ul style={{ lineHeight: "1.6", paddingLeft: "20px" }}>
                    <li style={{ marginBottom: "12px" }}>
                        <strong>Run Once:</strong> The script will execute a single time and then finish. Useful for setting up an initial state or performing a one-time calculation.
                    </li>
                    <li style={{ marginBottom: "12px" }}>
                        <strong>Run on Interval:</strong> The script will execute repeatedly, waiting the specified interval (in milliseconds) between each run.
                        <ul style={{ marginTop: "8px", paddingLeft: "20px" }}>
                            <li>By default, interval routines will expire and stop automatically after <strong>1 hour</strong> to prevent forgotten scripts from consuming resources.</li>
                            <li>If you need a continuously running background script, check the <strong>"Run indefinitely"</strong> box.</li>
                        </ul>
                    </li>
                    <li style={{ marginBottom: "12px" }}>
                        <strong>Run At (Scheduled):</strong> You can specify a future date and time for the routine to start. Your code will wait server-side until the exact time arrives.
                    </li>
                </ul>
            </section>

            <section style={{ marginBottom: "40px" }}>
                <h2 style={{ color: "var(--hmi-text-bright)" }}>Python API Wrappers</h2>
                <p style={{ lineHeight: "1.6", marginBottom: "16px" }}>
                    To make interacting with the Glazing Control System simple, three global wrapper objects are injected into your script automatically: <code>sensors</code>, <code>panels</code>, and <code>groups</code>.
                </p>

                <div style={{ backgroundColor: "var(--hmi-panel-bg)", padding: "20px", borderRadius: "8px", border: "1px solid var(--hmi-border)", marginBottom: "24px" }}>
                    <h3 style={{ marginTop: 0, color: "var(--btn-blue)" }}>sensors</h3>
                    <ul style={{ lineHeight: "1.6", margin: 0, paddingLeft: "20px" }}>
                        <li><code>sensors.list()</code>: Returns a list of dictionaries containing all known sensors.</li>
                        <li><code>sensors.get_latest(sensor_id, metric)</code>: Returns the latest numerical value for a given sensor ID and metric (e.g., <code>lux</code>, <code>melanopic_edi</code>), or <code>None</code>.</li>
                    </ul>
                </div>

                <div style={{ backgroundColor: "var(--hmi-panel-bg)", padding: "20px", borderRadius: "8px", border: "1px solid var(--hmi-border)", marginBottom: "24px" }}>
                    <h3 style={{ marginTop: 0, color: "var(--btn-blue)" }}>panels</h3>
                    <ul style={{ lineHeight: "1.6", margin: 0, paddingLeft: "20px" }}>
                        <li><code>panels.list()</code>: Returns a list of all individual panels.</li>
                        <li><code>panels.set_level(panel_id, level)</code>: Command a specific panel (e.g., <code>"P01"</code>) to tint to a specific level (0-100). Returns success or failure (e.g. if rejected by dwell time).</li>
                    </ul>
                </div>

                <div style={{ backgroundColor: "var(--hmi-panel-bg)", padding: "20px", borderRadius: "8px", border: "1px solid var(--hmi-border)" }}>
                    <h3 style={{ marginTop: 0, color: "var(--btn-blue)" }}>groups</h3>
                    <ul style={{ lineHeight: "1.6", margin: 0, paddingLeft: "20px" }}>
                        <li><code>groups.list()</code>: Returns a list of all configured groups.</li>
                        <li><code>groups.set_level(group_id, level)</code>: Command a group (e.g., <code>"G-facade"</code>) to tint to a specific level (0-100).</li>
                    </ul>
                </div>
            </section>

            <section style={{ marginBottom: "40px" }}>
                <h2 style={{ color: "var(--hmi-text-bright)" }}>Logging and Console Output</h2>
                <p style={{ lineHeight: "1.6" }}>
                    Instead of using the standard <code>print()</code> function, please use the provided <code>log()</code> function. For example:
                </p>
                <div style={{ backgroundColor: "#1e1e1e", padding: "16px", borderRadius: "8px", fontFamily: "monospace", margin: "16px 0", color: "#d4d4d4" }}>
                    lux_value = sensors.get_latest("KM1-00", "lux")<br />
                    log(f"Current lux is {'{'}lux_value{'}'}")
                </div>
                <p style={{ lineHeight: "1.6" }}>
                    The <code>log()</code> function immediately flushes the output, ensuring it streams live to the Console Output panel in the Routine Editor.
                </p>
            </section>

            <section style={{ marginBottom: "40px" }}>
                <h2 style={{ color: "var(--hmi-text-bright)" }}>Saving Routines</h2>
                <p style={{ lineHeight: "1.6" }}>
                    If you write a script you want to keep:
                </p>
                <ul style={{ lineHeight: "1.6", paddingLeft: "20px" }}>
                    <li>Type a name in the <strong>Routine Name</strong> field.</li>
                    <li>Click <strong>Save to Server</strong>. This saves the template permanently to the system database.</li>
                    <li>You can then reload it at any time from any device by clicking <strong>Load</strong> in the Saved Routines list at the bottom of the editor.</li>
                </ul>
            </section>
            <section style={{ marginBottom: "40px" }}>
                <h2 style={{ color: "var(--hmi-text-bright)" }}>Example Scripts</h2>

                <div style={{ marginBottom: "24px" }}>
                    <h3 style={{ color: "var(--hmi-text-bright)", marginBottom: "8px" }}>1. If lux {'>'} 80, tint Right Group to 50%</h3>
                    <p style={{ lineHeight: "1.6", marginBottom: "12px", color: "var(--hmi-text-muted)" }}>A simple threshold check. Best run on an <strong>Interval</strong>.</p>
                    <div style={{ backgroundColor: "#1e1e1e", padding: "16px", borderRadius: "8px", fontFamily: "monospace", color: "#d4d4d4", overflowX: "auto" }}>
                        <pre style={{ margin: 0 }}>
                            {`lux = sensors.get_latest("KM1-00", "lux")
log(f"Current lux: {lux}")

if lux is not None and lux > 80:
    groups.set_level("G-right", 50)
    log("High lux — tinted Right Group to 50%")
else:
    log("Lux is fine, no action needed")`}
                        </pre>
                    </div>
                </div>

                <div style={{ marginBottom: "24px" }}>
                    <h3 style={{ color: "var(--hmi-text-bright)", marginBottom: "8px" }}>2. Set all panels to 0% (clear)</h3>
                    <p style={{ lineHeight: "1.6", marginBottom: "12px", color: "var(--hmi-text-muted)" }}>Iterates through all individual panels and clears them. Best run <strong>Once</strong>.</p>
                    <div style={{ backgroundColor: "#1e1e1e", padding: "16px", borderRadius: "8px", fontFamily: "monospace", color: "#d4d4d4", overflowX: "auto" }}>
                        <pre style={{ margin: 0 }}>
                            {`all_panels = panels.list()
for p in all_panels:
    panels.set_level(p["id"], 0)
log("All panels cleared to 0%")`}
                        </pre>
                    </div>
                </div>

                <div style={{ marginBottom: "24px" }}>
                    <h3 style={{ color: "var(--hmi-text-bright)", marginBottom: "8px" }}>3. Log all sensor readings</h3>
                    <p style={{ lineHeight: "1.6", marginBottom: "12px", color: "var(--hmi-text-muted)" }}>Fetches and logs the current data for every sensor in the system.</p>
                    <div style={{ backgroundColor: "#1e1e1e", padding: "16px", borderRadius: "8px", fontFamily: "monospace", color: "#d4d4d4", overflowX: "auto" }}>
                        <pre style={{ margin: 0 }}>
                            {`sensor_list = sensors.list()
log(f"Found {len(sensor_list)} sensor(s)")

for s in sensor_list:
    val = sensors.get_latest(s["id"], "lux")
    log(f"{s['label']} ({s['id']}): lux = {val}")`}
                        </pre>
                    </div>
                </div>
            </section>
        </div>
    );
}
