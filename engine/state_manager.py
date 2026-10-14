QUEUED, RUNNING, RETRYING, COMPLETED, FAILED = "QUEUED", "RUNNING", "RETRYING", "COMPLETED", "FAILED"
ALLOWED = {
    QUEUED: {RUNNING},
    RUNNING: {COMPLETED, RETRYING, FAILED},
    RETRYING: {RUNNING, FAILED},
    COMPLETED: set(),
    FAILED: set(),
}


class InvalidTransition(Exception):
    pass


def check_transition(old, new):
    if new not in ALLOWED.get(old, set()):
        raise InvalidTransition(f"Illegal job state transition {old} -> {new}")
