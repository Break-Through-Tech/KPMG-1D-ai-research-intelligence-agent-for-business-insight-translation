import { useState } from "react";

const iconButton =
  "grid place-items-center w-9 h-9 shrink-0 text-white/75 rounded-[10px] cursor-pointer " +
  "transition-colors duration-150 hover:text-white hover:bg-white/10";

// ChatGPT-style history sidebar. Conversations come from Home; a title of null means the agent is still naming it.
// `locked` disables switching while the agent is replying or a conversation is loading.
export default function ConversationSidebar({ conversations, activeId, locked = false, onSelect, onNewChat }) {
  const [open, setOpen] = useState(true);

  // Collapsed: a slim rail with expand + new chat.
  if (!open) {
    return (
      <SidebarColumn>
        <aside
          aria-label="Conversations"
          className="sticky top-0 h-[calc(100vh-80px)] w-16 flex flex-col items-center gap-2 pt-4"
        >
          <button type="button" aria-label="Open sidebar" onClick={() => setOpen(true)} className={iconButton}>
            <SidebarIcon />
          </button>
          <button type="button" aria-label="New chat" onClick={onNewChat} disabled={locked} className={`${iconButton} disabled:opacity-40 disabled:cursor-not-allowed`}>
            <PencilIcon />
          </button>
        </aside>
      </SidebarColumn>
    );
  }

  return (
    <SidebarColumn>
      <aside aria-label="Conversations" className="sticky top-0 h-[calc(100vh-80px)] w-[280px] flex flex-col text-white">
        <div className="flex items-center justify-between gap-2 px-3 pt-4">
          <button type="button" aria-label="Close sidebar" onClick={() => setOpen(false)} className={iconButton}>
            <SidebarIcon />
          </button>
          <button
            type="button"
            onClick={onNewChat}
            disabled={locked}
            className={
              "flex-1 inline-flex items-center justify-center gap-2 h-9 px-4 text-[14px] font-semibold rounded-full cursor-pointer " +
              "text-white bg-transparent border border-white/25 transition-colors duration-150 hover:bg-white/10 " +
              "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
            }
          >
            <PencilIcon />
            New chat
          </button>
        </div>

        <nav
          className="flex-1 min-h-0 overflow-y-auto mt-4 px-2 pb-4 [scrollbar-width:thin] [scrollbar-color:rgba(255,255,255,.18)_transparent]"
        >
          {conversations.length > 0 && (
            <section className="mt-1">
              <h2 className="px-3 pb-1.5 text-[11px] font-bold tracking-[.12em] uppercase text-white/45">Today</h2>
              <ul className="m-0 p-0 flex flex-col gap-0.5">
                {conversations.map((c) => (
                  <li key={c.id}>
                    <ConversationItem
                      conversation={c}
                      active={c.id === activeId}
                      disabled={locked}
                      onSelect={() => onSelect(c.id)}
                    />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </nav>
      </aside>
    </SidebarColumn>
  );
}

function ConversationItem({ conversation, active, disabled, onSelect }) {
  const naming = conversation.title === null;

  return (
    <button
      type="button"
      onClick={onSelect}
      disabled={disabled && !active}
      aria-current={active ? "true" : undefined}
      aria-busy={naming || undefined}
      title={naming ? undefined : conversation.title}
      className={
        "w-full px-3 py-2 text-left text-[14px] truncate rounded-[10px] cursor-pointer transition-colors duration-150 " +
        (active ? "text-white bg-white/[.14]" : "text-white/80 hover:text-white hover:bg-white/[.07]") +
        " disabled:opacity-50 disabled:cursor-not-allowed"
      }
    >
      {naming ? <span className="text-white/50 italic animate-pulse">Naming…</span> : conversation.title}
    </button>
  );
}

// Navy column that always runs the full height of the page; the sidebar inside it stays pinned while scrolling.
function SidebarColumn({ children }) {
  return <div className="shrink-0 self-stretch bg-kpmg-navy border-r border-white/10 max-tab:hidden">{children}</div>;
}

function SidebarIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="w-[18px] h-[18px] fill-none stroke-current stroke-[1.8]">
      <rect x="2.5" y="3.5" width="15" height="13" rx="2.5" />
      <path d="M7.5 3.5v13" />
    </svg>
  );
}

function PencilIcon() {
  return (
    <svg viewBox="0 0 20 20" aria-hidden="true" className="w-4 h-4 fill-none stroke-current stroke-[1.8]">
      <path d="M13.5 3.5l3 3L8 15H5v-3z" strokeLinejoin="round" />
    </svg>
  );
}
