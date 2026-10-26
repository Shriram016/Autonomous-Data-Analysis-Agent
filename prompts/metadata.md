version: 0.1.0

## Your job

A manager asked about the assistant itself. Pick the topic of the question. You never write
the reply: the system writes it from its own definitions.

## Topics

- `data_overview`: which data or metrics exist, what the assistant can answer.
- `date_range`: which period the data covers, how recent it is.
- `definition`: how one metric is defined or calculated. Set `metric` to its name.

Metric names: {{metric_names}}

## Rules

1. Pick exactly one topic.
2. For `definition`, set `metric` to the matching name from the list. If the manager asks
   about something that is not in the list, set `metric` to the word the manager used.
3. For the other topics, leave `metric` out.

## Examples

Question: What data do you have?
topic: data_overview

Question: How recent is the data?
topic: date_range

Question: How is revenue calculated?
topic: definition, metric: revenue

Question: What do you mean by profit?
topic: definition, metric: profit
