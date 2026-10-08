# Development simulation

The development environment provides a hardware-free implementation of the
panel and sensor interfaces used by production.

## Selection

```text
SVC_ENVIRONMENT=development
```

`ControlService` selects `Simulator`; production selects `HalioAdapter`.
Unknown environments and the former `SVC_MODE` values are rejected.

## Panel behavior

- Loads panel structure from `svc/config/development/panels_config.json`.
- Stores levels, timestamps, groups, audit history, and routines in the
  development database.
- Simulates a two-second tint transition and enforces the same dwell setting
  used by production.
- Allows development-only group creation, editing, and deletion.

## Sensor behavior

Development configuration lives in
`svc/config/development/sensors_config.json`.

- T-10A emits simulated illuminance readings.
- JETI writes generated CAP rows beneath the development data directory and
  exercises the normal watcher/parser pipeline.
- EKO emits simulated irradiance, solar-position, and temperature readings.

Physical-device testing requires an explicit
`SVC_DEVELOPMENT_USE_PHYSICAL_*` override. Health reports `mixed` sensor
sources when an override is active.

## Isolation

Local development writes under `svc/.runtime/development`. Containerized
development uses the `glazing-development-data` named volume. Neither path can
write the production-compatible `svc/data/audit.db`.
