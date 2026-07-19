"""SOPVM — Public API (Milestone 13).

Per INTERFACES.md §8:

    sopvm.compile(sop_path: str, policy_path: str) -> CompiledProgram
    sopvm.check(compiled: CompiledProgram) -> CheckResult
    sopvm.Runtime(compiled: CompiledProgram, providers: list[ToolProvider])
        .run() -> RunResult

Anything not in this list is internal and may change without a version bump.
"""

from __future__ import annotations

__version__ = "0.4.0"

from typing import TYPE_CHECKING

from sopvm.compiler.pipeline import compile_sop
from sopvm.ir.model import CompiledProgram

if TYPE_CHECKING:
    from sopvm.checker.check import CheckResult
    from sopvm.plugins.base import ToolProvider
    from sopvm.runtime.executor import RunResult


# --- Public API surface ------------------------------------------------------

def compile(sop_path: str, policy_path: str) -> CompiledProgram:
    """Compile a SOP YAML into a ``CompiledProgram``.

    This is the primary entry point for the compiler pipeline.
    """
    return compile_sop(sop_path, policy_path)


def check(compiled: CompiledProgram) -> CheckResult:
    """Check a compiled program against its embedded policy.

    Returns a ``CheckResult`` with ``passed`` (bool) and ``violations``.
    """
    from sopvm.checker.check import check as _check
    from sopvm.capability.policy import load_policy
    policy = load_policy(compiled.policy_ref)  # type: ignore[attr-defined]
    return _check(compiled, policy)


class Runtime:
    """Runtime for executing a compiled SOP program.

    Per INTERFACES.md §8::

        sopvm.Runtime(compiled, providers).run() -> RunResult
    """

    def __init__(
        self,
        compiled: CompiledProgram,
        providers: list[ToolProvider] | None = None,
    ) -> None:
        from sopvm.plugins.registry import ProviderRegistry

        self._compiled = compiled
        self._registry = ProviderRegistry()
        if providers:
            for p in providers:
                self._registry.register(p)

    def run(self) -> RunResult:
        """Execute the compiled SOP and return a ``RunResult``."""
        from sopvm.runtime.executor import Executor
        from sopvm.runtime.state import StepState

        class _SimpleHandler:
            def execute(self, node, request_tool=None):
                return StepState.DONE

        executor = Executor(
            program=self._compiled,
            handler=_SimpleHandler(),
            registry=self._registry,
        )
        return executor.run()


__all__ = [
    "CompiledProgram",
    "Runtime",
    "check",
    "compile",
]
