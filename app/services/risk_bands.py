RISK_BANDS = [
    (0.70, "Critical"),
    (0.45, "High"),
    (0.25, "Medium"),
    (0.0, "Low"),
]


def risk_band(score: float) -> str:
    for threshold, label in RISK_BANDS:
        if score >= threshold:
            return label
    return "Low"
