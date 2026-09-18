import pandas as pd
from scripts.restore_dashboard_history import missing_partitions


def test_published_partition_wins_and_missing_sessions_are_restored() -> None:
    current = pd.DataFrame({"season": [2026], "round": [14], "session": ["R"], "v": [99]})
    old = pd.DataFrame(
        {"season": [2026] * 3, "round": [13, 14, 14], "session": ["R", "R", "Q"], "v": [1, 2, 3]}
    )
    result = missing_partitions(current, old)
    assert result.v.tolist() == [1, 3]
    assert missing_partitions(pd.concat([current, result]), old).empty
