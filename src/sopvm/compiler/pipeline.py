"""End-to-end compile pipeline (Milestone 5).

Chains the M2 parser, M3 lowerer, and M5 pager into a single call.
This becomes the function the CLI (M11) and public API (M13) invoke.
"""

from __future__ import annotations

from sopvm.capability.policy import load_policy
from sopvm.ir.model import CompiledProgram
from sopvm.parser import parse

from .lower import lower
from .page import apply_paging


def compile_sop(sop_path: str, policy_path: str) -> CompiledProgram:
    """Parse, lower, and apply paging in one call.

    Args:
        sop_path: Path to the YAML SOP file.
        policy_path: Path to the YAML policy file.

    Returns:
        A ``CompiledProgram`` with policy-resolved ``capabilities_paged``.
    """
    doc = parse(sop_path)
    program = lower(doc)
    policy = load_policy(policy_path)
    result = apply_paging(program, policy)
    # Store the policy path in the IR for later check() calls
    return CompiledProgram(
        ir_version=result.ir_version,
        entry=result.entry,
        nodes=result.nodes,
        policy_ref=policy_path,
    )
