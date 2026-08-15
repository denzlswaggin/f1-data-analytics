"""Dagster orchestration for the F1 platform.

Models the pipeline as software-defined assets:

    raw.* (Jolpica + FastF1 ingestion)  ->  dbt (staging/intermediate/marts)
                                        ->  marts.driver_ratings (Python solver)

A schedule refreshes the current season after each race weekend.
"""
