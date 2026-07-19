from __future__ import annotations


FACET_TYPES = [
    "person",
    "organization",
    "event",
    "place",
    "time",
    "concept",
    "quantity",
    "action",
    "result",
]

GRAPH_TYPE_TO_FACET = {
    "Person": "person",
    "Organization": "organization",
    "Event": "event",
    "Place": "place",
    "Time": "time",
    "Concept": "concept",
}

FACET_TO_GRAPH_TYPES = {
    "person": ["Person"],
    "organization": ["Organization"],
    "event": ["Event"],
    "place": ["Place"],
    "time": ["Time"],
    "concept": ["Concept"],
}

RELATION_TYPES = [
    "PARTICIPATED_IN",
    "OCCURRED_AT",
    "LOCATED_IN",
    "RELATED_TO",
    "CAUSES",
    "RESULTS_IN",
    "BEFORE",
    "AFTER",
]


def empty_facets() -> dict[str, list[str]]:
    return {facet_type: [] for facet_type in FACET_TYPES}
