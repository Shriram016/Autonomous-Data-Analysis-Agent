-- Runs once, the first time the Postgres container starts with an empty volume,
-- inside the "adaa" database. Roles (adaa_reader, adaa_agent, ...) are added by the slice
-- that first needs each one.

CREATE EXTENSION IF NOT EXISTS vector;  -- pgvector: store and search embeddings

CREATE SCHEMA IF NOT EXISTS business;      -- Olist data (read-only for the agent)
CREATE SCHEMA IF NOT EXISTS agent;         -- seller flags, tasks, audit, preferences, feedback
CREATE SCHEMA IF NOT EXISTS conversation;  -- turns, checkpoints, stored results
CREATE SCHEMA IF NOT EXISTS staging;       -- daily loads before validate-then-publish
