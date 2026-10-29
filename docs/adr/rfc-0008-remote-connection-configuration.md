# RFC: DIAL Control Center Remote Access

| Field | Value |
| --- | --- |
| Author | Ian Eddy |
| Date | 2026-10-24 |
| Status | Proposed |
| Decision Date | (TBD) |
| Deciders | Zane Brainard, Calvin Grabowski, Dominic Maluski, Clotilde Pierson, Alex Ulbrich |
| Superseded By | (TBD) |

## Problem and Context
The current DIAL Control Center application contains two environments: development and production. The development environment can be run on the local machine from anywhere, and does not require a WiFi connection to any networks connected to sensors. To simulate real-life sensor data, the development environment generates mock-data in real time. 

The production environment, on the other hand, can only be run while actively connected to the DIAL control center's mobile trailer WiFi network. Connecting to the trailer's WiFi network allows for the app to monitor real sensor data, as well as directly control electrochromic glazing of the trailer's window from their machine.

A consensus needs to be reached on the deployment and configuration of a remote-access connection method to the DIAL control trailer network. This will enable the team to be able to run the prod environment of the application remotely, removing the current requirement to be physically present within the trailer. Additionally, it is important to be able to test changes made to the app under real-life conditions, including with real sensor data & error codes. 

If no consensus is reached on remote-access, the team may gradually implement features that look fine on the development environment, but don't handle edge cases or real-life conditions in the prod environment. This is especially important, as the prod environment is the end-goal of the entire project.

## Options

### Option A: [Tailscale]

Tailscale is a semi open-source GUI tool that is easily downloadable for all platforms that our team may use, including Windows, Mac, and Linux. It is a networking tool specifically built to handle all of the difficult configuration of setting up encrypted, peer-to-peer mesh networks (called a tailnet). Users within a tailnet are required to create an account, which can be done through email, Google, & Github accounts. Additionally, the free personal plan can support up to 6 people within one tailnet, which is sufficient for our team of 6 people. The implementation of Tailscale is conditioned on our project partner supporting lower customization options for networking administration.

### Option B: [Team-Managed Wireguard VPN]

Wireguard is a free and open-source VPN tool that is available on all platforms used by our team, including Windows, Mac, and Linux. It can also be used to create P2P mesh networks. No account is required to be created for Wireguard. The Wireguard software & protocol requires much more manual customization, including keys & endpoint configuration, and firewall rules. As a result, implementing Wireguard gives much more control over remote-access, but also requires much more setup-overhead as well as an active maintainer with deeper networking knowledge. The implementation of Wireguard is conditioned on our project partner desiring higher network customization options, as well as having someone to actively maintain the Wireguard network infrastructure. 

### Option C: [Do Nothing]

Access to the production enviornment remains as on-site access only. Teammates will be required to be physically located at the DIAL control center to test how the system is working on prod, likely resulting in time-delays and scheduling constraints. This is the safest option, as all data remains within the local DAIL trailer network. Doing nothing would likely be conditioned on failing to implement Wireguard or Tailscale, as it is one of our project partner's goal to establish a remote-connection protocol.

## Analysis

### Security:
The option of doing nothing arguably brings the highest level of security, as the trailer computer and sensor data are kept on their local network. 

Both Tailscale and Wireguard are considered as highly-secure options, and largely respected in the cybersecurity community. 

Firstly, the Wireguard protocol is regarded as one of the most secure modern VPN protocols [1]. A review of the Wireguard protocol from IEEE concluded "WireGuard offers substantial improvements in terms of speed and reliability, attributed to its use of state-of-the-art cryptographic protocols" [2], and "WireGuard as a potent solution that balances security with performance" [2]. Notably, Tailscale also implements Wireguard as its underlying protocol for remote-connection.

Additionally, as of 2022, Tailscale has passed the SOC II audit [3], an independent-party audit that determines whether an organization has implemented appropriate processes to protect its systems and data [4].

However, the security of a team-managed Wireguard VPN depends on the team's experience and comfort with networking & security. If the team does not have experience with VPN configurations, it may potentially be an even less secure option than relying on Tailscale, which implements most of the underlying security measures automatically.

### Customization:
A Wireguard VPN offers the highest level of customization. This means that our team will be responsible for generating and distributing asymmetric key pairs [5], write our own configuration files containing the endpoint addresses, public keys, and the allowed IP subnets for each device [6].

