"""Contract defaults stay optional so existing constructors keep working."""

import unittest
from datetime import date

from kyc_copilot.contracts.models import CaseEvidence, Document, ToolResult


class ContractDefaultTests(unittest.TestCase):
    def test_new_document_and_evidence_fields_default_empty(self):
        doc = Document("S", "C1", "intake", True, date(2026, 10, 1), "ENT-1")
        self.assertEqual(doc.company_name, None)
        self.assertEqual(doc.label_conflicts, ())
        self.assertFalse(doc.empty)
        self.assertFalse(doc.review_date_unreadable)
        evidence = CaseEvidence(
            "C1",
            date(2026, 10, 1),
            "ENT-1",
            "attached",
            True,
            None,
            None,
            None,
            None,
        )
        self.assertIsNone(evidence.company_name)
        self.assertEqual(evidence.document_faults, ())
        self.assertEqual(ToolResult("customer", True, None, 1).attempt_log, ())
