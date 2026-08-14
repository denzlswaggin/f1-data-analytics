"""F1 data-engineering ingestion package.

Extract-Load layer: pulls Formula 1 data from Jolpica-F1 (and FastF1 in a later
milestone), lands it as partitioned Parquet, and loads it into the warehouse
(DuckDB for dev, Postgres for prod).
"""

__version__ = "0.1.0"
