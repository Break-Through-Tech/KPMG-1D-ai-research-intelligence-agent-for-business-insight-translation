# The Idea
.

## Where the papers come from
We use the arXiv API: `GET https://export.arxiv.org/api/query?search_query=cat:cs.AI&sortBy=submittedDate&sortOrder=descending`.
It returns the newest papers in the AI category, the same list as https://arxiv.org/list/cs.AI/recent.
Each paper is identified by its arXiv id (e.g. `2609.35769v1`). That id links everything together.


### 1. Update papers
- Download the newest papers that we don't have yet. If nothing is new, nothing happens.
- Save each PDF and a row with its details (title, authors, date, link, abstract) in `metadata.csv`.
- Turn each new paper into vectors and store them in ChromaDB so it can be searched.

### 2. Ask a question
- **Stage 1 – find papers:** compare the question to every paper's title + abstract. Keep the top ~10 papers.
- **Stage 2 – find passages:** compare the question to chunks of full text, but only from those top papers.
- **Answer:** give the best passages to an LLM. It summarizes the findings, explains the business impact, and cites paper ids.
- The ids are looked up in `metadata.csv` to show titles and links.


## How search works
An embedding model (`all-MiniLM-L6-v2`) turns text into 384 numbers that represent its meaning.


Each paper's title + abstract is stored in ChromaDB as one embedding.

The question is embedded the same way, and ChromaDB returns the papers whose embeddings are most similar to it.

Next, a second table stores the full text of each paper as chunks, one embedding per chunk, each tagged with its paper id.
Using the paper ids from the first search, we retrieve the top k most similar chunks, but only from those papers.

