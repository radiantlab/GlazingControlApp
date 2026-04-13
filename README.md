# Electrochromic Glazing Control System for Trailer Lab

A local first control and scheduling system for 18 facade electrochromic panels and 2 skylights in the OSU Radiant Lab trailer. Goals include safe manual control, study friendly scheduling, live status, and reliable operation on a constrained trailer network.

## Working Agreements

- Feature branches use `feature/<short-name>`
- PR required with at least one reviewer
- CI must be green before merge
- Respond to PR reviews within 24 hours

## Project Board

We use a board with columns Backlog → Ready → In Progress → Review → Done.

## Communication

Primary: Discord private server channel Team 76  
Secondary: email to partner or instructor

## Getting Started
An overview of the file structure:
- `docs/` for design notes and meeting minutes
- `docs/real_sensor_setup.md` and `docs/on_site_sensor_checklist.md` for real sensor deployment
- `facilities/` for site-specific facility notes
- `web/` for the researcher UI (Contains a README specific  to the web interface)
- `svc/` for the control service and queue (Contains a README specific to the backend service)

## Watch for errors
Run the watcher from `root`, `svc`, or `web`:

```bash
npm run watch
```

Defaults by folder:
- root: backend + frontend (`both`)
- svc: backend only
- web: frontend only

Override the target in any folder:

```bash
npm run watch -- backend
npm run watch -- frontend
npm run watch -- both
```

## Acknowledgment

- Aidan Lusk  <luskai@oregonstate.edu>  
- Carlos Vasquez  <vasqueca@oregonstate.edu>  
- Ian McKee  <mckeei@oregonstate.edu>  
- Tyler Vincent  <vincenty@oregonstate.edu>
- Alexander Ulbrich  <alexander.ulbrich@oregonstate.edu>

## License

GPL 3.0 License. See LICENSE.
