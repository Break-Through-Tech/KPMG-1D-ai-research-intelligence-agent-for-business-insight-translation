import { useEffect, useRef } from "react";
import Composer from "./Composer.jsx";
import RetrievalTrace from "./RetrievalTrace.jsx";

// An open conversation: the messages so far, then a follow-up box pinned to the bottom.
export default function ChatView({ messages, busy, loading, error, onAsk }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  return (
    <div className="w-full max-w-[820px] mx-auto h-[calc(100vh-80px)] flex flex-col">
      <div className="flex-1 min-h-0 overflow-y-auto pt-10 pb-6 px-1 flex flex-col gap-4 [scrollbar-width:thin] [scrollbar-color:rgba(255,255,255,.25)_transparent]">
        {loading && <p className="text-center text-[14px] text-white/70">Loading conversation…</p>}

        {messages.map((m, i) =>
          m.role === "user" ? (
            <UserMessage key={i} content={m.content} />
          ) : (
            <AgentMessage key={i} content={m.content} retrievals={m.retrievals} />
          )
        )}

        {busy && <AgentMessage thinking />}

        {error && (
          <p role="alert" className="self-center px-4 py-2 text-[13.5px] text-white bg-[#b42318]/80 rounded-[10px]">
            {error}
          </p>
        )}
        <div ref={endRef} />
      </div>

      <div className="pb-6">
        <Composer onAsk={onAsk} compact busy={busy || loading} />
      </div>
    </div>
  );
}

function UserMessage({ content }) {
  return (
    <div className="self-end max-w-[80%] px-4 py-3 text-[15.5px] leading-[1.6] text-white bg-white/15 rounded-[18px] rounded-br-[6px] whitespace-pre-wrap">
      {content}
    </div>
  );
}

function AgentMessage({ content, retrievals, thinking = false }) {
  return (
    <div className="self-start max-w-[90%] px-5 py-4 bg-white rounded-[18px] rounded-bl-[6px] shadow-[0_12px_30px_-14px_rgba(12,35,60,.4)]">
      <p className="text-[11px] font-bold tracking-[.12em] uppercase text-kpmg-blue">KAI</p>
      {thinking ? (
        <p className="mt-1 text-[15px] text-[#8a93ab] animate-pulse">Thinking…</p>
      ) : (
        <p className="mt-1 text-[15.5px] leading-[1.7] text-ink whitespace-pre-wrap">{content}</p>
      )}
      {retrievals?.length > 0 && <RetrievalTrace retrievals={retrievals} />}
    </div>
  );
}
