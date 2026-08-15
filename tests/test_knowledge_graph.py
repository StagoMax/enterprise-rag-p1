from __future__ import annotations

import json

from enterprise_rag.knowledge_extraction import (
    TerraDocumentReviewer,
    _expand_compact_result,
)
from enterprise_rag.knowledge_graph import (
    DocumentKnowledge,
    KnowledgeRelationType,
    SectionType,
    extract_rule_entities,
    parse_sections,
    propose_rule_relations,
    review_units,
)
from scripts.build_p3_knowledge_graph import project_document_relations


class AcceptingReviewModel:
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        assert "document structure" in system_prompt
        payload = json.loads(user_prompt)
        return json.dumps(
            {
                "section_reviews": [
                    {
                        "section_id": section["section_id"],
                        "section_type": section["proposed_type"],
                        "confidence": 0.99,
                        "reason": "heading and content agree",
                    }
                    for section in payload["sections"]
                ],
                "entities": [
                    {
                        "id": entity["id"],
                        "decision": "accept",
                        "surface": entity["surface"],
                        "canonical_name": entity["canonical_name"],
                        "entity_type": entity["entity_type"],
                        "section_id": entity["section_id"],
                        "evidence": entity["evidence"],
                        "confidence": entity["confidence"],
                        "normalization_reason": "canonical identifier or approved alias",
                    }
                    for entity in payload["proposed_entities"]
                ],
                "rule_reviews": [
                    {
                        "rule_id": relation["rule_id"],
                        "decision": "accept",
                        "relation": relation["relation"],
                        "source_ref": relation["source_ref"],
                        "target_ref": relation["target_ref"],
                        "evidence": relation["evidence"],
                        "confidence": relation["confidence"],
                        "reason": "the evidence directly supports the rule",
                    }
                    for relation in payload["proposed_rule_relations"]
                ],
                "new_relations": [],
                "document_validation": {"valid": True, "issues": []},
            }
        )


class OmittingOnceReviewModel(AcceptingReviewModel):
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            payload = json.loads(user_prompt)
            return json.dumps(
                {
                    "section_reviews": [
                        {
                            "section_id": section["section_id"],
                            "section_type": section["proposed_type"],
                            "confidence": 0.99,
                        }
                        for section in payload["sections"]
                    ],
                    "entities": [],
                    "rule_reviews": [],
                    "new_relations": [],
                    "document_validation": {"valid": True, "issues": []},
                }
            )
        return super().complete(system_prompt, user_prompt)


def test_compact_review_protocol_expands_losslessly() -> None:
    expanded = _expand_compact_result(
        {
            "s": [["d:section:0", "title", 0.99]],
            "ea": ["E1"],
            "ec": [["E2", "IBM Db2", "product", 0.98]],
            "er": [["E3", "not an entity"]],
            "ra": ["R1"],
            "rr": [["R2", "negated in the text"]],
            "ne": [],
            "nr": [],
            "v": {"valid": True, "issues": []},
        }
    )

    assert [row["decision"] for row in expanded["entities"]] == [
        "accept",
        "accept",
        "reject",
    ]
    assert expanded["entities"][1]["canonical_name"] == "IBM Db2"
    assert [row["decision"] for row in expanded["rule_reviews"]] == [
        "accept",
        "reject",
    ]
    assert expanded["document_validation"]["valid"] is True


def test_omitted_reviews_receive_targeted_intelligent_retry() -> None:
    text = "TITLE\nExample\n\nENVIRONMENT\nIBM DB2 9.7\n"
    sections = parse_sections("swg100", text)
    entities = extract_rule_entities(sections)
    relations = propose_rule_relations("swg100", sections, entities, set())
    model = OmittingOnceReviewModel()
    result = TerraDocumentReviewer(model).review(
        document_id="swg100",
        title="Example",
        document_text=text,
        sections=sections,
        entities=entities,
        relations=relations,
        units=review_units(sections, entities, relations),
    )

    audit = result[6]
    assert model.calls == 2
    assert audit["entity_extraction"]["reviewed"] == audit["entity_extraction"][
        "proposed"
    ]
    assert audit["deterministic_rule_review"]["reviewed"] == audit[
        "deterministic_rule_review"
    ]["proposed"]


