# Output Spec

## Columns

Use this exact order unless the user overrides it:

1. `Symbol`
2. `Name`
3. `Monthly Return (%)`
4. `YTD Return (%)`
5. `Month End Date`
6. `Month End Price`
7. `Previous Month End Date`
8. `Previous Month End Price`

## File names

Always write:

- `output/etf_performance_<actual_month_end_date>.csv`

Where:

- `actual_month_end_date` format: `YYYY-MM-DD`
- `output/` is relative to the current working directory where the command is executed

## Data rules

- `Month End Date` must be the last available trading date on or before the target month-end.
- `Previous Month End Date` must be the last available trading date on or before the previous month-end.
- Monthly and YTD returns should be rounded to one decimal place for display.
- Prices should be rounded to two decimal places.
