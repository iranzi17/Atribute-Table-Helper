# Reference Workbook Template

Use this outline when preparing Excel workbooks that will live in `reference_data/`.

| Column name   | Example value   | Notes                                      |
| ------------- | --------------- | ------------------------------------------ |
| `station_id`  | `RW-001`        | Join key that must also exist in the GPKG. |
| `station_name`| `Kigali North`  | Human readable name.                       |
| `voltage_kv`  | `110`           | Numeric column, keep as number/text.       |
| `commissioned`| `2018-05-01`    | ISO date string or Excel date.             |
| `status`      | `Active`        | Enum-style value.                          |

Feel free to add more sheets or columns; the UI lets you pick any sheet and join field.
