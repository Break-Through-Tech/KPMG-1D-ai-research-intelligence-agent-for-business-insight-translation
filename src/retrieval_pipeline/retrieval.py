"""arXiv cs.AI Retrieval

Downloads the most recent cs.AI papers (https://arxiv.org/list/cs.AI/recent) into data/downloaded/.
"""

import os
import csv
import urllib.request
import arxiv

from retrieval_pipeline.config import RetrievalConfig

FIELDS = ["id", "title", "authors", "published", "categories", "url", "abstract"]


class PaperRetriever:
    """Downloads the newest arXiv papers and records them in metadata.csv."""
    def __init__(self, config=RetrievalConfig()):
        # Where the PDFs + metadata are saved (set in config.py)
        self.config = config
        self.out_dir = config.resolve(config.downloaded_directory)
        self.meta_path = config.resolve(config.metadata_path)
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
        """Where a paper's PDF lives on disk: data/downloaded/<arxiv_id>.pdf"""
        return os.path.join(self.out_dir, f"{paper_id}.pdf")

    def load_known_ids(self):
        """Create the folder + CSV if needed and return the ids already in the CSV."""
        os.makedirs(self.out_dir, exist_ok=True)
        if not os.path.exists(self.meta_path):
            with open(self.meta_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(FIELDS)
        with open(self.meta_path, encoding="utf-8") as f:
            return {row["id"] for row in csv.DictReader(f)}

    def save_pdf(self, paper_id, pdf_bytes):
        """Write the PDF bytes to disk."""
        with open(self.pdf_path(paper_id), "wb") as f:
            f.write(pdf_bytes)

    def save_metadata(self, paper):
        """Append the paper's details as a row in metadata.csv and return them as a dict."""
        row = {
            "id": paper.get_short_id(),
            "title": paper.title,
            "authors": ", ".join(a.name for a in paper.authors),
            "published": paper.published.date(),
            "categories": ", ".join(paper.categories),
            "url": paper.entry_id,
            "abstract": " ".join(paper.summary.split()),
        }
        with open(self.meta_path, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writerow(row)
        return row

    def download_latest(self, n=10):
        """The "button": get the n newest papers, download + record the new ones.
        Returns the list of newly added papers (empty if there was nothing new)."""
        known_ids = self.load_known_ids()
        new_papers = []
        for paper in self.get_recent_papers(n):
            paper_id = paper.get_short_id()
            if not os.path.exists(self.pdf_path(paper_id)):  # also fills in a missing PDF for a paper already in the CSV
                self.save_pdf(paper_id, self.get_pdf(paper.pdf_url))
            if paper_id not in known_ids:
                new_papers.append(self.save_metadata(paper))
        return new_papers


if __name__ == "__main__":
    # Press the button: run this whenever you want the latest papers
    new_papers = PaperRetriever().download_latest(10)
