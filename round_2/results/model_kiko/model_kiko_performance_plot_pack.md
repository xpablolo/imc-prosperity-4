# model_kiko performance plot pack

- Verified model file used for these charts: `/Users/pablo/Desktop/prosperity/round_2/models/model_kiko.py`
- Important verification note: the repo contains **`model_kiko`**, not `model_kike`.
- These plots evaluate the same `round_2/models/model_kiko.py` strategy on both datasets:
  - Round 1 days `-2, -1, 0`
  - Round 2 days `-1, 0, 1`

## Overall round summary

| round | round_label | product | total_pnl | max_drawdown | fill_count | maker_share | aggressive_fill_share | avg_fill_size | turnover | avg_abs_position | max_abs_position | pct_at_limit | avg_signed_edge_to_mid | avg_signed_markout_10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| round_1 | Round 1 | ASH_COATED_OSMIUM | 62841.00 | -1840.00 | 1956 | 0.63 | 0.37 | 5.77 | 112919531.00 | 27.51 | 80.00 | 0.01 | 3.86 | 5.93 |
| round_1 | Round 1 | INTARIAN_PEPPER_ROOT | 247944.00 | -1520.00 | 1411 | 0.38 | 0.62 | 5.26 | 85500588.00 | 74.14 | 80.00 | 0.37 | 1.08 | 3.95 |
| round_2 | Round 2 | ASH_COATED_OSMIUM | 66456.00 | -1620.00 | 2024 | 0.67 | 0.33 | 5.69 | 115218391.00 | 28.27 | 80.00 | 0.02 | 4.23 | 6.10 |
| round_2 | Round 2 | INTARIAN_PEPPER_ROOT | 243484.00 | -1680.00 | 1525 | 0.39 | 0.61 | 5.34 | 102015582.00 | 71.12 | 80.00 | 0.26 | 1.27 | 4.29 |

## Ash Coated Osmium

### Round summary

| round_label | total_pnl | max_drawdown | fill_count | maker_share | avg_fill_size | avg_abs_position | avg_signed_markout_10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Round 1 | 62841.00 | -1840.00 | 1956 | 0.63 | 5.77 | 27.51 | 5.93 |
| Round 2 | 66456.00 | -1620.00 | 2024 | 0.67 | 5.69 | 28.27 | 6.10 |

### Daily summary

| round_label | day_label | day_pnl | fill_count | maker_share | avg_abs_position | pct_at_limit |
| --- | --- | --- | --- | --- | --- | --- |
| Round 1 | day -2 | 20113.00 | 645 | 0.65 | 26.35 | 0.00 |
| Round 1 | day -1 | 22308.00 | 652 | 0.63 | 21.38 | 0.00 |
| Round 1 | day 0 | 20420.00 | 659 | 0.60 | 34.81 | 0.04 |
| Round 2 | day -1 | 22167.00 | 669 | 0.67 | 41.55 | 0.02 |
| Round 2 | day 0 | 22630.00 | 677 | 0.67 | 21.62 | 0.01 |
| Round 2 | day 1 | 21659.00 | 678 | 0.66 | 21.64 | 0.02 |

### Plot files

- `plots/ASH_COATED_OSMIUM_model_kiko_pnl_curve_by_round.png`
- `plots/ASH_COATED_OSMIUM_model_kiko_drawdown_curve_by_round.png`
- `plots/ASH_COATED_OSMIUM_model_kiko_inventory_curve_by_round.png`
- `plots/ASH_COATED_OSMIUM_model_kiko_mid_and_fills_by_round.png`
- `plots/ASH_COATED_OSMIUM_model_kiko_daily_pnl_flow_dashboard.png`
- `plots/ASH_COATED_OSMIUM_model_kiko_execution_edge_dashboard.png`
- `plots/ASH_COATED_OSMIUM_model_kiko_inventory_utilization_dashboard.png`
- `plots/ASH_COATED_OSMIUM_model_kiko_pnl_increment_distribution.png`

## Intarian Pepper Root

### Round summary

| round_label | total_pnl | max_drawdown | fill_count | maker_share | avg_fill_size | avg_abs_position | avg_signed_markout_10 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Round 1 | 247944.00 | -1520.00 | 1411 | 0.38 | 5.26 | 74.14 | 3.95 |
| Round 2 | 243484.00 | -1680.00 | 1525 | 0.39 | 5.34 | 71.12 | 4.29 |

### Daily summary

| round_label | day_label | day_pnl | fill_count | maker_share | avg_abs_position | pct_at_limit |
| --- | --- | --- | --- | --- | --- | --- |
| Round 1 | day -2 | 83008.00 | 456 | 0.39 | 75.88 | 0.43 |
| Round 1 | day -1 | 82988.00 | 482 | 0.38 | 74.56 | 0.37 |
| Round 1 | day 0 | 81948.00 | 473 | 0.37 | 71.97 | 0.29 |
| Round 2 | day -1 | 81203.50 | 500 | 0.39 | 73.05 | 0.31 |
| Round 2 | day 0 | 81593.50 | 508 | 0.38 | 71.64 | 0.25 |
| Round 2 | day 1 | 80687.00 | 517 | 0.39 | 68.67 | 0.23 |

### Plot files

- `plots/INTARIAN_PEPPER_ROOT_model_kiko_pnl_curve_by_round.png`
- `plots/INTARIAN_PEPPER_ROOT_model_kiko_drawdown_curve_by_round.png`
- `plots/INTARIAN_PEPPER_ROOT_model_kiko_inventory_curve_by_round.png`
- `plots/INTARIAN_PEPPER_ROOT_model_kiko_mid_and_fills_by_round.png`
- `plots/INTARIAN_PEPPER_ROOT_model_kiko_daily_pnl_flow_dashboard.png`
- `plots/INTARIAN_PEPPER_ROOT_model_kiko_execution_edge_dashboard.png`
- `plots/INTARIAN_PEPPER_ROOT_model_kiko_inventory_utilization_dashboard.png`
- `plots/INTARIAN_PEPPER_ROOT_model_kiko_pnl_increment_distribution.png`
