# LLM StepHandler — Reference Implementation

This directory contains a reference `StepHandler` implementation that uses a
**local LLM** (via llama.cpp) to execute SOP steps. It demonstrates how a
real agent plugs into SOPVM's Executor/StepHandler protocol.

**This is NOT part of SOPVM's core package.** SOPVM has zero dependency on
any LLM — the core library compiles SOPs and enforces capabilities without
ever calling a model. This handler is a reference example showing how to
build a real agent on top of SOPVM's infrastructure.

## How It Works

1. The executor calls `handler.execute(node, request_tool)` for each step
2. The handler sends the step description + available capabilities to a local LLM
3. The LLM decides which capability to invoke (if any) and with what args
4. The handler calls `request_tool(cap, args)` — this goes through the capability
   gate (M7) and provider sandbox (M8) before reaching the actual tool
5. The handler returns `DONE` (success) or `FAILED` (failure)
6. The executor follows the appropriate edge based on the result

The handler does NOT control branching or loops — that's the executor's job
(via `condition`/`loop` fields from Phase 1). The handler just decides what
to do on each iteration.

## Prerequisites

- Python 3.10+
- `llama-cpp-python` installed: `pip install sopvm[llm-demo]`
- A GGUF model file (see below)

## Downloading a Model

Any GGUF model works. Recommended for testing:

```bash
# Create a models directory
mkdir -p models

# Download Llama 3.2 1B (smallest, ~700MB, runs on 8GB RAM)
# Option 1: From Hugging Face (recommended)
pip install huggingface-hub
python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id='bartowski/Llama-3.2-1B-Instruct-GGUF',
    filename='Llama-3.2-1B-Instruct-Q4_K_M.gguf',
    local_dir='models'
)
"

# Option 2: From llama.cpp directly
# Visit https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF
# and download the Q4_K_M quantized version
```

### Model Options

| Model | Size | RAM Required | Quality |
|---|---|---|---|
| Llama-3.2-1B-Instruct Q4_K_M | ~700MB | 4-6GB | Good for simple steps |
| Llama-3.2-3B-Instruct Q4_K_M | ~2GB | 6-8GB | Better for complex reasoning |
| Phi-3.5-mini Q4_K_M | ~2.2GB | 6-8GB | Strong for structured output |

## Usage

```python
from sopvm import compile
from sopvm.runtime import Executor
from examples.handlers.llm_handler import LlamaHandler

# Compile a SOP
compiled = compile("examples/sops/order-processing.sop.yaml",
                   "policies/order-processing.policy.yaml")

# Create the LLM handler
handler = LlamaHandler(
    model_path="models/Llama-3.2-1B-Instruct-Q4_K_M.gguf",
    temperature=0.0,  # deterministic for reproducibility
)

# Run
executor = Executor(compiled, handler)
result = executor.run()
print(f"State: {result.final_state.value}")
print(f"Path: {' -> '.join(result.path)}")
```

## Running the Demo

```bash
# Make sure you have the model downloaded
ls models/*.gguf

# Run the end-to-end demo
python examples/run_llm_demo.py
```

## Memory and CPU Requirements

- **Minimum**: 4GB RAM (with 1B model)
- **Recommended**: 8GB RAM (with 3B model)
- **No GPU required** — llama.cpp runs on CPU via AVX/AVX2
- **No network required** after model download — everything runs locally
- **First run**: ~5-10 seconds to load the model into memory
- **Per-step inference**: ~0.5-2 seconds depending on model size

## What This Demonstrates

- How to implement the `StepHandler` protocol from M6
- How the capability gate (M7) intercepts tool calls
- How the provider sandbox (M8) catches out-of-scope invocations
- How conditional steps work: the LLM decides, the executor controls flow
- How bounded loops work: the executor tracks iterations, the handler just acts

## What This Does NOT Do

- This is NOT a production agent — it's a reference implementation
- The LLM sees no prompt engineering beyond basic step context
- There's no memory/scratchpad between steps (each step is independent)
- Tool results from prior steps aren't fed back to the LLM (no RAG)
- The prompt template is minimal — real agents would need much more
