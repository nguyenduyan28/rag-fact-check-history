# GraphRAG Placeholder

GraphRAG is intentionally separated from the text RAG baseline.

Planned modules:

- `extract_entities.py`: extract people, organizations, events, places, dates, and relations from textbook chunks.
- `build_graph.py`: build a graph JSON or database import format from extracted entities and `RELATE_TO` edges.
- `retrieve_graph.py`: retrieve graph neighborhoods relevant to `key + claim`.
- `verify_graph.py`: verify claims using graph evidence plus text evidence.

Do not call the current baseline GraphRAG until these modules are implemented.
