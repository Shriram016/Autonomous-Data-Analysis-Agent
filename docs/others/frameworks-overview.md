# LLM Frameworks — Overview & Decision Guide

## What Problem Are These Frameworks Solving?

When you build an LLM-powered app, you quickly hit recurring plumbing problems:
- Calling different LLM providers (OpenAI, Groq, Anthropic, etc.) with different SDKs
- Parsing structured output from LLMs
- Connecting LLMs to external tools, databases, APIs
- Managing multi-step workflows where one LLM call feeds the next
- Handling retries, error recovery, state management

Frameworks exist to avoid rebuilding this plumbing every time. But **they're not always necessary**.

---

## The Major Frameworks

### 1. LangChain

**What:** Library of abstractions for LLM apps — prompt templates, output parsers, tool connectors, document loaders, retrievers, chains.

**Strengths:**
- Massive integration ecosystem (150+ LLM providers, vector stores, document loaders)
- Great for RAG (Retrieval-Augmented Generation) — document loading, splitting, embedding, retrieval are all built in
- Fast prototyping — go from idea to working demo quickly

**Weaknesses:**
- Heavy abstraction layer — simple things become complex when you fight the abstractions
- Debugging is hard — stack traces go through many layers of framework code
- Opinionated about how you structure things — if your pattern doesn't fit, you're swimming upstream
- Rapid API changes historically — code breaks across versions

**Best for:** RAG pipelines, quick prototypes, projects that need many integrations out of the box.

---

### 2. LangGraph

**What:** A graph-based orchestration framework for stateful, multi-step agent workflows. Separate from LangChain, different mental model.

**Core idea:** Graph, not chain. You define:
- **Nodes** — functions that do work (LLM calls, tool execution, validation)
- **Edges** — connections between nodes (including conditional edges that route based on state)
- **State** — a typed object passed between nodes, mutated at each step

**Strengths:**
- First-class support for cycles (retry loops, re-planning)
- Conditional routing between steps based on state
- Built-in checkpointing — resume from any node after a crash
- Typed state passed explicitly between nodes — you can see exactly what data flows where