def reviewed_document(document_id: str, text: str) -> DocumentKnowledge:
    sections = parse_sections(document_id, text)
    entities = extract_rule_entities(sections)
    relations = propose_rule_relations(
        document_id,
        sections,
        entities,
        {"swg100", "swg200"},
    )
    reviewer = TerraDocumentReviewer(AcceptingReviewModel())
    reviewed = reviewer.review(
        document_id=document_id,
        title="Example",
        document_text=text,
        sections=sections,
        entities=entities,
        relations=relations,
        units=review_units(sections, entities, relations),
    )
    return DocumentKnowledge(
        document_id=document_id,
        checksum="checksum",
        extraction_version="test",
        model="gpt-5.6-terra",
        sections=reviewed[0],
        nodes=reviewed[1],
        mentions=reviewed[2],
        relations=reviewed[3],
        deterministic_entity_count=len(entities),
        deterministic_relation_count=len(relations),
        llm_request_count=reviewed[5],
        validation_rejections=reviewed[4],
        intelligence_audit=reviewed[6],
    )


def test_structure_entities_rules_and_terra_validation_form_one_pipeline() -> None:
    text = """Title: DB2 support note

ENVIRONMENT
IBM DB2 9.7
IBM DB2 9.7

ANSWER
See swg200 for the supported procedure.
"""
    result = reviewed_document("swg100", text)

    assert any(section.section_type == SectionType.ENVIRONMENT for section in result.sections)
    assert all("terra-review" in section.extraction_method for section in result.sections)
    assert any(node.canonical_name == "IBM Db2" for node in result.nodes)
    assert any(node.canonical_name == "swg200" for node in result.nodes)
    assert any(
        relation.relation == KnowledgeRelationType.REFERENCES
        for relation in result.relations
    )
    assert result.llm_request_count == 1
    assert result.intelligence_audit["structure_parsing"] == {
        "proposed": 3,
        "reviewed": 3,
    }
    rule_audit = result.intelligence_audit["deterministic_rule_review"]
    assert rule_audit["proposed"] > 1
    assert rule_audit["reviewed"] == rule_audit["proposed"]


def test_projected_graph_preserves_references_and_adds_reviewed_shared_entity_edges() -> None:
    first = reviewed_document(
        "swg100",
        "Title: First\n\nSYMPTOM\nSQL1227N occurs in IBM DB2 9.7.\n",
    )
    second = reviewed_document(
        "swg200",
        "Title: Second\n\nANSWER\nResolve SQL1227N for IBM DB2 9.7.\n",
    )

    projected, counts = project_document_relations(
        [
            {"document_id": "swg100"},
            {"document_id": "swg200"},
        ],
        [first, second],
        [
            {
                "source_id": "swg100",
                "target_id": "swg200",
                "relation": "references",
                "confidence": 1.0,
                "evidence_anchor": "See swg200.",
            }
        ],
        max_entity_documents=20,
        neighbors_per_document=3,
    )

    assert any(row["relation"] == "references" for row in projected)
    assert any(row["relation"] == "related_to" for row in projected)
    assert counts["baseline_explicit_reference"] == 1


def test_split_review_units_only_include_entities_inside_each_text_window() -> None:
    text = "TITLE\nExample\n\nCONTENT\n" + "A" * 1800 + " SQL1227N " + "B" * 1800
    sections = parse_sections("swg100", text)
    entities = extract_rule_entities(sections)
    units = review_units(sections, entities, [], max_characters=1000)

    containing = [
        unit
        for unit in units
        if any(entity.canonical_name == "SQL1227N" for entity in unit["entities"])
    ]
    assert len(containing) == 1
    assert "SQL1227N" in containing[0]["sections"][0].content
