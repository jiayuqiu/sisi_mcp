# Entry Scripts

## 1. Daily trigger

### 1.1 main_sync_bci_data

- schedule: Daily run
- purpose: get latest traffic data for straits and ports
- depend on: BCI Data API completion
- command:
```bash
$ uv run python -m mcp_conductor.entry.main_sync_bci_data   --start-date 2026-10-15   --end-date 2026-10-29
```

### 1.2 main_traffic_detect.py

- schedule: Daily run
- purpose: detect traffic anomaly level for straits and ports
- depend on: main_sync_bci_data
- command:
```bash
$ uv run python -m mcp_conductor.entry.main_traffic_detect --run-date=2026-10-29
```

### 1.3 main_trigger_dify_chatflow

- schedule: Daily run
- purpose: trigger dify chatbot to analyze traffic status for straits and ports
- depend on: main_traffic_detect
- command:
```bash
$ uv run python -m mcp_conductor.entry.main_trigger_dify_chatflow   --start-date 2026-06-01 --end-date 2026-10-15   --location-type all
```

## 2. Manully trigger

## 2.1 Fit model

- schedule: Manually
- purpose: update traffic anomaly detection parameters.
- depend on: main_sync_bci_data
- command:
```bash
$ uv run python -m mcp_conductor.entry.main_fit_model   --location_type pipe   --metric duration   --as_of 20261015
```

## 2.2 main_rebuild_detection

- schedule: Manually
- purpose: After fitting model parameters, you can re-run the traffic detection based on latest parameters.
- depend on: main_fit_model
- command: 

```bash
$ uv run python -m mcp_conductor.entry.main_rebuild_detection   --start-date 2026-05-22   --end-date 2026-10-15
```