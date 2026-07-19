"""Local LLM StepHandler using llama.cpp — reference implementation.

This is a REFERENCE EXAMPLE demonstrating how a real agent plugs into
SOPVM's Executor/StepHandler protocol. It is NOT part of SOPVM's core
package and has zero dependency on llama-cpp-python at the package level.

The handler reads a step's description + capabilities_paged, prompts a
local LLM to decide which capability to invoke (if any) and with what
args, calls request_tool() with that decision, and returns DONE/FAILED
based on the tool result.

On steps with condition/loop fields (from M16 Phase 1), the handler's
job is just to decide what to do THIS iteration — the executor still
owns the actual loop/branch control flow.

Requirements:
    pip install sopvm[llm-demo]
    # or
    pip install llama-cpp-python

Usage:
    from examples.handlers.llm_handler import LlamaHandler
    handler = LlamaHandler(model_path="models/llama-3.2-1b-instruct.Q4_K_M.gguf")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from sopvm.capability.token import CapabilityToken, parse_capability
from sopvm.ir.model import IrNode
from sopvm.plugins.base import ToolResult
from sopvm.runtime.state import StepState

logger = logging.getLogger(__name__)

# Default prompt template for the local LLM
_DEFAULT_SYSTEM_PROMPT = """You are an AI agent executing a Standard Operating Procedure (SOP).
You have access to specific tools (capabilities) for the current step.
Your job is to decide which tool to call and with what arguments.

Respond with a JSON object containing:
- "tool": the capability string to invoke (e.g. "db:read(orders)"), or null if no tool call is needed
- "args": arguments dict for the tool (e.g. {"resource": "orders"})
- "reasoning": brief explanation of your decision

If no tool call is needed, respond with {"tool": null, "args": {}, "reasoning": "..."}.
If the step has no applicable tool, respond with {"tool": null, "args": {}, "reasoning": "no tool needed"}.
"""


@dataclass
class LlamaHandler:
    """StepHandler that uses a local LLM via llama.cpp.

    Args:
        model_path: Path to the GGUF model file.
        n_ctx: Context window size (default 2048, sufficient for most SOPs).
        temperature: Sampling temperature (0.0 for deterministic).
        max_tokens: Maximum tokens to generate per step.
        system_prompt: Override the default system prompt.
    """

    model_path: str
    n_ctx: int = 2048
    temperature: float = 0.0
    max_tokens: int = 256
    system_prompt: str = _DEFAULT_SYSTEM_PROMPT
    _model: Any = field(default=None, repr=False)

    def _ensure_model(self) -> Any:
        """Lazily load the llama.cpp model."""
        if self._model is None:
            try:
                from llama_cpp import Llama
            except ImportError:
                raise ImportError(
                    "llama-cpp-python is required for LlamaHandler. "
                    "Install with: pip install sopvm[llm-demo]"
                )
            logger.info("Loading model from %s (ctx=%d)", self.model_path, self.n_ctx)
            self._model = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                verbose=False,
            )
        return self._model

    def _build_prompt(self, node: IrNode) -> str:
        """Build the user prompt from the step's IR node."""
        parts = [f"Step: {node.condition or 'Execute this step'}"]

        if node.condition:
            parts.append(f"Question to evaluate: {node.condition}")

        if node.capabilities_paged:
            parts.append(f"Available tools: {', '.join(node.capabilities_paged)}")
        else:
            parts.append("No tools available for this step.")

        if node.loop:
            parts.append(f"Loop: max {node.loop.max_iterations} iterations.")

        return "\n".join(parts)

    def _parse_llm_response(self, response: str) -> dict[str, Any]:
        """Parse the LLM's JSON response."""
        # Try to extract JSON from the response
        text = response.strip()

        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass

        # Fallback: no tool call
        return {"tool": None, "args": {}, "reasoning": "Could not parse LLM response"}

    def execute(
        self,
        node: IrNode,
        request_tool: Callable[[CapabilityToken, dict], ToolResult],
    ) -> StepState:
        """Execute a step using the local LLM.

        The LLM decides which capability to invoke. The executor handles
        the actual capability gate check and tool invocation via
        request_tool().
        """
        model = self._ensure_model()
        prompt = self._build_prompt(node)

        # Generate response from local LLM
        response = model.create_chat_completion(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        content = response["choices"][0]["message"]["content"]
        logger.info("LLM response for step: %s", content[:200])

        decision = self._parse_llm_response(content)
        tool_str = decision.get("tool")
        args = decision.get("args", {})
        reasoning = decision.get("reasoning", "")

        if tool_str is None:
            # No tool call needed — step completes successfully
            logger.info("No tool call needed. Reasoning: %s", reasoning)
            return StepState.DONE

        # Attempt to invoke the requested tool via the gate
        try:
            cap = parse_capability(tool_str)
        except Exception:
            logger.warning("LLM produced invalid capability string: %s", tool_str)
            return StepState.FAILED

        result = request_tool(cap, args)

        if result.success:
            logger.info("Tool call succeeded: %s -> %s", tool_str, result.data)
            return StepState.DONE
        else:
            logger.info("Tool call failed: %s -> %s", tool_str, result.error)
            return StepState.FAILED
