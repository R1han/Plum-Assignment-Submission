"""Extraction adapter tests (fixture path; vision is exercised via mocks)."""

import pytest

from app.agents.extraction import ExtractionError, ExtractionService, FixtureAdapter
from app.models.claim import DocumentContent, DocumentInput, DocumentQuality, DocumentType
from app.models.extraction import consolidate_facts


def test_fixture_adapter_passthrough():
    doc = DocumentInput(
        file_id="F007",
        actual_type="PRESCRIPTION",
        content=DocumentContent(
            doctor_name="Dr. Arun Sharma",
            patient_name="Rajesh Kumar",
            diagnosis="Viral Fever",
            medicines=["Paracetamol 650mg"],
        ),
    )
    extracted = FixtureAdapter().extract(doc)
    assert extracted.doc_type == DocumentType.PRESCRIPTION
    assert extracted.content.diagnosis == "Viral Fever"
    assert extracted.extraction_confidence == 1.0
    assert extracted.source == "fixture"


def test_fixture_adapter_unreadable_strips_content():
    doc = DocumentInput(
        file_id="F004", actual_type="PHARMACY_BILL", quality="UNREADABLE",
        content=DocumentContent(total=800),
    )
    extracted = FixtureAdapter().extract(doc)
    assert extracted.quality == DocumentQuality.UNREADABLE
    assert extracted.extraction_confidence == 0.0
    assert extracted.content.total is None 
    assert extracted.warnings


def test_fixture_adapter_patient_name_on_doc():
    doc = DocumentInput(
        file_id="F005", actual_type="PRESCRIPTION",
        patient_name_on_doc="Rajesh Kumar",
    )
    extracted = FixtureAdapter().extract(doc)
    assert extracted.content.patient_name == "Rajesh Kumar"


def test_fixture_adapter_rejects_empty_input():
    with pytest.raises(ExtractionError):
        FixtureAdapter().extract(DocumentInput(file_id="F0"))


def test_service_routes_fixture_without_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    service = ExtractionService()
    doc = DocumentInput(file_id="F1", actual_type="HOSPITAL_BILL",
                        content=DocumentContent(total=100))
    assert service.extract(doc).source == "fixture"


def test_consolidate_facts_merges_documents():
    rx = FixtureAdapter().extract(DocumentInput(
        file_id="F1", actual_type="PRESCRIPTION",
        content=DocumentContent(
            patient_name="Rajesh Kumar", diagnosis="Viral Fever",
            doctor_registration="KA/45678/2015",
        ),
    ))
    bill = FixtureAdapter().extract(DocumentInput(
        file_id="F2", actual_type="HOSPITAL_BILL",
        content=DocumentContent(
            patient_name="Rajesh Kumar", hospital_name="City Clinic",
            line_items=[{"description": "Consultation Fee", "amount": 1000}],
            total=1000,
        ),
    ))
    facts = consolidate_facts([rx, bill])
    assert facts.diagnosis == "Viral Fever"
    assert facts.hospital_name == "City Clinic"
    assert facts.bill_total == 1000
    assert len(facts.line_items) == 1
    assert facts.patient_names == ["Rajesh Kumar"]
    assert facts.extraction_confidence == 1.0


def test_consolidate_facts_min_confidence():
    good = FixtureAdapter().extract(DocumentInput(
        file_id="F1", actual_type="PRESCRIPTION", quality="GOOD",
        content=DocumentContent(diagnosis="X"),
    ))
    partial = FixtureAdapter().extract(DocumentInput(
        file_id="F2", actual_type="HOSPITAL_BILL", quality="PARTIAL",
        content=DocumentContent(total=500),
    ))
    facts = consolidate_facts([good, partial])
    assert facts.extraction_confidence == 0.6  
