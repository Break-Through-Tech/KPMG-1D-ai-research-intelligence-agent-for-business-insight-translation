import { useState } from "react";

// Question box. Submitting hands the text to Home (`onAsk`).
// `compact` is the in-conversation version (no Context field); `busy` blocks sending while the agent replies.
export default function Composer({ onAsk, compact = false, busy = false }) {
  const [question, setQuestion] = useState("");
  const [context, setContext] = useState("");
  const canSend = question.trim() && !busy;

  const submit = (e) => {
    e.preventDefault();
    if (!canSend) return;
    onAsk(question.trim(), compact ? null : context.trim() || null);
    setQuestion("");
    setContext("");
  };

  return (
    <form
      id="ask"
      onSubmit={submit}
      className={
        `${compact ? "" : "mt-8 "}bg-white border-2 border-transparent rounded-[20px] shadow-[0_16px_40px_-12px_rgba(12,35,60,.35)] ` +
        "transition-[border-color,box-shadow] duration-150 " +
        "focus-within:border-white focus-within:shadow-[0_16px_40px_-12px_rgba(12,35,60,.35),0_0_0_4px_rgba(255,255,255,.25)]"
      }
    >
      <label htmlFor="q" className="sr-only">Your question</label>
      <textarea
        id="q"
        rows={compact ? 2 : 3}
        autoFocus
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => {
          // Enter sends, Shift+Enter adds a new line.
          if (e.key === "Enter" && !e.shiftKey) submit(e);
        }}
        placeholder={compact ? "Ask a follow-up…" : "Ask about recent AI research…"}
        className={
          "block w-full pt-5 px-6 pb-2 text-[17px] leading-[1.55] text-ink bg-transparent border-0 outline-0 resize-none " +
          "placeholder:text-[#8a93ab] max-phone:text-[16px] max-phone:px-5"
        }
      />

      <div className="flex items-end gap-3 pt-1 px-3 pb-3 max-phone:px-2.5 max-phone:pb-2.5">
        {compact ? (
          <span className="flex-1" />
        ) : (
          // Optional business context, inside the composer (first message only)
          <div
            className={
              "flex-1 min-w-0 flex flex-col gap-0.5 py-2 px-3.5 bg-[#f6f7fb] rounded-[12px] transition-[background-color,box-shadow] duration-150 " +
              "focus-within:bg-white focus-within:shadow-[inset_0_0_0_1px_#c9d3fb]"
            }
          >
            <label htmlFor="ctx" className="flex items-center gap-2 text-[12px] font-semibold text-kpmg-navy">
              Context
              <span className="text-[11px] font-normal text-[#8a93ab]">Optional</span>
            </label>
            <input
              id="ctx"
              type="text"
              value={context}
              onChange={(e) => setContext(e.target.value)}
              placeholder="e.g. Preparing a client briefing for a regional bank"
              className="w-full text-[14.5px] text-ink bg-transparent border-0 outline-0 placeholder:text-[#8a93ab]"
            />
          </div>
        )}

        <button
          type="submit"
          aria-label="Ask KAI"
          disabled={!canSend}
          className={
            "shrink-0 grid place-items-center w-10 h-10 text-white bg-kpmg-blue border-0 rounded-[12px] cursor-pointer " +
            "transition-colors duration-150 hover:bg-kpmg-cobalt disabled:bg-[#c9cfe0] disabled:cursor-not-allowed"
          }
        >
          <svg viewBox="0 0 24 24" aria-hidden="true" className="w-5 h-5">
            <path
              d="M12 19V5M5 12l7-7 7 7"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>
    </form>
  );
}
