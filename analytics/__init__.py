"""Analytical transforms that go beyond SQL (e.g. the global driver rating).

These read modelled tables from the warehouse, compute a result in Python
(pandas/numpy), and write a mart back. Orchestrated after dbt's intermediate
models are built.
"""
