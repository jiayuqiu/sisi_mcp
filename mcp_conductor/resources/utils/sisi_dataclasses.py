from dataclasses import dataclass, field, fields as dataclass_fields


@dataclass
class AnomalyFlag:
    @staticmethod
    def validate_no_duplicate_values(instance) -> None:
        """Raise ValueError if any two fields share the same int value."""
        seen = {}
        for f in dataclass_fields(instance):
            val = getattr(instance, f.name)
            if val in seen:
                raise ValueError(
                    f"Duplicate flag value {val}: '{seen[val]}' and '{f.name}'"
                )
            seen[val] = f.name

    @dataclass(frozen=True)
    class Basic:
        NORMAL:  int = field(default=0, metadata={"description": "Traffic within historical bounds"})
        ANOMALY: int = field(default=1, metadata={"description": "Outlier ratio exceeds threshold"})
        NO_DATA: int = field(default=2, metadata={"description": "Empty DataFrame or all-zero ship_cnt"})

        def __post_init__(self):
            AnomalyFlag.validate_no_duplicate_values(self)

    @dataclass(frozen=True)
    class RollingPercentileFlag(Basic):
        FLAT_DATA: int = field(default=3, metadata={"description": "p10 == p90, insufficient variance to detect"})
        INSUFFICIENT_DATA: int = field(default=4, metadata={"description": "both of p10 and p90 are less then 3, "
                                                                           "cnt are too small to detect"})


ROLLING_PERCENTILE_FLAG = AnomalyFlag.RollingPercentileFlag()

