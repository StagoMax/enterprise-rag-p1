from enterprise_rag.models import Route
from enterprise_rag.router import RuleBasedRouter


def test_graph_intent_beats_version_number_exact_match() -> None:
    decision = RuleBasedRouter().route(
        "From the document IBM WebSphere 8.5.5 security bulletin, "
        "follow its documented reference and identify the related document."
    )

    assert decision.route == Route.RAG
    assert decision.graph_expansion is True


def test_document_number_still_uses_exact_search_without_graph_intent() -> None:
    decision = RuleBasedRouter().route("Find document number swg22010419.")

    assert decision.route == Route.EXACT_SEARCH
    assert decision.graph_expansion is False
