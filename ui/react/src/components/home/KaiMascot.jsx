// KAI mascot: a geometric owl research assistant with a speech bubble.
export default function KaiMascot() {
  return (
    <section className="flex justify-center" aria-label="KAI, the research assistant">
      <div className="relative w-full max-w-[500px]">
        <KaiOwl />
        <div
          className={
            "absolute -left-[6%] top-0 max-w-[230px] py-3.5 px-[18px] text-[14px] leading-[1.5] text-muted bg-white " +
            "border border-line rounded-[16px_16px_16px_4px] shadow-[0_12px_30px_rgba(12,35,60,.1)] " +
            "max-phone:static max-phone:max-w-none max-phone:mt-3"
          }
        >
          <strong className="block text-kpmg-navy text-[15px]">Hi, I&apos;m KAI.</strong>
          Ask me about recent AI research, I&apos;m an expert!!
        </div>
      </div>
    </section>
  );
}

function KaiOwl() {
  return (
    <svg
      viewBox="0 0 480 500"
      role="img"
      aria-labelledby="kai-title"
      className="block w-full h-auto drop-shadow-[0_30px_40px_rgba(30,73,226,.2)] animate-float motion-reduce:animate-none"
    >
      <title id="kai-title">KAI, a geometric owl research assistant wearing reading glasses</title>
      <defs>
        <radialGradient id="halo" cx=".5" cy=".5" r=".5">
          <stop offset="0" stopColor="#ffffff" stopOpacity=".22" />
          <stop offset=".7" stopColor="#ffffff" stopOpacity=".06" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="owl-body" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#3a63ff" />
          <stop offset=".55" stopColor="#1e49e2" />
          <stop offset="1" stopColor="#00338d" />
        </linearGradient>
        <linearGradient id="owl-wing" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#8b3cf5" />
          <stop offset="1" stopColor="#5a12c4" />
        </linearGradient>
        <linearGradient id="owl-belly" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="1" stopColor="#dfe5ff" />
        </linearGradient>
        <linearGradient id="hl-line" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#00b8f5" />
          <stop offset="1" stopColor="#7213ea" />
        </linearGradient>
      </defs>

      {/* Soft halo */}
      <circle cx="240" cy="270" r="215" fill="url(#halo)" />
      <circle
        cx="240" cy="270" r="190" fill="none" stroke="#ffffff" strokeOpacity=".18"
        strokeWidth="1.5" strokeDasharray="2 10" strokeLinecap="round"
      />

      {/* Sparkles */}
      <g fill="#ffffff">
        <path d="M92 150 l5 13 13 5 -13 5 -5 13 -5 -13 -13 -5 13 -5z" opacity=".9" />
        <path d="M392 118 l3.5 9 9 3.5 -9 3.5 -3.5 9 -3.5 -9 -9 -3.5 9 -3.5z" fill="#00b8f5" />
        <path d="M410 300 l3 7 7 3 -7 3 -3 7 -3 -7 -7 -3 7 -3z" opacity=".7" />
        <circle cx="120" cy="330" r="3" opacity=".6" />
        <circle cx="360" cy="190" r="2.5" opacity=".7" />
      </g>

      {/* Stack of research pages */}
      <g strokeLinejoin="round">
        <path d="M240 415 L370 460 L240 505 L110 460 Z" fill="#b7c1f4" />
        <path d="M240 405 L370 450 L240 495 L110 450 Z" fill="#d3d9fa" stroke="#b7c1f4" />
        <path d="M240 395 L370 440 L240 485 L110 440 Z" fill="#ffffff" stroke="#c9d0f3" />
        <g strokeWidth="4" strokeLinecap="round">
          <line x1="292" y1="425" x2="330" y2="438" stroke="#d2d7ea" />
          <line x1="300" y1="437" x2="336" y2="449" stroke="url(#hl-line)" />
          <line x1="150" y1="440" x2="178" y2="430" stroke="#d2d7ea" />
          <line x1="158" y1="452" x2="196" y2="439" stroke="#d2d7ea" />
        </g>
      </g>
      <ellipse cx="240" cy="440" rx="74" ry="13" fill="#0c233c" opacity=".16" />

      <g transform="translate(0 12)">
        {/* Ear tufts */}
        <path d="M172 190 L150 118 L218 166 Z" fill="#1e49e2" />
        <path d="M308 190 L330 118 L262 166 Z" fill="#1e49e2" />

        {/* Body */}
        <path
          d="M240 150 C 322 150, 348 232, 348 302 C 348 372, 302 422, 240 422 C 178 422, 132 372, 132 302 C 132 232, 158 150, 240 150 Z"
          fill="url(#owl-body)"
        />

        {/* Belly with feather chevrons */}
        <ellipse cx="240" cy="352" rx="74" ry="66" fill="url(#owl-belly)" />
        <g fill="none" stroke="#b9c4f6" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <path d="M212 372 l10 8 10 -8" />
          <path d="M248 372 l10 8 10 -8" />
          <path d="M230 392 l10 8 10 -8" />
        </g>

        {/* Left wing (resting) */}
        <path d="M136 268 C 104 300, 108 362, 152 398 C 160 352, 166 312, 162 280 Z" fill="url(#owl-wing)" />

        {/* Right wing (raised, holding a page) */}
        <path d="M342 266 C 384 272, 410 312, 404 346 C 380 338, 356 318, 338 296 Z" fill="url(#owl-wing)" />
        <g transform="translate(-14 4) rotate(14 412 330)">
          <rect x="386" y="290" width="54" height="68" rx="6" fill="#ffffff" stroke="#c9d0f3" strokeWidth="2" />
          <rect x="395" y="303" width="36" height="5" rx="2.5" fill="#d2d7ea" />
          <rect x="395" y="315" width="28" height="5" rx="2.5" fill="#d2d7ea" />
          <rect x="395" y="327" width="36" height="5" rx="2.5" fill="url(#hl-line)" />
          <rect x="395" y="339" width="22" height="5" rx="2.5" fill="#d2d7ea" />
        </g>

        {/* Face discs */}
        <circle cx="194" cy="236" r="44" fill="#ffffff" />
        <circle cx="286" cy="236" r="44" fill="#ffffff" />

        {/* Eyes */}
        <circle cx="198" cy="238" r="24" fill="#00b8f5" />
        <circle cx="282" cy="238" r="24" fill="#00b8f5" />
        <circle cx="200" cy="240" r="15" fill="#0c233c" />
        <circle cx="280" cy="240" r="15" fill="#0c233c" />
        <circle cx="206" cy="232" r="5.5" fill="#ffffff" />
        <circle cx="286" cy="232" r="5.5" fill="#ffffff" />

        {/* Reading glasses */}
        <g fill="none" stroke="#0c233c" strokeWidth="5">
          <circle cx="194" cy="236" r="44" />
          <circle cx="286" cy="236" r="44" />
          <path d="M150 226 L134 216" strokeLinecap="round" />
          <path d="M330 226 L346 216" strokeLinecap="round" />
        </g>

        {/* Beak */}
        <path
          d="M240 266 L252 280 L240 298 L228 280 Z" fill="#00b8f5" stroke="#0c233c"
          strokeWidth="2" strokeLinejoin="round"
        />

        {/* Feet */}
        <ellipse cx="216" cy="424" rx="14" ry="7" fill="#00b8f5" />
        <ellipse cx="264" cy="424" rx="14" ry="7" fill="#00b8f5" />
      </g>
    </svg>
  );
}
