# Contributing Guide
How to set up code test review and release so contributions meet our Definition of Done

## Code of Conduct
We will work with respect and clarity. No harassment. No abuse. Speak up if something is off.  
Report concerns to the rest of the team and the project partner. For private concers use direct email.

## Getting Started
Prereqs  
- Git installed  
- Python 3.11 or newer  
- Node LTS  
- A terminal and an editor

Backend setup  
- open a terminal  
- cd svc  
- install UV: https://github.com/astral-sh/uv
- uv sync  (creates venv and installs dependencies)
- copy .env.example to .env  
- run: uv run python main.py
- open http://127.0.0.1:8000/docs and test GET health

(Alternative: use pip/venv - see DEV-SETUP.md for legacy instructions)

Frontend setup  
- open a new terminal  
- cd web  
- npm install  
- npm run dev  
- open the URL that Vite prints

## Branching and Workflow
We use a light trunk model with short lived feature branches  
- default branch is main  
- create branches as feature short name or fix short name  
- rebase small branches before merge if there are conflicts  
- do not force push main

## Issues and Planning
We track all work in GitHub Issues  
- write a clear title, and one sentence summary  
- add labels, feature, fix, docs, chore  
- link to related PRs, and meeting notes  

## Commit Messages
Keep messages short and clear  
- describe what you changed, and why it matters  
- one focused change per commit, when possible  

- keep each commit focused on one change  
## Code Style, Linting, and Formatting
Python  
- follow PEP 8 style  
- keep functions short and clear  
- use type hints for public functions  
- run tests before pushing  

Web  
- use TypeScript types, avoid any  
- keep components small and simple  
- never include secrets in code  

## Testing
Required tests  
- service  
  - update or add tests for any code change  
  - test both normal use and one error case  
- web  
  - do a quick manual check for now  
  - add unit tests later when the UI is stable  

How to run  
- svc: uv run pytest -q  (or pytest -q if venv is activated)
- web: run the app and make sure it runs properly

## Pull Requests and Reviews
Before you open a PR  
- branch is up to date with main  
- code runs locally  
- tests pass locally  
- update docs if the user sees a change

PR requirements  
- use the PR template in the repo  
- small PRs are preferred  
- request at least one reviewer who is not the author

Review rules  
- at least one approval  
- all review comments resolved  
- no red CI checks

## CI/CD
Current CI  
- file  .github workflows ci.yml  
- runs on push and pull request and confirms the pipeline is wired

Required before merge  
- CI is green  
- svc tests pass locally  pytest -q  
- web builds locally  npm run build

We will expand CI to run pytest and a web type check. Until then reviewers must run these locally.

## Security and Secrets
- never commit secrets or API keys  
- do not paste keys in issues or PRs  
- use .env files that are ignored by git  
- report security bugs privately to the lead and partner  
- keep dependencies current when possible

Prohibited  
- hard coded credentials  
- copying key material into sample code

## Documentation Expectations
Update docs when something changes  
- update README for setup or usage changes  
- update quick start guide for researchers  
- add short docstrings for important functions  
- note visible changes in the PR description  

## Release Process
We make tags when needed  
- tag format: v0.minor.patch  
- update README if needed  
- add a short summary of changes in the PR  
- to undo a release, revert the merge commit  

## Support and Contact
Need help?  
- ask in the team Discord first  
- if stuck for more than a day, post in the issue and tag the lead  
- for project questions, contact Dr. Pierson or Alex  
