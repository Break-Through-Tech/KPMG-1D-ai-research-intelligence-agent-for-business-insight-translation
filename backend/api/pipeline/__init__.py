"""Routes that run the src/ pipeline (arXiv download, passages, Chroma indexing).

Retrieve and store both rewrite pipeline files, so they share one lock: only one may run at a time.
"""

import threading

pipeline_lock = threading.Lock()
