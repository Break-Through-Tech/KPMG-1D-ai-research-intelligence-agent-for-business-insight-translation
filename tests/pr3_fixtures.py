"""Hand-sized citation fixtures shared by the PR3 contract tests."""

from research_pipeline.models import ExtractedPage, PaperMetadata
from tests.test_ingestion import VALID_RECORD


def paper():
    return PaperMetadata.from_dict(VALID_RECORD)


def page(text="abcdefghij", number=1):
    return ExtractedPage.from_dict({**VALID_RECORD, "page_number": number, "text": text})
