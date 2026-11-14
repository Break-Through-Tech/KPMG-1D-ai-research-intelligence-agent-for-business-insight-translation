import { useEffect, useState } from "react";
import EmbeddingCard from "../components/EmbeddingCard.jsx";

// Read-only view of the papers currently stored in Chroma (GET /papers on the backend).
export default function DatabaseMonitor() {
  const [state, setState] = useState({ status: "loading" });
  const [openId, setOpenId] = useState(null);

  useEffect(() => {
    const load = () =>
      fetch("/api/papers?limit=500")
        .then((res) => {
          if (!res.ok) throw new Error(`Backend returned ${res.status}`);
          return res.json();
        })
        .then((data) => setState({ status: "ready", ...data }))
        .catch((error) => setState({ status: "error", message: error.message }));

    load();
    // Reload after "Retrieve New Papers" finishes (dispatched from the header button).
    window.addEventListener("papers-updated", load);
    return () => window.removeEventListener("papers-updated", load);
  }, []);

  const papers = state.items ?? [];
  const latest = papers[0]?.published;

  return (
    <main className="min-h-[calc(100vh-80px)] bg-[#f4f6fc]">
      <title>Database Monitor · KPMG AI Research Intelligence</title>

      <section className="bg-[linear-gradient(160deg,#1e49e2_0%,#1a3fc9_100%)] text-white">
        <div className="max-w-[1600px] mx-auto px-16 pt-12 pb-11 flex items-end justify-between gap-12 max-tab:flex-col max-tab:items-start max-tab:px-8 max-phone:px-5">
          <div>
            <p className="text-[13px] font-bold tracking-[.16em] uppercase text-white/80">Database Monitor</p>
            <h1 className="mt-3 font-display text-[clamp(40px,4vw,60px)] font-semibold leading-none">Papers in the database</h1>
            <p className="mt-3 text-[18px] text-white/90">Everything KAI can currently search, straight from the vector database.</p>
          </div>
          <dl className="flex gap-12 m-0">
            <Stat label="Papers" value={state.status === "ready" ? state.total : "–"} />
            <Stat label="Latest" value={latest ?? "–"} small />
          </dl>
        </div>
      </section>

      <div className="max-w-[1600px] mx-auto px-16 py-8 max-tab:px-8 max-phone:px-5">
        <div className="bg-white rounded-[18px] overflow-hidden shadow-[0_1px_2px_rgba(12,35,60,.04),0_12px_32px_-10px_rgba(12,35,60,.14)]">
          {state.status === "loading" && <Message title="Loading papers…" />}

          {state.status === "error" && (
            <Message title="Can't reach the backend">
              Start it with <code className="font-mono text-kpmg-navy">cd backend &amp;&amp; uvicorn main:app --reload</code>{" "}
              and refresh. ({state.message})
            </Message>
          )}

          {state.status === "ready" && papers.length === 0 && (
            <Message title="No papers stored yet">Retrieve and store papers to see them here.</Message>
          )}

          {state.status === "ready" && papers.length > 0 && (
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="text-[11px] font-bold tracking-[.08em] uppercase text-[#9aa2b8] border-b border-[#eef0f7]">
                  <th className="py-3.5 pl-6 pr-3 font-bold">Title</th>
                  <th className="py-3.5 px-3 font-bold w-[150px] max-phone:hidden">arXiv ID</th>
                  <th className="py-3.5 pl-3 pr-6 font-bold w-[130px] text-right">Published</th>
                </tr>
              </thead>
              <tbody>
                {papers.map((paper) => (
                  <PaperRow
                    key={paper.id}
                    paper={paper}
                    open={paper.id === openId}
                    onToggle={() => setOpenId(paper.id === openId ? null : paper.id)}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </main>
  );
}

function PaperRow({ paper, open, onToggle }) {
  // The stored document is "<title>. <abstract>"; show just the abstract.
  const abstract = paper.document.startsWith(`${paper.title}. `)
    ? paper.document.slice(paper.title.length + 2)
    : paper.document;

  return (
    <>
      <tr
        onClick={onToggle}
        aria-expanded={open}
        className={`border-b border-[#eef0f7] cursor-pointer transition-colors ${open ? "bg-[#f7f8fd]" : "hover:bg-[#fafbfe]"}`}
      >
        <td className="py-3.5 pl-6 pr-3">
          <span className="flex items-start gap-3">
            <span
              aria-hidden="true"
              className={`mt-2 shrink-0 size-2 border-r-2 border-b-2 border-[#8a93ab] transition-transform ${open ? "rotate-45" : "-rotate-45"}`}
            />
            <span className="text-[15px] font-semibold leading-[1.45] text-kpmg-navy">{paper.title}</span>
          </span>
        </td>
        <td className="py-3.5 px-3 font-mono text-[13px] text-muted max-phone:hidden">{paper.paper_id}</td>
        <td className="py-3.5 pl-3 pr-6 text-[14px] text-muted text-right tabular-nums whitespace-nowrap">{paper.published}</td>
      </tr>
      {open && (
        <tr className="bg-[#f7f8fd] border-b border-[#eef0f7]">
          <td colSpan={3} className="pt-1 pb-5 pl-11 pr-6">
            <p className="max-w-[90ch] text-[14.5px] leading-[1.7] text-[#26324a]">{abstract}</p>
            <p className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-[#8a93ab]">
              <a href={paper.url} target="_blank" rel="noreferrer" className="font-semibold text-kpmg-blue hover:underline">
                Open on arXiv ↗
              </a>
              <span>Embedding: {paper.embedding_model}</span>
              <span className="font-mono">Generation {paper.generation.slice(0, 12)}…</span>
            </p>
            <PaperEmbeddings paperId={paper.id} />
          </td>
        </tr>
      )}
    </>
  );
}

// All vectors stored for one paper (GET /papers/{id}/embeddings): the paper embedding + one per passage.
function PaperEmbeddings({ paperId }) {
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    fetch(`/api/papers/${encodeURIComponent(paperId)}/embeddings`)
      .then((res) => {
        if (!res.ok) throw new Error(`Backend returned ${res.status}`);
        return res.json();
      })
      .then((data) => setState({ status: "ready", data }))
      .catch((error) => setState({ status: "error", message: error.message }));
  }, [paperId]);

  if (state.status === "loading") return <p className="mt-5 text-[13.5px] text-[#8a93ab]">Loading embeddings…</p>;
  if (state.status === "error") {
    return <p className="mt-5 text-[13.5px] text-[#b42318]">Couldn't load embeddings ({state.message}).</p>;
  }

  const { data } = state;
  return (
    <section className="mt-6" aria-label="Embeddings">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[11px] font-bold tracking-[.12em] uppercase text-kpmg-blue">Embeddings</h3>
        <p className="text-[12.5px] text-[#8a93ab]">
          {data.passages.length + 1} vectors · {data.dimensions} dimensions · {data.embedding_model}
        </p>
      </div>

      <div className="mt-2.5 flex flex-col gap-2 max-h-[560px] overflow-y-auto pr-1 [scrollbar-width:thin] [scrollbar-color:#d5dbee_transparent]">
        <EmbeddingCard label="Paper" meta="title + abstract" text={data.paper.text} vector={data.paper.embedding} />
        {data.passages.map((p, i) => (
          <EmbeddingCard
            key={p.id}
            label={`Passage ${i + 1}`}
            meta={`page ${p.page_number} · chars ${p.start_character.toLocaleString()}–${p.end_character.toLocaleString()}`}
            text={p.text}
            vector={p.embedding}
          />
        ))}
      </div>
    </section>
  );
}

function Stat({ label, value, small = false }) {
  return (
    <div>
      <dt className="text-[12px] font-bold tracking-[.12em] uppercase text-white/70">{label}</dt>
      <dd className={`mt-1 font-display font-semibold leading-none tabular-nums ${small ? "text-[28px]" : "text-[44px]"}`}>
        {value}
      </dd>
    </div>
  );
}

function Message({ title, children }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 min-h-[280px] p-8 text-center text-[14px] text-[#6b7590]">
      <p className="text-[17px] font-semibold text-kpmg-navy">{title}</p>
      {children && <p>{children}</p>}
    </div>
  );
}
