import {Link} from "react-router"


//note the classnames in the room of the info are misnamed, but apply nicely to the styling.
export default function Docs() {


    return(
        <>
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
                        <div className="hmi-status-item">
                            <span className="hmi-status-label">System</span>
                        </div>

                        <div className="hmi-status-item">
                            <span className="hmi-status-label">Panels</span>
                        </div>

                            <Link to="/">
                        <button
                            className="hmi-manage-btn"
                            title="Home"
                        >
                            Back to Home
                        </button>
                    </Link>

                    </div>
                </div>
            </header>


            <main className="hmi-main">
                <div className="room-section group-card">

                    <div className="room-header">
                            <h1 className="room-title">Docs Page</h1>

                    </div>

                    <h2 className="room-header">What is the purpose of each menu?</h2>
                    


                </div>

                <div className="room-section group-card">


                    <h2 className="room-header">Nav Bar Info</h2>
                    <ol>
                        <li>Sim vs. real</li>
                        <ul>
                            <li>We have a simulator option and a real option, the simulator being the default. When in the trailer and connected to Wi-Fi, switch to real.</li>
                        </ul>
                    </ol>

                    <h4 className="room-header">Logs</h4>
                    <ol>
                        <li>Audit Log</li>
                        <ul>
                            <li>Lists every change so far in the levels of each panel or group.</li>
                            <li>Sort by date range, panels/group, filter by specific panel ID or title.</li>
                            <li>Export as CSV: keeps all audits listed, with all filters, in the visible order.</li>
                        </ul>

                        <li>Sensor Log - TBA</li>
                    </ol>

                    <h4 className="room-header">Manage</h4>
                    <ol>
                        <li>Groups</li>
                        <ul>
                            <li>...</li>
                        </ul>

                        <li>Routines</li>
                        <ul>
                            <li>...</li>
                        </ul>
                    </ol>

                </div>

                <div className="room-section group-card">
                    <h2 className="room-header">Group Control</h2>

                </div>

                <div className="room-section group-card">
                    <h2 className="room-header">Windows</h2>


                </div>

            </main>
        </>
    )
}