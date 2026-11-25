import { useEffect, useState } from "react";
import { useLocation } from "react-router";
import Composer from "../components/home/Composer.jsx";
import ChatView from "../components/home/ChatView.jsx";
import KaiMascot from "../components/home/KaiMascot.jsx";
import HowItWorks from "../components/home/HowItWorks.jsx";
import ConversationSidebar from "../components/home/ConversationSidebar.jsx";

// Horizontal page gutter: 64px, growing so content stays centred within 1600px.
const PAGE_PAD_X = "px-[max(64px,calc((100%_-_1600px)/2_+_64px))]";
const BANNER_GRADIENT = "bg-[linear-gradient(160deg,#1e49e2_0%,#1a3fc9_100%)]";

// Small fetch helpers: JSON in/out, backend error message ("detail") surfaced as the Error text.
async function api(url, options) {
  const res = await fetch(url, options);
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(body?.detail || "Can't reach the backend. Is it running?");
  return body;
}
const send = (method, url, data) =>
  api(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data ?? {}) });

export default function Home() {
  // "How it works" opens via the #how link in the header and swaps out the mascot.
  const { hash } = useLocation();
  const showDiagram = hash === "#how";

  const [conversations, setConversations] = useState([]); // [{ id, title }]; title null = agent is naming it
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]); // messages of the open conversation
  const [busy, setBusy] = useState(false); // waiting for the agent's reply
  const [loading, setLoading] = useState(false); // loading a conversation's history
  const [error, setError] = useState(null);

  // Saved conversations (SQLite) for the sidebar.
  useEffect(() => {
    api("/api/conversations")
      .then((list) => setConversations(list.map((c) => ({ id: c.id, title: c.title ?? "Untitled chat" }))))
      .catch(() => {});
  }, []);

  const setTitle = (id, title) => setConversations((list) => list.map((c) => (c.id === id ? { ...c, title } : c)));

  // Start a brand-new conversation: save it, then let the agent name it from the first question.
  const createConversation = async (question, context) => {
    const id = crypto.randomUUID();
    setConversations((list) => [{ id, title: null }, ...list]);
    setActiveId(id);
    setMessages([]);
    await send("POST", "/api/conversations", { id }).catch((e) => setError(e.message));

    send("POST", "/api/conversations/title", { question, context })
      .then(({ title }) => {
        setTitle(id, title);
        return send("PATCH", `/api/conversations/${id}`, { title });
      })
      .catch(() =>
        setConversations((list) =>
          list.map((c) => (c.id === id && c.title === null ? { ...c, title: "Untitled chat" } : c))
        )
      );
    return id;
  };

  // Send a message to the agent; it reads the conversation so far from Redis.
  const ask = async (question, context) => {
    setError(null);
    const content = context ? `${question}\n\nContext: ${context}` : question;
    const id = activeId ?? (await createConversation(question, context));

    setMessages((list) => [...list, { role: "user", content }]);
    setBusy(true);
    try {
      const reply = await send("POST", `/api/conversations/${id}/chat`, { content });
      setMessages((list) => [...list, reply]);
    } catch (e) {
      setMessages((list) => list.slice(0, -1)); // the backend dropped the unanswered question too
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  // Switch conversation: the backend dumps the current one to SQLite and loads this one into Redis.
  const openConversation = (id) => {
    if (id === activeId) return;
    const previousId = activeId;
    setActiveId(id);
    setMessages([]);
    setError(null);
    setLoading(true);
    send("POST", `/api/conversations/${id}/open`, { previous_id: previousId })
      .then((data) => setMessages(data.messages))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  // New chat: dump the current conversation and go back to the start screen.
  const newChat = () => {
    if (activeId) send("POST", `/api/conversations/${activeId}/dump`).catch(() => {});
    setActiveId(null);
    setMessages([]);
    setError(null);
  };

  return (
    <div className="flex items-start">
      <ConversationSidebar
        conversations={conversations}
        activeId={activeId}
        locked={busy || loading}
        onSelect={openConversation}
        onNewChat={newChat}
      />

      {activeId ? (
        <main className={`flex-1 min-w-0 ${BANNER_GRADIENT} px-8 max-phone:px-5`}>
          <title>KPMG · AI Research Intelligence</title>
          <ChatView messages={messages} busy={busy} loading={loading} error={error} onAsk={ask} />
        </main>
      ) : (
        <main
          className={
            `relative isolate overflow-clip flex-1 min-w-0 min-h-[calc(100vh-80px)] grid grid-cols-[minmax(0,6fr)_minmax(0,5fr)] gap-12 items-center ` +
            `${PAGE_PAD_X} ${BANNER_GRADIENT} max-tab:grid-cols-1 max-tab:gap-0 max-tab:px-0`
          }
        >
          <title>KPMG · AI Research Intelligence</title>

          <section className="self-center max-w-[680px] pt-16 pb-16 text-white max-tab:px-8 max-tab:pb-12 max-phone:px-5 max-phone:py-10">
            <p className="text-[12.5px] font-semibold tracking-[.12em] uppercase text-white/75">
              AI research for business teams
            </p>
            <h1 className="mt-3 text-[clamp(30px,2.6vw,40px)] font-semibold leading-[1.2] tracking-[-0.01em] text-white">
              What would you like to know about AI research?
            </h1>
            <p className="mt-3 text-[16.5px] leading-[1.6] text-white/85">
              Answers are drawn from recent arXiv papers in the database, with a citation for every claim.
            </p>

            <Composer onAsk={ask} busy={busy} />
            {error && <p role="alert" className="mt-3 text-[13.5px] text-white">{error}</p>}
          </section>

          <div className="py-10 max-tab:px-8 max-tab:pt-0 max-tab:pb-12 max-phone:px-5 max-phone:pb-10">
            {showDiagram ? <HowItWorks /> : <KaiMascot />}
          </div>
        </main>
      )}
    </div>
  );
}
