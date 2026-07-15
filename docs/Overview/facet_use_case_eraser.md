# Eraser Flow: Facet Graph Retrieval

Paste this block into Eraser.io.

```text
title Facet Graph Retrieval

direction right

Claim [label: "Input claim", shape: oval, color: blue]

Extract [label: "Extract facets", color: blue]
Match [label: "Match facets to graph nodes", color: purple]

Retrieve [label: "Retrieve graph evidence", color: green] {
  Mentions [label: "Node mentions\nchunk -> node", color: green]
  Relations [label: "1-hop relations\nedge.source_chunk", color: orange]
}

Evidence [label: "Evidence candidates", color: teal] {
  Chunks [label: "Chunks"]
  FacetHits [label: "facet_hits\ncovered claim facets", color: blue]
  RelationHits [label: "relation_hits\nsupporting graph edges", color: orange]
}

Rank [label: "Dedup + rerank\nfacet coverage + relation score + text overlap", color: orange]
Verify [label: "LLM verifier", color: green]
Decision [label: "real / fake / uncertain", shape: oval, color: green]

Claim > Extract
Extract > Match
Match > Mentions
Match > Relations
Mentions > Chunks
Relations > Chunks
Chunks > FacetHits
Chunks > RelationHits
FacetHits > Rank
RelationHits > Rank
Rank > Verify
Verify > Decision
```
