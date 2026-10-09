# Reference files

- `sensors_config.legacy-site.json`: the full-site sensor configuration that
  was tracked as `svc/data/sensors_config.json` before the production and
  development split. It lists two T-10A bodies (KM1 on COM5, KM2 on COM4, eight
  heads each), three JETI file sources (SPECTRAVAL-1, SPECTRAVAL-2, SPECBOS-1)
  and the EKO C-BOX. The current template is
  `svc/config/production.example/sensors_config.json`, which carries the T-10A
  bodies as external devices; the two Spectraval entries exist only here. They are left
  out of production on purpose (see the JETI section of
  `docs/production_sensor_setup.md`).
