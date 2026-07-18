"""Runtime state machine (Milestone 6).

Per INTERFACES.md §5:

    States per step: PENDING → RUNNING → {DONE, FAILED, DENIED}

- DENIED is a distinct terminal state from FAILED — a capability
  violation is not an execution error, it's a policy event.
- Transition rules are a fixed table, not ad hoc branching.

The actual transition logic lives in the executor (executor.py) as
inline checks against the step's terminal flag and edge map. This
module only defines the enum.
"""

from enum import Enum, unique


@unique
class StepState(Enum):
    """State of a single step during execution."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    DENIED = "DENIED"
