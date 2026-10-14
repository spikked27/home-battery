# Development

Policy/accounting logic is pure Python and can be tested without hardware:

```sh
python -m unittest discover -s tests -p 'test_policy.py' -v
```

Integration tests use `pytest-homeassistant-custom-component` and the HA version it pins. CI also validates HACS metadata and Python syntax. Commands are mocked in tests; no tests transmit to physical equipment.

All runtime files, including the native panel, live under `custom_components/home_battery`. There are no frontend npm dependencies or external scripts. Never publish live configuration, credentials, captured household telemetry or source-evidence files.

Before a release: run policy, lifecycle/config-flow/command tests, validate HACS, inspect desktop/mobile UI, verify diagnostics omit sensitive source details, and review support claims. Release tag and integration manifest version must match.
