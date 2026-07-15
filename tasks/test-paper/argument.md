# Paper Argument Structure

## Core Thesis
Academic writing can be decomposed into modular sub-tasks handled by context-aware agents, enabling better coherence and quality than single-pass generation.

## Argument Flow

### 1. Problem Statement (Introduction)
- Academic writing is hard: multiple cognitive concerns simultaneously
- LLMs help but have context limitations
- Single-pass generation doesn't match iterative writing process
- → We need structured, context-aware decomposition

### 2. Gap Identification (Related Work)
- Existing LLM writing tools operate at sentence/paragraph level
- RAG addresses facts but not document structure
- Multi-agent systems lack shared structured document grounding
- → No prior work combines document parsing + context engine + modular agents

### 3. Solution (Methodology)
- Document graph: parse → sections, labels, cites, refs
- Context engine: locate, expand, outline → L1-L5 layers
- Agent modules: uniform run() interface, black-box internals
- → Architecture separates concerns: parsing ≠ context ≠ generation

### 4. Evidence (Experiments)
- Case study: complete paper pipeline
- Metrics: structural coherence, citation accuracy, style consistency
- Baseline: single-pass LLM generation
- → Context-aware approach improves all metrics

### 5. Contribution Summary
- Context engine architecture (separation of concerns)
- Modular agent pipeline (uniform interface)
- Empirical validation (case study results)

### 6. Limitations & Future
- LaTeX-only input format
- Single case study with GPT-4 only
- Basic workflow orchestration
- Extend to legal, technical, curriculum domains
