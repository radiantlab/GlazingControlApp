import {Link} from "react-router"

export default function Docs() {

    return(
        <>
            <Link to="/">
                <button
                    className="home-btn"
                    title="Home"
                >
                    Back to Home
                </button>
            </Link>
            <h1>Docs Page</h1>

            <h2>What is the purpose of each menu?</h2>

            <h3>Nav Bar</h3>
            
            <ol>
                <li>Sim vs. real</li>
            </ol>
        </>
    )
}