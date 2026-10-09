# Halio bring-up logs

Raw transcripts from the first connection to the trailer's Halio controller,
kept for reference. They were tracked under `svc/data/ResponseData/` until
2026-10-08 and are not read by any code.

- `rawResponses.txt`: curl requests and responses against the legacy key API
  on port 8084. The one API key value it contained is redacted; that API is no
  longer served.
- `successfulAPIReq.txt`: the request sequence that first worked.
- `Moreinfo.txt`: service log from an early real-mode run (panel and group
  listing, tint commands).

The controller's window and group listings from the same session are test
fixtures in `svc/tests/fixtures/halio/`. The current API is the unauthenticated
v3 API on port 8083; see `svc/README.md`.
