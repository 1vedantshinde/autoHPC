from workloads.monte_carlo_pi import TransientError


def is_retryable(exc):
    return isinstance(exc, TransientError)


def should_retry(exc, attempt, max_retries):
    """attempt is 1-based; retries used so far = attempt - 1."""
    return is_retryable(exc) and (attempt - 1) < max_retries
