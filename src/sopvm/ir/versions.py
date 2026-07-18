"""IR version support constants (Milestone 13).

The runtime rejects IR files with unsupported versions rather than
attempting to run and failing confusingly mid-execution.
"""

SUPPORTED_IR_VERSIONS = frozenset({"0.1"})
