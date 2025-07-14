# DATA_DICTIONARY

All tables are deterministic outputs of the research data generator
(seed 20250710). All records are synthetic case records for method
demonstration and reproducibility.

## events.csv

| column | type | description |
|---|---|---|
| event_id | str | unique event record id |
| case_key | str | case identifier |
| site_key | str | SITE_A / SITE_B / SITE_C |
| workflow_version | str | WF_V1 / WF_V2 / WF_V3 (version at case receipt) |
| event_code_raw | str | raw site/version-specific event code (dictionary input) |
| record_version | int | 1 = first record, 2 = repeat (rework signature) |
| occurred_at_utc | datetime | event occurrence time, UTC |
| known_at_utc | datetime | time the event entered the log, UTC |

## cases.csv

| column | type | description |
|---|---|---|
| case_key | str | case identifier |
| site_key | str | site |
| workflow_version | str | version valid at receipt |
| sample_class | str | class id (see sample_classes.csv) |
| received_at_utc | datetime | receipt time |
| released_at_utc | datetime | release time |
| total_hours | float | released minus received, hours |
| queue_quartile | int | load quartile at receipt (1-4) |

## quality_events.csv (ground truth)

| column | type | description |
|---|---|---|
| event_id | str | unique quality-event id |
| case_key | str | case identifier |
| event_type | str | DELAY or REWORK |
| rule_version | str | rule version the label was assigned under |
| adjudicated_at | str | label assignment timestamp (rule application time) |
| adjudicated_by | str | label-rule role id (fictional) |
| basis | str | label basis: review stage(s), supporting factor |

## sample_classes.csv

| column | type | description |
|---|---|---|
| class_id | str | class identifier |
| test_family | str | test family (e.g. WGS, WES, panel) |
| priority_class | str | priority class |
| source_category | str | source category |
| valid_from | str | first receipt date the class applies |
| valid_to | str | last receipt date the class applies |

## load_staffing.csv

| column | type | description |
|---|---|---|
| site_key | str | site |
| workflow_version | str | workflow version |
| snapshot_at_utc | datetime | monthly snapshot time |
| queue_size | int | queued cases at snapshot |
| staffing_category | str | staffing bucket |
| equipment_class | str | equipment class serving the queue |

## stage_map (dictionary, shipped as stage_map.csv)

| column | type | description |
|---|---|---|
| site_key | str | site |
| workflow_version | str | workflow version |
| event_code_raw | str | raw code |
| canonical_stage | str | one of the seven canonical stages |
| valid_from / valid_to | date | code validity window |
| reviewed_by | str | reviewer role id |

## Canonical stages

SAMPLE_RECEIVED, ACCESSIONED, LIBRARY_PREPARED, SEQUENCING_STARTED,
ANALYSIS_COMPLETE, REVIEWED, RELEASED.
