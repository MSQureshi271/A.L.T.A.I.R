"""
Integration & Regression Tests for Email Attachments & Document-Attached Emails.
"""
from __future__ import annotations

import unittest
from app.capabilities.documents.models import DocumentRecord
from app.config.settings import settings
from app.ai.planner.planner_schema import TaskStep
from app.providers.google.gmail.api import stage_email_with_attachment


class TestEmailAttachmentsIntegration(unittest.TestCase):

    def test_document_record_fields(self):
        record = DocumentRecord(
            id="test-123",
            user_id="user-1",
            filename="invoice.pdf",
            display_name="invoice",
            file_type="pdf",
            mime_type="application/pdf",
            storage_path="user-1/test-123/invoice.pdf",
            file_size_bytes=1024,
            status="ready",
            source_type="email_attachment",
            source_email_id="msg-999",
        )
        self.assertEqual(record.source_type, "email_attachment")
        self.assertEqual(record.source_email_id, "msg-999")

    def test_tier_quota_limit(self):
        # Default tier is premium -> limit is 0 (unlimited)
        self.assertEqual(settings.upload_limit_bytes, 0)

    def test_stage_email_with_attachment_no_matches(self):
        result = stage_email_with_attachment(
            recipient="test@example.com",
            subject="Test Subject",
            body="Test Body",
            document_names=["non_existent_document_12345"],
        )
        self.assertEqual(result.get("type"), "clarification_needed")
        self.assertIn("No document named", result.get("question", ""))


if __name__ == "__main__":
    unittest.main()
