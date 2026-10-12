# Review search is hybrid (keyword + meaning), stored in PostgreSQL with pgvector

Reviews are found with hybrid search: PostgreSQL full-text search (exact words, product names) combined with vector similarity search (paraphrases, slang, e.g. "late" ≈ "took forever to arrive"), results merged. Vectors are stored with pgvector inside the same PostgreSQL as the business data.

## Why pgvector, on its own merits (not just "we already run PostgreSQL")

1. **Filtering by business data is the core need.** Hybrid questions ask for "reviews of *late* orders in *electronics*". With vectors beside the order tables, one SQL query filters by order data and ranks by similarity. A separate vector DB must either copy order fields into its metadata (and keep them in sync) or fetch candidates and filter in application code, which is slower and can miss results.
2. **Scale fit.** ~40k short reviews (400k at the 10× growth target) is small for an approximate-nearest-neighbour index like HNSW in pgvector. Dedicated vector DBs are built for tens of millions+: capacity we'd pay for in operations without using.
3. **No sync problem.** One store means no second copy to drift: a review is searchable in the same transaction it is loaded, which keeps the 24h freshness pipeline simple.
4. **Keyword + vector in one engine.** PostgreSQL full-text search provides the keyword half of hybrid search natively; many vector DBs need extra setup for it.
5. **One security boundary.** The same read-only role and query time limits cover review search; no second set of credentials or access rules.
6. **Portfolio breadth.** The builder's other RAG project uses ChromaDB; pgvector shows a different, production-common pattern.

Honest note: reason 1 depends on the structured data being in PostgreSQL; reasons 2–5 would favour pgvector at this scale regardless.

## Considered Options

- **Dedicated vector DB (Qdrant, Pinecone, Chroma, Weaviate).** Better at very large scale and vector-specific features (sharding, quantization, multi-tenancy), but adds a second system, data sync and separate security for no measurable benefit at ~40k reviews. Rejected.
- **Keyword-only or vector-only search.** Each misses what the other catches (paraphrases vs exact terms). Rejected.

## Revisit trigger

Reviews grow to millions, vector search becomes a measured latency/index-size problem, or review search must scale independently of the SQL workload.

## Questions that drove this

- What is the main query pattern: pure similarity, or similarity filtered by business data?
- What is the data volume now and at 10×, and what is each option built for?
- How many systems must be kept in sync and secured?
- Would this choice still hold if we weren't already running PostgreSQL?
