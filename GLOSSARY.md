# ADAA V3

An AI agent that answers a business manager's natural-language questions over a company's structured records and customer text.

## Language

**Manager**:
The primary user: a non-technical business person who asks questions in plain English and cannot verify the answer themselves.
_Avoid_: User (too generic), analyst, client

## Data and actions

**Business data**:
The company's records and reviews (orders, items, sellers, customers, reviews). The agent only reads it.
_Avoid_: Source data, production data

**Action**:
A change the agent makes on the manager's behalf, only after the manager approves it; written to agent-owned tables, never to business data.
_Avoid_: Write, operation, update

**Seller flag**:
An action marking a seller for review, with a reason.
_Avoid_: Seller alert, mark

**Task**:
An action creating a to-do for a team (e.g. logistics), with a reason.
_Avoid_: Follow-up task (clashes with Follow-up), ticket

## Computing numbers

**Semantic layer**:
The single place where every metric, dimension, table relationship and messy-data rule is defined; the agent can only compute what it defines.
_Avoid_: Business layer, metrics layer, menu

**Metric**:
A defined business number (e.g. revenue, late-delivery rate), including which rows count.
_Avoid_: Measure, KPI, calculation

**Dimension**:
A defined way to break a metric down (e.g. state, product category, month).
_Avoid_: Breakdown, group-by, attribute

**Structured request**:
What the LLM fills in for the semantic layer: metric, dimensions, filters, time period, sort and limit.
_Avoid_: Query, plan, form

**Review topic**:
A label from a fixed list (e.g. late delivery, damaged item) attached to each review at load time, so complaints can be counted.
_Avoid_: Theme (themes are what the answer groups quotes into), category (clashes with product category)

**Escalation**:
A task the manager creates to hand a question the agent could not answer to a human analyst.
_Avoid_: Handoff, ticket, referral

## Questions

**Question**:
What the manager types, in plain English.
_Avoid_: Query, prompt, request

**Turn**:
One question and the agent's reply within a conversation.
_Avoid_: Message, exchange, interaction

**Follow-up**:
A question that cannot be understood without earlier turns of the conversation.
_Avoid_: Contextual query

**Hybrid question**:
A question that needs both numbers from the records and what customers said in reviews.
_Avoid_: Mixed query, combined question

**Ambiguous question**:
A question whose words are understood but allow more than one reasonable meaning (e.g. "best customers").
_Avoid_: Vague question, unclear question

**Unknown business term**:
A business word the agent has no definition for (e.g. "GMV"); distinct from ambiguity.
_Avoid_: Jargon, unknown keyword

**Unanswerable question**:
An on-topic question the data cannot answer, including one built on a false premise.
_Avoid_: Invalid question, out-of-scope question

**Route**:
The category the router assigns a question: numbers, reviews, hybrid, clarify, refuse, off-topic, metadata or action.
_Avoid_: Intent, path, category

**Off-topic question**:
A question unrelated to the company's data.
_Avoid_: Unanswerable, irrelevant query
