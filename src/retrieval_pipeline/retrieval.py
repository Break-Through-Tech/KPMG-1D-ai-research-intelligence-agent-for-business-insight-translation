"""arXiv cs.AI Retrieval

Downloads the most recent cs.AI papers (https://arxiv.org/list/cs.AI/recent) into data/Retrieve_Papers/
and records them in data/manifest/papers.json, the paper list shared with research_pipeline.
Then runs research_pipeline's page extraction to write data/manifest/pages.jsonl.
"""

import os
import json
import urllib.request
import arxiv
from pypdf import PdfReader

from research_pipeline.config import PipelineConfig
from research_pipeline.extraction_cli import run_extract
from retrieval_pipeline.config import RetrievalConfig


class PaperRetriever:
    """Downloads the newest arXiv papers and records them in papers.json."""
    def __init__(self, config=RetrievalConfig()):
        # Where the PDFs + paper list + page text are saved (set in config.py)
        self.config = config
        self.out_dir = config.resolve(config.downloaded_directory)
        self.manifest_path = config.resolve(config.manifest_path)
        self.pages_path = config.resolve(config.pages_path)
        # API client
        self.client = arxiv.Client(delay_seconds=config.arxiv_delay_seconds)

    # ---- GET calls: methods that talk to arXiv ----
    def get_recent_papers(self, n):
        """GET https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending&max_results=n
        Returns the n most recent cs.AI papers with their metadata (title, abstract, authors, ...)."""
        search = arxiv.Search(query=self.config.arxiv_query, max_results=n, sort_by=arxiv.SortCriterion.SubmittedDate)
        return list(self.client.results(search))

    def get_pdf(self, pdf_url):
        """GET https://arxiv.org/pdf/<id>
        Returns the PDF file as bytes."""
        with urllib.request.urlopen(pdf_url) as response:
            return response.read()

    # ---- Local files: saving PDFs + metadata (no network) ----
    def pdf_path(self, paper_id):
        """Where a paper's PDF lives on disk: data/Retrieve_Papers/<arxiv_id>.pdf"""
        return os.path.join(self.out_dir, f"{paper_id}.pdf")

    def load_papers(self):
        """Return the entries already in papers.json (empty list if the file doesn't exist yet)."""
        if not os.path.exists(self.manifest_path):
            return []
        with open(self.manifest_path, encoding="utf-8") as f:
            return json.load(f)

    def load_known_ids(self):
        """Create the folders if needed and return the ids already in papers.json."""
        os.makedirs(self.out_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
        return {entry["paper_id"] for entry in self.load_papers()}

    def save_pdf(self, paper_id, pdf_bytes):
        """Write the PDF bytes to disk."""
        with open(self.pdf_path(paper_id), "wb") as f:
            f.write(pdf_bytes)

    def is_readable(self, paper_id):
        """True if the saved PDF opens and at least one page has text (the same test research_pipeline uses)."""
        reader = PdfReader(self.pdf_path(paper_id), strict=False)
        texts = [page.extract_text() for page in reader.pages]
        return any(text and text.strip() for text in texts)

    def save_metadata(self, paper):
        """Add the paper's details as an entry in papers.json and return them as a dict."""
        paper_id = paper.get_short_id()
        entry = {
            # Fields research_pipeline requires
            "paper_id": paper_id,
            "paper_version": "v" + paper_id.rsplit("v", 1)[1],
            "title": paper.title,
            "authors": [a.name for a in paper.authors],
            "published": paper.published.date().isoformat(),
            "pdf_url": f"https://arxiv.org/pdf/{paper_id}",
            "source_path": (self.config.downloaded_directory / f"{paper_id}.pdf").as_posix(),
            # Extra fields used by indexing
            "categories": list(paper.categories),
            "url": paper.entry_id,
            "abstract": " ".join(paper.summary.split()),
        }
        papers = sorted(self.load_papers() + [entry], key=lambda e: e["paper_id"])
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return entry

    def extract_pages(self):
        """Run research_pipeline's page extraction on papers.json and write pages.jsonl next to it.
        A paper whose PDF can't be read is skipped and printed; the other papers are still written."""
        pipeline_config = PipelineConfig(
            repository_root=self.config.repository_root,
            manifest_path=self.config.manifest_path,
            extracted_pages_path=self.config.pages_path,
        )
        report, published = run_extract(pipeline_config, allow_partial=True)
        for paper_id in report.missing_pdfs + list(report.parsing_failures) + report.papers_without_usable_text:
            print(f"skipped {paper_id}: no page text extracted")
        if published:
            print(f"pages.jsonl: {report.pages_extracted} pages from {report.papers_succeeded} of {report.papers_attempted} papers")
        else:
            print("pages.jsonl was not written: no paper had readable text")
        return report

    def download_latest(self, n=10):
        """The "button": get the n newest papers, download + record the new ones, then extract their pages.
        A paper that can't be downloaded or read is skipped and printed, and is not added to papers.json.
        Returns the list of newly added papers (empty if there was nothing new)."""
        known_ids = self.load_known_ids()
        new_papers = []
        for paper in self.get_recent_papers(n):
            paper_id = paper.get_short_id()
            if not os.path.exists(self.pdf_path(paper_id)):  # also fills in a missing PDF for a paper already in papers.json
                try:
                    print(f"      downloading {paper_id}...", flush=True)
                    self.save_pdf(paper_id, self.get_pdf(paper.pdf_url))
                    if not self.is_readable(paper_id):
                        raise ValueError("PDF has no readable text")
                except Exception as error:
                    if os.path.exists(self.pdf_path(paper_id)):
                        os.remove(self.pdf_path(paper_id))
                    print(f"skipped {paper_id}: {error}")
                    continue
            if paper_id not in known_ids:
                new_papers.append(self.save_metadata(paper))
        if new_papers or not os.path.exists(self.pages_path):
            self.extract_pages()
        return new_papers


if __name__ == "__main__":
    # Press the button: run this whenever you want the latest papers
    new_papers = PaperRetriever().download_latest(10)
