import { useState } from "react";
import { Link, NavLink, useLocation } from "react-router";
import logo from "../assets/kpmg-logo.png";

const navLink = "text-[15px] font-semibold text-white/85 hover:text-white max-phone:hidden";
const navLinkActive = "text-white! shadow-[inset_0_-2px_0_var(--color-kpmg-cyan)] pb-1";
const headerButton =
  "inline-flex items-center justify-center h-10 px-5 text-[15px] font-semibold rounded-full cursor-pointer " +
  "text-white bg-kpmg-blue border border-kpmg-blue transition-colors duration-150 " +
  "hover:bg-white hover:text-kpmg-navy hover:border-white";

export default function Header() {
  const { pathname } = useLocation();
  const onHome = pathname === "/";

  return (
    <header className="bg-kpmg-navy">
      <div className="max-w-[1600px] mx-auto h-20 px-16 flex items-center justify-between max-tab:px-8 max-phone:h-[68px] max-phone:px-5">
        <Link to="/" className="flex items-center gap-4">
          {/* Blue-on-white logo turned white on the navy bar; the white background drops out via screen blending */}
          <img
            src={logo}
            alt="KPMG"
            className="h-10 block [filter:grayscale(1)_contrast(12)_invert(1)] mix-blend-screen"
          />
          <span className="w-px h-6 bg-white/25 max-phone:hidden" aria-hidden="true" />
          <span className="text-[15px] font-semibold text-white max-phone:hidden">AI Research Intelligence</span>
        </Link>

        <nav className="flex items-center gap-7">
          <Link to="/#how" className={navLink}>How it works</Link>
          <NavLink to="/database" className={({ isActive }) => `${navLink} ${isActive ? navLinkActive : ""}`}>
            Database Monitor
          </NavLink>
          <RetrieveButton />
          {onHome ? (
            <label htmlFor="q" className={headerButton}>Try a question</label>
          ) : (
            <Link to="/" className={headerButton}>Ask KAI</Link>
          )}
        </nav>
      </div>
    </header>
  );
}

// Number of newest arXiv papers to check on each press.
const RETRIEVE_COUNT = 10;

class BackendDown extends Error {}

async function post(url) {
  const res = await fetch(url, { method: "POST" }).catch(() => null);
  const body = res ? await res.json().catch(() => null) : null;
  // No response, or the Vite proxy answering with no JSON (502/500): FastAPI isn't running.
  if (!res || (!res.ok && body === null)) {
    throw new BackendDown("Start it with: cd backend && uvicorn main:app --reload");
  }
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}

// Downloads the newest papers from arXiv, then stores them in Chroma (papers + chunks tables).
function RetrieveButton() {
  const [status, setStatus] = useState({ step: "idle" });
  const busy = status.step === "retrieving" || status.step === "storing";

  const run = async () => {
    try {
      setStatus({ step: "retrieving" });
      const { new_papers } = await post(`/api/papers/retrieve?n=${RETRIEVE_COUNT}`);
      setStatus({ step: "storing" });
      await post("/api/papers/store");
      setStatus({ step: "done", added: new_papers.length });
      window.dispatchEvent(new Event("papers-updated")); // lets the Database Monitor refresh
    } catch (error) {
      setStatus({ step: "error", message: error.message, down: error instanceof BackendDown });
    }
    setTimeout(() => setStatus((s) => (s.step === "done" || s.step === "error" ? { step: "idle" } : s)), 6000);
  };

  const label = {
    idle: "Retrieve New Papers",
    retrieving: "Downloading from arXiv…",
    storing: "Storing in database…",
    done: status.added ? `Added ${status.added} new paper${status.added === 1 ? "" : "s"}` : "Already up to date",
    error: status.down ? "Backend not running" : "Retrieve failed",
  }[status.step];

  return (
    <button
      type="button"
      onClick={run}
      disabled={busy}
      aria-live="polite"
      title={status.step === "error" ? status.message : undefined}
      className={
        "inline-flex items-center gap-2 h-10 px-5 text-[15px] font-semibold rounded-full cursor-pointer " +
        "text-white bg-transparent border border-white/40 transition-colors duration-150 " +
        "hover:bg-white hover:text-kpmg-navy hover:border-white max-phone:hidden " +
        "disabled:cursor-wait disabled:hover:bg-transparent disabled:hover:text-white disabled:hover:border-white/40"
      }
    >
      <svg
        viewBox="0 0 20 20"
        aria-hidden="true"
        className={`w-4 h-4 fill-none stroke-current stroke-2 ${busy ? "animate-spin" : ""}`}
      >
        <path d="M16.5 10a6.5 6.5 0 1 1-1.9-4.6M16.5 3.5v3.5H13" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {label}
    </button>
  );
}
