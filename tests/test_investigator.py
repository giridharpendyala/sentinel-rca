"""Automated unit and integration test suite for the Multi-Agent Incident Investigator."""

import pytest
from agents.masking import mask_text
from agents.state import RCAResult, InvestigationState
from agents.graph import build_graph
from eval.evaluators import (
    evaluate_tool_selection,
    evaluate_investigation_path,
    evaluate_hallucination,
    evaluate_efficiency,
)


def test_log_masking_sensitive_fields():
    """Verify that emails, card numbers, and JWTs are redacted."""
    raw_log = (
        'Customer user.name@domain.com purchased with card 4111-2222-3333-4444 '
        'using token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozG6'
    )
    masked = mask_text(raw_log)

    assert "user.name@domain.com" not in masked
    assert "***REDACTED-EMAIL***" in masked

    assert "4111-2222-3333-4444" not in masked
    assert "***REDACTED-CARD***" in masked

    assert "eyJhbGciOi" not in masked
    assert "***REDACTED-JWT***" in masked


def test_rca_result_model():
    """Verify that RCAResult enforces structured outputs correctly."""
    result = RCAResult(
        root_cause="Payment database pool exhaustion after deploy",
        confidence="high",
        evidence=["Active pool connections hit maximum (50/50)"],
        recommended_action="Restore DB_POOL_SIZE to 100",
        requires_approval=True,
    )
    assert result.confidence == "high"
    assert result.requires_approval is True
    assert len(result.evidence) == 1


def test_graph_build():
    """Verify the StateGraph builds and compiles with all required specialist nodes."""
    graph = build_graph()
    assert graph is not None
    # Check that key specialist nodes are compiled in the graph
    node_keys = graph.nodes.keys()
    for expected_node in ("supervisor", "metrics", "traces", "logs", "changes", "rca_agent", "remediation"):
        assert expected_node in node_keys


def test_evaluator_tool_selection():
    """Verify tool selection precision, recall, and F1 calculation."""
    used = ["metrics", "traces", "logs"]
    expected = ["metrics", "traces", "logs", "changes"]
    res = evaluate_tool_selection(used, expected)

    assert res["score"] > 0.8
    assert "changes" in res["missing"]
    assert res["recall"] == 0.75
    assert res["precision"] == 1.0


def test_evaluator_investigation_path():
    """Verify path scoring detects repeated loops and enforces limits."""
    # Good path
    good_path = ["metrics", "traces", "logs", "changes"]
    score_good = evaluate_investigation_path(good_path)
    assert score_good["score"] >= 0.9

    # Path with consecutive repetitions
    loopy_path = ["metrics", "metrics", "metrics", "metrics"]
    score_loopy = evaluate_investigation_path(loopy_path)
    assert score_loopy["score"] < score_good["score"]


def test_evaluator_hallucination_detection():
    """Verify hallucination evaluator flags unsupported numeric assertions."""
    collected_evidence = [
        {"summary": "p95 latency rose to 4.5s and error rate is 25%"},
    ]

    # Grounded statement
    grounded_rca = "Latency reached 4.5s with an error rate of 25%."
    res_grounded = evaluate_hallucination(grounded_rca, collected_evidence)
    assert res_grounded["score"] == 1.0

    # Hallucinated statement claiming 99.9% and 500 connections
    hallucinated_rca = "Latency hit 99.9s and pool dropped 500 connections."
    res_hallucinated = evaluate_hallucination(hallucinated_rca, collected_evidence)
    assert res_hallucinated["score"] < 1.0


def test_evaluator_efficiency():
    """Verify efficiency scoring normalizes tool calls and latency."""
    tool_log = [
        {"agent": "metrics", "latency_ms": 120},
        {"agent": "traces", "latency_ms": 250},
        {"agent": "logs", "latency_ms": 180},
    ]
    res = evaluate_efficiency(iterations=4, tool_call_log=tool_log, duration_seconds=12.5)
    assert res["score"] >= 0.8
    assert res["total_tool_calls"] == 3


def test_api_health_and_incidents():
    """Verify that the FastAPI test API serves health and incident fixtures."""
    from fastapi.testclient import TestClient
    from agents.api import app

    client = TestClient(app)

    health_res = client.get("/healthz")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "ok"

    incidents_res = client.get("/api/incidents")
    assert incidents_res.status_code == 200
    incidents = incidents_res.json().get("incidents", [])
    assert len(incidents) == 10
    assert incidents[0]["id"] == "INC-01"
