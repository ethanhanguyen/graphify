# Cumulative Feature Stacking Benchmark

Each row represents the **cumulative** effect of all features up to that point.

| Configuration | BFS p50 | BFS avg | Path p50 | Path avg | Expl. deg | Nodes | Edges |
|---|---|---|---|---|---|---|---|
| Baseline (all OFF) | 21.1ms | 18.6ms | 0.5ms | 1.7ms | 39 | 31,510 | 56,243 |
| + conf-filter | 39.6ms | 34.4ms | 0.3ms | 1.6ms | 39 | 31,510 | 56,243 |
| + code-schema | 35.4ms | 31.3ms | 0.5ms | 1.8ms | 39 | 31,510 | 56,243 |
