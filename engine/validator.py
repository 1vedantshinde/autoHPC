import math


def validate_result(res):
    """Return (ok, reason). Checks structure, finiteness, range and sample count."""
    try:
        est, n, inside = res["estimate"], res["n_samples"], res["inside"]
    except (KeyError, TypeError):
        return False, "Malformed result: missing fields"
    if not isinstance(n, int) or n <= 0:
        return False, f"Invalid sample count: {n}"
    if not isinstance(est, (int, float)) or not math.isfinite(est):
        return False, f"Estimate is not finite: {est}"
    if not (0.0 <= est <= 4.0):
        return False, f"Estimate {est} outside [0, 4]"
    if not (0 <= inside <= n):
        return False, "Inside-count inconsistent with sample count"
    return True, "ok"
