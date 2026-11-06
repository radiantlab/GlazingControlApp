# RFC: Monolith or Microservice

- **Author:** Zane Brainard
- **Date:** 2026-10-22
- **Status:** Proposed
- **Decision Date:** (fill when decided)
- **Deciders:** (who agreed to the outcome)
- **Superseded By:** —
- **Decision type:**

## Problem and Context
The Dial Control Center has been outfitted electrochromic glass that can be adjusted to simulate different lighting conditions to collect data on sunlights affect in architectural design. Researchers use multiple instruments to collect the data used in there experiments and capture data like illuminance and solar radiation.
The previous Capstone team that worked on this project built the control application for the researchers using FastAPI, React and SQLite. Our Capstone team’s goal this year is to improve system reliability to enable researchers to be able to run the DIAL lab unattended for extended periods of time.

Currently the sensors collect data in with an Embedded acquisition inside the FastAPI application for EKO network measurements and JETI file ingestion. Data is also collected using a separate Windows Sensor Agent for instruments requiring COM ports. Since some sensors run inside the same process as FastAPI, a serious failure could potentially affect other parts of the application. Separating sensor acquisition into its own service could help prevent this, but it would also make the system more complicated to manage and maintain.

Our main concern with collecting sensor data inside of the FastAPI is that it is creating relablilty risks. We need to be able to tell when a sensor is malfunctioning without losing data or the program crashing. If nothing is changed to the current system, existing monitoring and failure-isolation limitations may remain. Our team needs to decide whether improving the current architecture is enough to meet our reliability goals or if separating more components would be worth the additional complexity.

## Options Considered:
**Option A**
One of our Capstone’s teams options are to either do nothing. The first option is to leave the current DIAL architecture. That would mean FastAPI would continue to collect the embedded sensor data from the instruments using the com ports. The windows sensor agent would allow us to collect data from instruments using the Com ports.  This option doesn’t require us to add any more development time or complexity to the system allowing us to tackle other issues. We would also be avoiding introducing new issues and bugs while adding in a new system. The cons would be that we would be limited in our ability to record data reliably and have other limitations. With the current system, Docker could be reporting the application is healthy even when /health response indicates a sensor is not recording. This issue would make it harder for researchers to catch problems while the lab is running. While being the simplest, it may  not allow our team to achieve out goals.

**Option B**
Our second option is to keep the dials exsiting architecture but improve the reliablility and monitoring. In this scenario FastAPI would continue to collect the EKO measurements and reading JETI data. We would improve the sensor health monitoring, error handeling and automatic recovery. With this option we would have a less complex system that would be easier to maintain with an existing codebase. The downsides of this path are that the embedded sensors still runs in the FastAPI, and a serious error could lead to a failure of the whole application.

**Option C**
The final option is to move the remaining sensors out of the FastAPI  and into a separate service. This would handel the EKO measurements and the JETI file separately. If FastAPI crashes the other services could continue collecting data. This would improve reliability and if a crash happened the services could continue running and store them temporarily. Sensor crashes would be less likely to crash the whole program. The downside would be adding more services would increase complexity and would take more watching and implementation. This approach could improve fault isolation, but it adds complexity to a system researchers need to operate without technical assistance.



## Technical trade off
The three options have different advantages and disadvantages when it comes to reliability, complexity, and maintenance. The current architecture without making changes would be the easiest option but it does leave some of the existing reliability concerns unaddressed. If we improved the current architecture like in option b it would allow us to build on the error handling and monitoring systems that are already in place. The current FastAPI application uses separate worker threads for sensors, which helps prevent individual sensor errors from affecting other sensors but a more serious failure could still affect the entire application.
Another concern is the health monitoring of the system. DIAL already has health monitoring in place, but there is still room to improve how sensor failures are detected and reported. Separating sensor acquisition into another service could improve fault isolation but it would also require more time and effort to maintain. It would also introduce another communication step when transferring sensor data to the database. Improving the existing architecture seems like the best balance between reliability and simplicity especially since researchers need the system to operate unattended.

## Recommendation and Verification Plan
I recommend improving the existing architecture before separating additional services. To verify this decision our team could simulate sensor failures and check whether the rest of the application continues working. We could also test whether disconnected sensors are reported correctly and whether they automatically reconnect. Another important test would be restarting FastAPI and checking that previously recorded data is preserved. If these tests show that sensor failures can disrupt other parts of the application separating sensor acquisition into an independent service may be necessary.

## Constraints
One major constraint is that DIAL runs on a Windows computer and some sensors require Windows COM ports that the Linux container cannot directly access. This is why the system already uses a separate Windows Sensor Agent. Any changes to the architecture would need to maintain compatibility with these instruments. Another concern is protecting the existing research data stored in SQLite and making sure changes don't cause data loss. Since the trailer could lose its network connection being mobile, data collection needs to work without internet access. The system needs to remain simple enough for researchers to operate without a developer.

## Delegation and Validation
To support the analysis, I referenced the existing architecture documentation, sensor manager, and health monitoring implementation. I also used my experience working on PR #78, where I tested Docker health checks in development and confirmed they were passing. These tests did not verify how the system responds to actual sensor failures. Before making any architecture changes I would want to run additional tests, review the results, and discuss the recommendation with my team. I used AI to help me better understand DIAL's current architecture and organize the different options for this RFC. It helped me find relevant files in the GitHub repository and understand how FastAPI and the Windows Sensor Agent work together


## Proposed decision
My recommendation would be to keep DIAL's current FastAPI and Windows Sensor Agent architecture and spend resources on improving health monitoring, error handling, and automatic recovery. This approach would allow us to improve reliability without adding more complexity. If testing shows that embedded sensor failures significantly affect the rest of the application, our team should reconsider separating sensor acquisition into an independent service. This decision is still open for team discussion and review.

## Works Cited
Radiant Lab. “Architecture.” GlazingControlApp, GitHub, https://github.com/radiantlab/GlazingControlApp/blob/main/docs/architectureDiagram.md.
Radiant Lab. “The Container Owns Network Sensors and the Agent Owns COM Ports.” GlazingControlApp, GitHub, https://github.com/radiantlab/GlazingControlApp/blob/main/docs/adr/0002-the-container-owns-network-sensors-and-the-agent-owns-com-ports.md.
Radiant Lab. “Sensor Manager.” GlazingControlApp, GitHub, https://github.com/radiantlab/GlazingControlApp/blob/main/svc/app/sensors/manager.py.
Radiant Lab. “Production Sensor Setup.” GlazingControlApp, GitHub, https://github.com/radiantlab/GlazingControlApp/blob/main/docs/production_sensor_setup.md.
Radiant Lab. “Partial Implementation of Issue #76.” GlazingControlApp, GitHub, pull request no. 78, 22 Oct. 2026, https://github.com/radiantlab/GlazingControlApp/pull/78.