**Weaknesses:**
- Learning curve — graph thinking is different from linear code
- Overkill for simple linear workflows
- Tightly coupled to LangChain ecosystem (uses LangChain's message types, some abstractions)
- Relatively new — smaller community, fewer battle-tested production examples

**Best for:** Complex agent loops with branching, retries, error recovery, and checkpointing needs.

---

### 3. LlamaIndex

**What:** A framework specifically built for **connecting LLMs to your data**. Originally called GPT Index.

**Core idea:** You have documents, databases, APIs — LlamaIndex helps you index that data, retrieve the relevant parts, and feed them to an LLM.

**Strengths:**
- Best-in-class for RAG — ingestion, chunking, indexing, retrieval, all deeply thought through
- Supports many index types (vector, keyword, tree, knowledge graph)
- Great abstractions for querying over structured and unstructured data
- Built-in evaluation for retrieval quality

**Weaknesses:**
- Narrowly focused on data retrieval/querying — not a general agent framework
- If your problem isn't "connect LLM to external data," it's the wrong tool
- Abstractions can be heavy when you just want a simple vector search

**Best for:** Production RAG systems, querying over large document collections, structured data Q&A, knowledge bases.

**LlamaIndex vs LangChain for RAG:** LlamaIndex is deeper on retrieval (more index types, better chunking strategies, retrieval evaluation). LangChain is broader (RAG is one of many things it does). If RAG is your core problem, LlamaIndex is usually the better choice.

---

### 4. CrewAI

**What:** Framework for multi-agent systems — you define "agents" with roles and "tasks," and they collaborate.

**Strengths:**
- Natural metaphor for team-style workflows (researcher agent, writer agent, reviewer agent)
- Simple API for defining agent roles and delegation

**Weaknesses:**
- Less control over execution flow than LangGraph
- The "agents as team members" metaphor can obscure what's actually happening
- Limited when you need precise step-by-step control

**Best for:** Multi-agent collaboration scenarios where you want agents with distinct roles working together.

---

### 5. Autogen (Microsoft)

**What:** Framework for multi-agent conversations — agents talk to each other in a conversation loop.

**Strengths:**
- Good for agent-to-agent dialogue patterns
- Built-in human-in-the-loop support
- Strong code generation and execution patterns

**Weaknesses:**
- Conversation-centric — not all problems are best modeled as agent conversations
- Can be hard to control when agents go off-track

**Best for:** Scenarios where multiple agents need to debate, review each other's work, or iterate through conversation.

---

### 6. Raw Python + LLM SDK

**What:** No framework. Just `pip install openai` (or `groq`, `anthropic`) and write your own orchestration.

**Strengths:**
- Full control — you understand every line
- No abstraction tax — no fighting frameworks
- Minimal dependencies
- Easiest to debug

**Weaknesses:**
- You rebuild common patterns from scratch (retries, state management, tool calling)
- No checkpointing unless you build it
- Harder to maintain as complexity grows

**Best for:** Simple LLM apps, learning how things work, projects where you need maximum control and minimal dependencies.

---

## Other Frameworks Worth Knowing

| Framework | Focus |
|---|---|
| **Haystack** (deepset) | RAG and search pipelines — similar to LlamaIndex, popular in enterprise |
| **DSPy** (Stanford) | Programmatic prompt optimization — treats prompts as learnable parameters, auto-tunes them |
| **Semantic Kernel** (Microsoft) | LLM orchestration for .NET/Python — Microsoft's answer to LangChain |
| **Pydantic AI** | Lightweight agent framework built on Pydantic — type-safe, minimal abstraction |
| **Instructor** | Small library for getting structured (Pydantic-validated) output from LLMs |
| **Marvin** | Lightweight — AI functions, classifiers, extractors as simple Python decorators |
| **OpenAI Agents SDK** | OpenAI's own agent framework — tool use, handoffs, guardrails |
| **Anthropic Agent SDK** | Anthropic's agent framework — similar idea, Claude-native |

---

## Framework Categories

```
Data/Retrieval focused:     LlamaIndex, Haystack
General LLM plumbing:       LangChain, Semantic Kernel
Agent orchestration:        LangGraph, CrewAI, Autogen, Pydantic AI
Prompt optimization:        DSPy
Structured output:          Instructor, Marvin
Provider-native:            OpenAI Agents SDK, Anthropic Agent SDK
```

---

## LangChain vs LangGraph — Key Differences

| | LangChain | LangGraph |
|---|---|---|
| Mental model | Linear chain | Directed graph with cycles |
| Branching | Limited (agents can loop, but you don't control the flow) | First-class conditional edges |
| State | Passed implicitly through chain | Explicit typed state object |
| Checkpointing | No | Yes (SQLite, Postgres, etc.) |
| Retry/replan | You build it yourself | Natural — just add edges back to earlier nodes |
| Best for | RAG, simple chains, prototyping | Complex agent workflows with cycles and error recovery |

---

## Decision Framework — When to Use What

```
Is it a single LLM call (prompt -> response)?
  -> Raw Python + SDK. No framework needed.

Is it a linear chain (step A -> step B -> step C, no branching)?
  -> Raw Python still works fine.
  -> LangChain if you need many integrations (vector stores, doc loaders).

Does it have loops, retries, or conditional branching?
  -> LangGraph if you also need checkpointing/resumability.
  -> Raw Python if the branching is simple enough (a few if/else).

Is it multiple agents with distinct roles collaborating?
  -> CrewAI or Autogen depending on the interaction pattern.

Are you prototyping fast and need 10+ integrations?
  -> LangChain for speed to demo.

Is the core problem "connect LLM to my data"?
  -> LlamaIndex (or Haystack for enterprise).
```

---

## Do You Always Need a Framework?

**No.** The honest answer:

- **Most LLM apps are simpler than people think.** A single API call with good prompting solves a surprising number of problems. No framework needed.
- **Frameworks earn their place when complexity is real** — when you have genuine cycles, state management across many steps, or need checkpointing. Not when you *might* need them someday.
- **The cost of a framework is permanent** — you inherit its abstractions, its bugs, its upgrade cycle, its way of thinking. You should adopt one because the problem demands it, not because it's trendy.
- **Understanding the raw patterns first is always valuable.** If you can't build it without the framework, you won't debug it with the framework.

**The right default is: start with raw Python, adopt a framework when the pain is real and specific.**

---

## The Ecosystem Is Fragmented and Moving Fast

New frameworks appear regularly, existing ones merge ideas from each other. The fundamentals underneath are always the same:
1. Call an LLM
2. Parse the output
3. Connect to tools/data
4. Manage state

If you understand those fundamentals from raw Python, picking up any framework becomes straightforward — they're all packaging the same patterns differently.
