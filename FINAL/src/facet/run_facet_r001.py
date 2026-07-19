from __future__ import annotations

import argparse

from src.common.io import load_yaml
from src.facet.evaluate_facet import run_evaluate
from src.facet.extract_claim_facets import run_extract
from src.facet.extract_claim_facets import load_dotenv
from src.facet.match_facets import run_match
from src.facet.retrieve_evidence import run_retrieve
from src.facet.rerank_evidence import run_rerank


def main() -> None:
    parser = argparse.ArgumentParser(description="Run R001 FacetGraphRAG MVP pipeline.")
    parser.add_argument("--config", default="configs/facet/facet.yaml")
    parser.add_argument("--limit", type=int, default=None, help="Override config run.limit.")
    parser.add_argument("--workers", type=int, default=None, help="Facet extraction workers.")
    parser.add_argument("--batch-size", type=int, default=None, help="Claims per OpenAI request during facet extraction.")
    parser.add_argument("--use-llm", action="store_true", help="Use OpenAI with OPENAI_API_KEY loaded from .env.")
    parser.add_argument("--no-llm", action="store_true", help="Force deterministic facet extraction.")
    parser.add_argument("--no-resume", action="store_true", help="Ignore existing claim_facets output.")
    args = parser.parse_args()

    load_dotenv()
    config = load_yaml(args.config)
    use_llm = True if args.use_llm else False if args.no_llm else None

    print("Step 1/5: extracting claim facets")
    run_extract(
        config,
        limit=args.limit,
        use_llm=use_llm,
        no_resume=args.no_resume,
        workers=args.workers,
        batch_size=args.batch_size,
    )
    print("Step 2/5: matching facets to graph")
    run_match(config)
    print("Step 3/5: retrieving 1-hop graph evidence")
    run_retrieve(config)
    print("Step 4/5: reranking evidence")
    run_rerank(config)
    print("Step 5/5: writing EDA report")
    eda = run_evaluate(config)
    print(f"Done. Claims={eda['claims']} evidence_coverage={eda['evidence_coverage']:.3f}")
    print(f"Report: {config['paths']['eda_report']}")


if __name__ == "__main__":
    main()