Tailscale also offers several customization options, but automatically implements much of the content covered above [7].

### Cost:
All options are free. For Tailscale, the only potential cost would come from needing to add more than 6 people to a tailnet, which would automatically switch from free, to a paid license [8].

### Maintanence
Because of Wireguard's higher customization, at least one person on our team will be required to set up and actively maintain the Wireguard configuration. This would likely be unnecessary with a Tailscale implementation, and would likely only require a one-time set up.

## Recommendation and Verification Plan
Overall, I recommend using Tailscale for remote-connection to the DIAL control center. 

It is one of our project partner's goals to implement a remote-connection method to access the production environment. Therefore, choosing to do nothing is not recommended, and would also make it much more difficult to test code changes in real-world conditions.

Compared to Wireguard, the setup and maintanence requirements of Tailscale are also far simpler, by automatically implementing key management, NAT traversal, IP allocation, and much more. Having to manually manage these requirements through a Wireguard VPN would require at least one dedicated person on the team, who must also have extensive knowledge in security and networking. 

Additionally, having to manually manage security configurations is arguably less secure than having Tailscale implement it for us. Remote-connection through Wireguard would require research on different security & networking concepts, that could potentially be implemented incorrectly.

Tailscale supports connectivity to CI/CD pipelines in Github, which our team currently uses. However, having automatic CI tests to test the Tailnet may prove to be overengineering, and largely unnecessary. More communication with the team would be necessary to determine if we want to connect Tailscale to our current CI/CD pipeline.

Otherwise, from the user(s) perspective, we will know that Tailscale has been set up properly when every person added to our Tailnet is capable of:
    1. Connecting to the Tailnet at any location
    2. Connecting to the Tailnet at any time
    3. Having remote access to the production environment on their local machine
    4. Being capable of controlling window glazing and receiving real-time sensor data from any location

## Constraints

There are likely to be no restrictions on licensing, IP, data use, or partner confidentiality. Tailscale is available for 24/7 use once it is set up, for a maximum of 6 people. Additionally, as our project is not intended for commerical use, we meet Tailscale's free license use requirements [8].

## Delegation and Validation

### Delegation
I used AI primarily for online research on Tailscale and Wireguard. Specifically, I had AI explain the architecture of Tailscale, what sort of features it automatically implements, and what sort of features in Wireguard would require manual configuration.

Other than research, I did not use AI to write any part of this RFC, but used it to double-check the validity of my writing.

### Validation
I independently reviewed all of the cited sources that were provided by the AI to ensure they were correct. As of now, this RFC is still a proposal, and does not have any sort of tests or reviews. Communication with the DIAL Control Center team will be necessary to determine if we want automated CI tests to ensure the Tailnet is working correctly.

## Decision

TBD

## Citations
[1] Cruz, B., & Turner, G. (2024, May 29). VPN protocols compared in 2023. Security.Org. https://www.security.org/vpn/protocols/

[2] A. V. Ostroukh, C. B. Pronin, A. A. Podberezkin, J. V. Podberezkina and A. M. Volkov, "Enhancing Corporate Network Security and Performance: A Comprehensive Evaluation of WireGuard as a Next-Generation VPN Solution," 2024 Systems of Signal Synchronization, Generating and Processing in Telecommunications (SYNCHROINFO), Vyborg, Russian Federation, 2024, pp. 1-5, doi: 10.1109/SYNCHROINFO61835.2024.10617501.

[3] Anderson, D., Lubman, R., Gentry, D., & Crawshaw, D. (2022, September 6). What we learned (and can share) from passing our SOC 2 type II audit. Tailscale. https://tailscale.com/blog/soc2-type2

[4] What is SOC 2 compliance? (2015). Palo Alto Networks. https://www.paloaltonetworks.com/cyberpedia/soc-2

[5] Donenfeld, J. A. (n.d.). Quick start - WireGuard. Www.Wireguard.Com. Retrieved October 25, 2026, from https://www.wireguard.com/quickstart/

[6] What is WireGuard? (2015). Palo Alto Networks. https://www.paloaltonetworks.com/cyberpedia/what-is-wireguard

[7] Customize tailscale using system policies · tailscale docs. (2026, September 29). Tailscale. https://tailscale.com/docs/features/tailscale-system-policies

[8] Pricing. (n.d.). Tailscale.Com. Retrieved October 25, 2026, from https://tailscale.com/pricing