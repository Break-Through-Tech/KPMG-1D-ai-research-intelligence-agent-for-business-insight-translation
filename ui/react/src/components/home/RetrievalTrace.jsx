import EmbeddingCard from "../EmbeddingCard.jsx";

// What the agent pulled from the vector database for one reply: each search it chose to run,
// the query vector it embedded, and the top passages Chroma returned with their stored vectors.
export default function RetrievalTrace({ retrievals }) {
  const passages = retrievals.reduce((n, r) => n + r.passages.length, 0);
  const { embedding_model, dimensions } = retrievals[0];

  return (
    <details className="group mt-3 pt-3 border-t border-line">
      <summary className="flex flex-wrap items-baseline gap-x-2 cursor-pointer list-none select-none">
        <span className="text-[12.5px] font-semibold text-kpmg-blue group-hover:underline">
          <span aria-hidden className="inline-block w-3 transition-transform group-open:rotate-90">›</span>
          Embeddings used
        </span>
        <span className="text-[12px] text-[#8a93ab]">
          {retrievals.length === 1 ? "1 search" : `${retrievals.length} searches`} · {passages} passages ·{" "}
          {embedding_model} · {dimensions} dimensions
        </span>
      </summary>

      <div className="mt-3 flex flex-col gap-5 max-h-[520px] overflow-y-auto pr-1 [scrollbar-width:thin] [scrollbar-color:#d5dbee_transparent]">
        {retrievals.map((r, i) => (
          <section key={i} className="flex flex-col gap-2 p-3 bg-kpmg-lavender rounded-[14px]" aria-label={`Search ${i + 1}`}>
            <h4 className="text-[11px] font-bold tracking-[.12em] uppercase text-kpmg-blue">
              Search {i + 1}: top {r.passages.length} by cosine similarity
            </h4>
            <EmbeddingCard label="Query" meta="written by the agent" text={r.query} vector={r.query_embedding} />
            {r.passages.map((p) => (
              <EmbeddingCard
                key={p.chunk_id}
                label={`#${p.rank} · similarity ${p.score.toFixed(3)}`}
                meta={`${p.title} · p. ${p.page_number} · arXiv ${p.paper_id}`}
                text={p.text}
                vector={p.embedding}
              />
            ))}
          </section>
        ))}
      </div>
    </details>
  );
}
