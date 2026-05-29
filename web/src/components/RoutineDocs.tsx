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
                        <li><code>sensors.get_latest(sensor_id, metric)</code>: Returns the latest numerical value for a given sensor ID and metric (e.g., <code>lux</code>, <code>melanopic_edi_lx</code>), or <code>None</code>.</li>
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
                    lux_value = sensors.get_latest("T10A1-H1", "lux")<br />
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
                    <li>Click <strong>Save Routine</strong>. This saves the template permanently to the system database.</li>
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
                            {`lux = sensors.get_latest("T10A1-H1", "lux")
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
            <section style={{ marginBottom: "40px" }}>
                <h2 style={{ color: "var(--hmi-text-bright)" }}>Available Sensors & Metrics</h2>
                <p style={{ lineHeight: "1.6", marginBottom: "16px" }}>
                    The <code>sensors.get_latest(sensor_id, metric)</code> function requires specific sensor IDs and metric names depending on the hardware. Use the references below to know what metrics you can extract from each sensor on the system.
                </p>

                <details style={{ backgroundColor: "var(--hmi-panel-bg)", padding: "16px", borderRadius: "8px", border: "1px solid var(--hmi-border)", marginBottom: "16px", cursor: "pointer" }}>
                    <summary style={{ color: "var(--btn-blue)", fontSize: "16px", fontWeight: "bold", outline: "none" }}>T-10A Illuminance Meter (t10a)</summary>
                    <div style={{ marginTop: "16px", paddingLeft: "20px", cursor: "default" }}>
                        <p style={{ lineHeight: "1.6", marginBottom: "8px" }}>Provides basic illuminance (lux) readings.</p>
                        <h4 style={{ color: "var(--hmi-text-muted)", marginBottom: "4px" }}>Common Sensor IDs:</h4>
                        <ul style={{ margin: "0 0 12px 0", paddingLeft: "20px" }}>
                            <li><code>T10A1-H1</code> - T-10A body 1, head 1</li>
                            <li><code>T10A2-H4</code> - T-10A body 2, head 4</li>
                        </ul>
                        <h4 style={{ color: "var(--hmi-text-muted)", marginBottom: "4px" }}>Available Metrics:</h4>
                        <ul style={{ margin: 0, paddingLeft: "20px", display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: "4px" }}>
                            <li><code>lux</code>: Illuminance (lx)</li>
                        </ul>
                    </div>
                </details>

                <details style={{ backgroundColor: "var(--hmi-panel-bg)", padding: "16px", borderRadius: "8px", border: "1px solid var(--hmi-border)", marginBottom: "16px", cursor: "pointer" }}>
                    <summary style={{ color: "var(--btn-blue)", fontSize: "16px", fontWeight: "bold", outline: "none" }}>JETI Spectraval / Specbos (jeti_spectraval)</summary>
                    <div style={{ marginTop: "16px", paddingLeft: "20px", cursor: "default" }}>
                        <p style={{ lineHeight: "1.6", marginBottom: "8px" }}>Provides advanced colorimetry, illuminance, and non-visual lighting metrics from JETI spectraval or specbos devices.</p>
                        <h4 style={{ color: "var(--hmi-text-muted)", marginBottom: "4px" }}>Common Sensor IDs:</h4>
                        <ul style={{ margin: "0 0 12px 0", paddingLeft: "20px" }}>
                            <li><code>SPECTRAVAL-1</code> - first configured Spectraval device</li>
                            <li><code>SPECBOS-1</code> - configured Specbos device</li>
                        </ul>
                        <h4 style={{ color: "var(--hmi-text-muted)", marginBottom: "4px" }}>Available Metrics:</h4>
                        <ul style={{ margin: 0, paddingLeft: "20px", display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "4px" }}>
                            <li><code>lux</code>: Illuminance (lx)</li>
                            <li><code>melanopic_edi_lx</code>: Melanopic EDI (lx)</li>
                            <li><code>cct_ohno_k</code>: CCT (K) - Ohno, 2013</li>
                            <li><code>cri_ra</code>: Colour Rendering Index [Ra]</li>
                            <li><code>cfi_rf</code>: Colour Fidelity Index [Rf]</li>
                            <li><code>cie1931_x</code>: CIE 1931 xy chromaticity [x]</li>
                            <li><code>cie1931_y</code>: CIE 1931 xy chromaticity [y]</li>
                            <li><code>s_cone_irradiance_mw_m2</code>: S-cone-opic irradiance (mW/m2)</li>
                            <li><code>m_cone_irradiance_mw_m2</code>: M-cone-opic irradiance (mW/m2)</li>
                            <li><code>l_cone_irradiance_mw_m2</code>: L-cone-opic irradiance (mW/m2)</li>
                            <li><code>rhodopic_irradiance_mw_m2</code>: Rhodopic irradiance (mW/m2)</li>
                            <li><code>melanopic_irradiance_mw_m2</code>: Melanopic irradiance (mW/m2)</li>
                            <li><code>s_cone_edi_lx</code>: S-cone-opic EDI (lx)</li>
                            <li><code>m_cone_edi_lx</code>: M-cone-opic EDI (lx)</li>
                            <li><code>l_cone_edi_lx</code>: L-cone-opic EDI (lx)</li>
                            <li><code>rhodopic_edi_lx</code>: Rhodopic EDI (lx)</li>
                            <li><code>cct_robertson_k</code>: CCT (K) - Robertson, 1968</li>
                            <li><code>duv_ohno</code>: Duv - Ohno, 2013</li>
                            <li><code>duv_robertson</code>: Duv - Robertson, 1968</li>
                            <li><code>sample_interval_s</code>: Sample interval (s)</li>
                        </ul>
                    </div>
                </details>

                <details style={{ backgroundColor: "var(--hmi-panel-bg)", padding: "16px", borderRadius: "8px", border: "1px solid var(--hmi-border)", marginBottom: "16px", cursor: "pointer" }}>
                    <summary style={{ color: "var(--btn-blue)", fontSize: "16px", fontWeight: "bold", outline: "none" }}>EKO MS-90+ Sun Tracker Pyranometer (eko_ms90_plus)</summary>
                    <div style={{ marginTop: "16px", paddingLeft: "20px", cursor: "default" }}>
                        <p style={{ lineHeight: "1.6", marginBottom: "8px" }}>Outdoor environmental sensor providing global, direct, and diffuse solar irradiance, as well as sun position data.</p>
                        <h4 style={{ color: "var(--hmi-text-muted)", marginBottom: "4px" }}>Common Sensor IDs:</h4>
                        <ul style={{ margin: "0 0 12px 0", paddingLeft: "20px" }}>
                            <li><code>EKO-00</code> - EKO MS-90+ / C-BOX</li>
                        </ul>
                        <h4 style={{ color: "var(--hmi-text-muted)", marginBottom: "4px" }}>Available Metrics:</h4>
                        <ul style={{ margin: 0, paddingLeft: "20px", display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "4px" }}>
                            <li><code>ghi_w_m2</code>: Global horizontal irradiance (W/m2)</li>
                            <li><code>dni_w_m2</code>: Direct normal irradiance (W/m2)</li>
                            <li><code>dhi_w_m2</code>: Diffuse horizontal irradiance (W/m2)</li>
                            <li><code>sun_elevation_deg</code>: Sun elevation (deg)</li>
                            <li><code>sun_azimuth_deg</code>: Sun azimuth (deg)</li>
                            <li><code>board_temp_c</code>: Board temperature (degC)</li>
                            <li><code>sensor_temp_c</code>: Sensor temperature (degC)</li>
                            <li><code>gps_satellites</code>: GPS satellites</li>
                            <li><code>latitude_deg</code>: Latitude (deg)</li>
                            <li><code>longitude_deg</code>: Longitude (deg)</li>
                            <li><code>gps_timestamp_s</code>: GPS timestamp (s)</li>
                        </ul>
                    </div>
                </details>
            </section>
        </div>
    );
}
