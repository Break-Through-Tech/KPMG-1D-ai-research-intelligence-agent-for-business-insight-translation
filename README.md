# AI Research Intelligence Agent for Business Insight Translation
---

### 👥 **Team Members**

**Example:**

| Name                   | GitHub Handle | Contribution                                                             |
|------------------------|---------------|--------------------------------------------------------------------------|
| Bhoomi Patni           | @bhoomipatni  |                                                                          |
| Pratima Nallapareddy   | @PratimaNallapareddy|                                                                          |
| Brianna Wilkins        | @b1wilks             |                                                                          |
| Samita Bomasamudram    | @samita-boma  |                                                                          |
| Matias Freire          | @MatiasPF1       |                                                                          |
| Chaitanya Raj Shah     | @cr-shah      |                                                                          |
| Madison Lizbinski      | @Madisonlizbinski   |                                                                          |

---

## 🎯 **Project Highlights**

- Fixed manifest for the five supplied research PDFs and validated citation metadata.
- Reproducible paper ingestion with explicit arXiv collection and offline tests.
- Page-by-page PDF extraction with original page citations and conservative cleanup.

---

## 👩🏽‍💻 **Setup and Installation**

The current implementation validates a fixed paper manifest, prepares a paper
catalog, and extracts citation-preserving PDF pages. Use Python 3.11 or newer
and run from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
PYTHONPATH=src python -m research_pipeline.ingestion_cli ingest
PYTHONPATH=src python -m research_pipeline.extraction_cli
PYTHONPATH=src python -m unittest discover -s tests -v
```

Ingestion uses the standard library; extraction uses pinned `pypdf==6.1.1`.
The default commands use the five supplied PDFs without network access.
Ingestion writes `data/processed/papers.jsonl`; extraction writes
`data/processed/pages.jsonl`. Complete runs publish staged output. Partial or
failed extraction preserves previous pages by default; `--allow-partial`
explicitly allows usable incomplete output but still returns exit code 2.
Total failure returns 3 and never publishes.

The independently tested ingestion/extraction boundary passes 32 offline tests.
The supplied corpus produces 104 pages and 373,982 cleaned characters from 5/5
papers, with valid citation metadata and byte-identical repeated outputs.

Generated catalogs and newly downloaded PDFs are ignored by Git; the supplied
PDFs remain tracked in their original locations. Optional collection accepts
explicit versioned arXiv IDs and downloads PDFs only when requested.

See [the pipeline guide](docs/pipeline.md) for commands, data contracts,
validation, PDF limitations, and the proposed handoff to retrieval work.
Chunking, embeddings, and generation remain follow-up work.

---

## 🏗️ **Project Overview**

**Describe:**

**Connection to Break Through Tech AI Program**: This project is part of the Break Through Tech AI Studio, where students work with industry partners to apply AI and machine learning concepts to real-world business challenges. Our team is applying concepts including natural language processing, retrieval-augmented generation (RAG), embeddings, vector search, and large language models to develop a practical AI solution.

**AI Studio host company, project objective, and scope:**: Our AI Studio host company is KPMG, and our project focuses on developing an AI Research Intelligence Agent for Business Insight Translation. The objective is to help users identify relevant AI research, retrieve supporting information from research papers, generate concise summaries with citations, and translate technical findings into actionable business insights. The project scope includes building a research data ingestion pipeline, developing and evaluating a RAG-based retrieval system, implementing LLM-based summarization, and creating a framework for translating technical research into business-relevant recommendations.

**Real World Impact**: AI research is advancing rapidly, making it difficult for businesses to efficiently identify and understand developments that may affect their strategies, products, and operations. Our project aims to reduce the time and effort required to navigate technical research by connecting relevant academic findings with practical business applications. A successful solution could help professionals more efficiently monitor emerging AI developments, evaluate their relevance, and make more informed decisions about potential opportunities and applications.


---

## 📊 **Data Exploration**

**You might consider describing the following (as applicable):**

* The dataset(s) used: origin, format, size, type of data
* Data exploration and preprocessing approaches
* Insights from your Exploratory Data Analysis (EDA)
* Challenges and assumptions when working with the dataset(s)

**Potential visualizations to include:**

* Plots, charts, heatmaps, feature visualizations, sample dataset images

---

## 🧠 **Model Development**

**You might consider describing the following (as applicable):**

* Model(s) used (e.g., CNN with transfer learning, regression models)
* Feature selection and Hyperparameter tuning strategies
* Training setup (e.g., % of data for training/validation, evaluation metric, baseline performance)


---

## 📈 **Results & Key Findings**

**You might consider describing the following (as applicable):**

* Performance metrics (e.g., Accuracy, F1 score, RMSE)
* How your model performed
* Insights from evaluating model fairness

**Potential visualizations to include:**

* Confusion matrix, precision-recall curve, feature importance plot, prediction distribution, outputs from fairness or explainability tools

---

## 🚀 **Next Steps**

**You might consider addressing the following (as applicable):**

* What are some of the limitations of your model?
* What would you do differently with more time/resources?
* What additional datasets or techniques would you explore?

---

## 📝 **License**

Specify how your project can be used by others. Choose an appropriate license and link it here (e.g., MIT, Apache 2.0). Make sure your Challenge Advisor approves of the selected license type. 

**Example:**
This project is licensed under the MIT License.

---

## 📄 **References** (Optional but encouraged)

Cite relevant papers, articles, or resources that supported your project.

---

## 🙏 **Acknowledgements** (Optional but encouraged)

Thank your Challenge Advisor, host company representatives, TA, and others who supported your project.
