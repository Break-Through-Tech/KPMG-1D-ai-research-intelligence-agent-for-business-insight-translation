import { useState } from "react";

// One stored vector and the text it embeds; shows the first values, expandable to the full vector.
export default function EmbeddingCard({ label, meta, text, vector }) {
  const [showText, setShowText] = useState(false);
  const [showVector, setShowVector] = useState(false);
  const toggle = "text-[12.5px] font-semibold text-kpmg-blue hover:underline cursor-pointer";

  return (
    <article className="p-3.5 bg-white rounded-xl shadow-[inset_0_0_0_1px_#e6e9f5]">
      <p className="flex flex-wrap items-baseline gap-x-2.5 text-[12.5px]">
        <span className="font-bold text-kpmg-navy">{label}</span>
        <span className="text-[#8a93ab]">{meta}</span>
      </p>
      <p className={`mt-1.5 text-[13.5px] leading-[1.6] text-muted ${showText ? "" : "line-clamp-2"}`}>{text}</p>

      <p className="mt-2 font-mono text-[11.5px] text-[#6b7590] break-all">
        [{(showVector ? vector : vector.slice(0, 8)).map((v) => v.toFixed(4)).join(", ")}
        {showVector ? "" : ", …"}]
      </p>

      <p className="mt-1.5 flex gap-4">
        <button type="button" className={toggle} onClick={() => setShowText((s) => !s)}>
          {showText ? "Hide full text" : "Show full text"}
        </button>
        <button type="button" className={toggle} onClick={() => setShowVector((s) => !s)}>
          {showVector ? "Collapse vector" : `Show all ${vector.length} values`}
        </button>
      </p>
    </article>
  );
}
