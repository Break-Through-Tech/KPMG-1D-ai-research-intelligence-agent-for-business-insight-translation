"""Shared processing outcomes and command-line exit-code policy."""

SUCCESS = "success"
PARTIAL_FAILURE = "partial_failure"
FAILURE = "failure"

EXIT_SUCCESS = 0
EXIT_PARTIAL_FAILURE = 2
EXIT_FAILURE = 3


def exit_code_for_outcome(outcome: str) -> int:
    """Map a processing outcome to the documented CLI exit code."""

    if outcome == SUCCESS:
        return EXIT_SUCCESS
    if outcome == PARTIAL_FAILURE:
        return EXIT_PARTIAL_FAILURE
    if outcome == FAILURE:
        return EXIT_FAILURE
    raise ValueError(f"unknown processing outcome: {outcome}")
