# Table schemas (frozen)

Column contracts for the four research tables. `validate` checks these
contracts mechanically.

## events.csv

| column | dtype | nullable | note |
|---|---|---|---|
| event_id | string | no | unique |
| case_key | string | no | foreign key -> cases |
| site_key | string | no | SITE_A/B/C |
| workflow_version | string | no | WF_V1/V2/V3 |
| event_code_raw | string | no | dictionary input |
| record_version | int | no | 1 or 2 |
| occurred_at_utc | datetime UTC | no | |
| known_at_utc | datetime UTC | no | >= occurred_at |

## quality_events.csv

| column | dtype | nullable | note |
|---|---|---|---|
| event_id | string | no | unique |
| case_key | string | no | foreign key -> cases |
| event_type | string | no | DELAY or REWORK |
| rule_version | string | no | |
| adjudicated_at | string | no | label assignment timestamp, <= era end |
| adjudicated_by | string | no | label-rule role id (fictional) |
| basis | string | no | non-empty review basis |

## sample_classes.csv

| column | dtype | nullable | note |
|---|---|---|---|
| class_id | string | no | unique |
| test_family | string | no | |
| priority_class | string | no | |
| source_category | string | no | |
| valid_from | string | no | |
| valid_to | string | no | |

## load_staffing.csv

| column | dtype | nullable | note |
|---|---|---|---|
| site_key | string | no | |
| workflow_version | string | no | |
| snapshot_at_utc | datetime UTC | no | monthly |
| queue_size | int | no | >= 0 |
| staffing_category | string | no | |
| equipment_class | string | no | |

## stage_map.csv (dictionary)

| column | dtype | nullable | note |
|---|---|---|---|
| site_key | string | no | |
| workflow_version | string | no | |
| event_code_raw | string | no | |
| canonical_stage | string | no | one of seven |
| valid_from | date | no | |
| valid_to | date | yes | open-ended when empty |
| reviewed_by | string | no | role id |
