import { Link } from "react-router";

// "How it works" flow diagram. Replaces the mascot while open.
export default function HowItWorks() {
  return (
    <section className="animate-fade-in motion-reduce:animate-none" aria-label="How it works">
      <div className="relative mb-8">
        <p className="text-center text-[15px] text-white/85 max-phone:text-left">How KAI answers your question</p>
        <Link
          to="/"
          className="absolute right-0 top-1/2 -translate-y-1/2 text-[14px] font-semibold text-white border-b-2 border-kpmg-cyan hover:text-kpmg-cyan"
        >
          Close
        </Link>
      </div>

      <FlowDiagram />
    </section>
  );
}

const laneText = "text-[13px] font-bold tracking-[.16em] fill-white/75";
const arrowLine = "stroke-white/85";
const arrowLabel = "text-[14px] font-semibold fill-white";
const pillText = "text-[14px] font-semibold fill-kpmg-navy";

// White card with an icon disc, a title and two lines of description.
function FlowCard({ x, y, title, lines, children }) {
  const cx = x + 95;
  // [&_rect]:fill-white also whitens the icon rects (matching the original static design).
  // Remove it to show the icons' own fill colours.
  return (
    <g className="[&_rect]:fill-white">
      <rect x={x} y={y} width="190" height="150" rx="14" className="fill-white" />
      <circle cx={cx} cy={y + 48} r="30" className="fill-[#eef1ff]" />
      {children}
      <text x={cx} y={y + 102} textAnchor="middle" className="text-[18px] font-bold fill-kpmg-navy">
        {title}
      </text>
      {lines.map((line, i) => (
        <text key={line} x={cx} y={y + 122 + i * 16} textAnchor="middle" className="text-[13px] fill-[#5b6580]">
          {line}
        </text>
      ))}
    </g>
  );
}

function FlowDiagram() {
  return (
    <svg
      viewBox="0 0 760 540"
      role="img"
      aria-labelledby="flow-title"
      className="block w-full h-auto overflow-visible font-sans"
    >
      <title id="flow-title">
        KAI collects AI papers from arXiv, processes them into a database, and answers a KPMG employee&apos;s question
        with cited passages from that database.
      </title>
      <defs>
        <marker id="arw" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" fill="#ffffff" />
        </marker>
        <marker id="arw-c" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" fill="#00b8f5" />
        </marker>
      </defs>

      <text className={laneText} x="10" y="36">BEHIND THE SCENES</text>
      <text className={laneText} x="10" y="356">WHEN YOU ASK</text>

      {/* Top row: arXiv -> Processing -> Database */}
      <g className={arrowLine} strokeWidth="2">
        <line x1="202" y1="131" x2="281" y2="131" markerEnd="url(#arw)" />
        <line x1="477" y1="131" x2="556" y2="131" markerEnd="url(#arw)" />
      </g>
      <text className={arrowLabel} textAnchor="middle" x="242" y="121">collect</text>
      <text className={arrowLabel} textAnchor="middle" x="517" y="121">store</text>

      <FlowCard x={10} y={56} title="arXiv AI papers" lines={["Newest research from", "the AI section (cs.AI)"]}>
        <rect x="87" y="84" width="26" height="34" rx="3" fill="#c9d0f3" />
        <rect x="97" y="90" width="26" height="34" rx="3" fill="#fff" stroke="#1e49e2" strokeWidth="1.5" />
        <rect x="102" y="98" width="16" height="3" rx="1.5" fill="#c9d0f3" />
        <rect x="102" y="105" width="12" height="3" rx="1.5" fill="#c9d0f3" />
        <rect x="102" y="112" width="16" height="3" rx="1.5" fill="#1e49e2" />
      </FlowCard>

      <FlowCard x={285} y={56} title="Processing" lines={["Papers are read and", "split into short passages"]}>
        <rect x="356" y="88" width="20" height="30" rx="3" fill="#fff" stroke="#1e49e2" strokeWidth="1.5" />
        <path
          d="M380 103 h8 m-3 -3 l3 3 -3 3" fill="none" stroke="#1e49e2" strokeWidth="1.5"
          strokeLinecap="round" strokeLinejoin="round"
        />
        <rect x="392" y="90" width="18" height="6" rx="3" fill="#c9d0f3" />
        <rect x="392" y="100" width="18" height="6" rx="3" fill="#00b8f5" />
        <rect x="392" y="110" width="18" height="6" rx="3" fill="#c9d0f3" />
      </FlowCard>

      <FlowCard x={560} y={56} title="Database" lines={["Passages saved with", "their paper and page"]}>
        <path d="M635 92 v24 a20 7 0 0 0 40 0 v-24" fill="#1e49e2" />
        <path d="M635 104 a20 7 0 0 0 40 0" fill="none" stroke="#7d9bff" strokeWidth="1.5" />
        <ellipse cx="655" cy="92" rx="20" ry="7" fill="#5b7fff" />
      </FlowCard>

      {/* KAI searches the database */}
      <g className={arrowLine} strokeWidth="2">
        <line x1="655" y1="210" x2="655" y2="372" markerStart="url(#arw)" markerEnd="url(#arw)" />
      </g>
      <text className={arrowLabel} textAnchor="end" x="643" y="286">KAI searches</text>
      <text className={arrowLabel} textAnchor="end" x="643" y="302">the database</text>

      {/* Bottom row: employee asks, KAI answers */}
      <g className={arrowLine} strokeWidth="2">
        <line x1="202" y1="426" x2="556" y2="426" markerEnd="url(#arw)" />
      </g>
      <g className="stroke-kpmg-cyan" strokeWidth="2">
        <line x1="558" y1="478" x2="204" y2="478" markerEnd="url(#arw-c)" />
      </g>

      <rect className="fill-white" x="210" y="390" width="340" height="28" rx="14" />
      <text className={pillText} textAnchor="middle" x="380" y="408">
        &#8220;What are the risks of deploying AI agents?&#8221;
      </text>

      <rect className="fill-kpmg-cyan" x="262" y="486" width="236" height="28" rx="14" />
      <text className={pillText} textAnchor="middle" x="380" y="504">Cited answer &#183; sources [1] [2]</text>

      <FlowCard x={10} y={376} title="KPMG employee" lines={["Asks a question in", "plain language"]}>
        <circle cx="105" cy="414" r="10" fill="#1e49e2" />
        <path d="M84 446 c0 -18 42 -18 42 0 z" fill="#1e49e2" />
        <rect x="109" y="433" width="10" height="7" rx="1.5" fill="#00b8f5" />
      </FlowCard>

      <FlowCard x={560} y={376} title="KAI agent" lines={["Reads the best passages", "and writes the answer"]}>
        <path d="M639 412 l-4 -16 13 9 z M671 412 l4 -16 -13 9 z" fill="#1e49e2" />
        <circle cx="655" cy="424" r="20" fill="#1e49e2" />
        <circle cx="647" cy="420" r="7.5" fill="#fff" stroke="#0c233c" strokeWidth="2" />
        <circle cx="663" cy="420" r="7.5" fill="#fff" stroke="#0c233c" strokeWidth="2" />
        <circle cx="648" cy="421" r="3.5" fill="#0c233c" />
        <circle cx="662" cy="421" r="3.5" fill="#0c233c" />
        <path d="M655 428 l3 4 -3 4 -3 -4 z" fill="#00b8f5" />
      </FlowCard>
    </svg>
  );
}
