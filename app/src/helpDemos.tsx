import type { ReactNode } from "react";

export function DemoFrame({ children, caption }: { children: ReactNode; caption: string }) {
  return <figure className="hd-frame"><span className="hd-badge">ANIMATED GUIDE</span><div className="hd-stage">{children}</div><figcaption>{caption}</figcaption></figure>;
}

function WorkspaceTourDemo() {
  return (
    <svg className="hd" viewBox="0 0 320 180" role="img" aria-label="Workspace tour: import, terminals, mesh, solve, report">
      <rect x="1" y="1" width="318" height="178" rx="6" fill="#101c23" stroke="#344b55" />
      <rect x="8" y="8" width="304" height="14" rx="3" fill="#182a34" />
      <text x="16" y="18" fontSize="7" fill="#8ba1aa">SPIKE</text>
      <circle cx="298" cy="15" r="4" fill="#20333c" stroke="#e0a443" className="hd-win hd-win-solve" />
      <path d="M296 13l2 2 3 -3" stroke="#e0a443" strokeWidth="1.2" fill="none" className="hd-win hd-win-solve" />
      <g>
        <rect x="8" y="26" width="52" height="104" rx="3" fill="#0c171d" stroke="#263b44" />
        {[38, 56, 74, 92].map(y => <rect key={y} x="14" y={y} width="40" height="10" rx="2" fill="#14232b" />)}
        <g className="hd-win hd-win-import">
          <rect x="14" y="38" width="40" height="10" rx="2" fill="#24343b" stroke="#dfa344" strokeWidth="1" />
          <text x="19" y="45" fontSize="5.5" fill="#f0bf64">Import</text>
        </g>
        <rect x="17" y="41" width="4" height="4" rx="1" fill="#8ed1d1" className="hd-static" opacity="0.35" />
      </g>
      <g>
        <rect x="260" y="26" width="52" height="104" rx="3" fill="#0c171d" stroke="#263b44" />
        {[38, 56, 74].map(y => <rect key={y} x="266" y={y} width="40" height="12" rx="2" fill="#14232b" />)}
        <text x="272" y="46" fontSize="5" fill="#718a94">Setup</text>
      </g>
      <g>
        <rect x="64" y="26" width="192" height="104" rx="3" fill="#0b1419" stroke="#263b44" />
        <g transform="translate(78 36)">
          <rect x="30" y="14" width="134" height="72" rx="5" fill="#14453a" stroke="#1d5a4a" />
          <path d="M42 66 L84 66 L84 40 L128 40" stroke="#d98d47" strokeWidth="3" fill="none" strokeLinecap="round" />
          <path d="M52 74 L110 74" stroke="#d98d47" strokeWidth="2" fill="none" strokeLinecap="round" opacity=".7" />
          <g className="hd-win hd-win-terminals">
            <circle cx="42" cy="66" r="4" fill="#62c88f" />
            <text x="34" y="60" fontSize="6" fill="#62c88f">SRC</text>
            <circle cx="128" cy="40" r="4" fill="#eb746a" />
            <text x="132" y="36" fontSize="6" fill="#eb746a">LOAD</text>
            <line x1="42" y1="70" x2="42" y2="80" stroke="#62c88f" strokeWidth="1" strokeDasharray="2 2" />
            <line x1="128" y1="44" x2="128" y2="54" stroke="#eb746a" strokeWidth="1" strokeDasharray="2 2" />
          </g>
          <g className="hd-win hd-win-mesh" stroke="#58cbbb" strokeWidth=".4" opacity=".9">
            {[0, 1, 2, 3, 4, 5, 6, 7, 8].map(i => <line key={`v${i}`} x1={30 + i * 16.75} y1="14" x2={30 + i * 16.75} y2="86" />)}
            {[0, 1, 2, 3, 4, 5].map(i => <line key={`h${i}`} x1="30" y1={14 + i * 14.4} x2="164" y2={14 + i * 14.4} />)}
          </g>
          <g className="hd-win hd-win-report">
            <rect x="96" y="30" width="52" height="60" rx="3" fill="#122029" stroke="#e0a443" />
            <text x="103" y="42" fontSize="6" fill="#f0bf64">Report</text>
            {[50, 57, 64, 71, 78].map(y => <line key={y} x1="103" y1={y} x2="140" y2={y} stroke="#718a94" strokeWidth="1" />)}
          </g>
        </g>
      </g>
      <g>
        <rect x="8" y="134" width="304" height="38" rx="3" fill="#0c171d" stroke="#263b44" />
        {["worker: design imported · 46 nets", "preflight: terminals mapped", "mesh preview ready"].map((t, i) => (
          <text key={i} x="16" y={147 + i * 9} fontSize="6" fill="#718993" fontFamily="ui-monospace, monospace">{t}</text>
        ))}
      </g>
      <g className="hd-captions" fontFamily="inherit">
        {[
          ["Import", "hd-cap-import"], ["Terminals", "hd-cap-terminals"], ["Mesh", "hd-cap-mesh"], ["Solve", "hd-cap-solve"], ["Report", "hd-cap-report"],
        ].map(([label, cls], i) => (
          <g key={cls} className={`hd-chip ${cls}`} transform={`translate(${86 + i * 36} 116)`}>
            <rect x="-14" y="-8" width="28" height="12" rx="6" fill="#20333c" stroke="#dfa344" strokeWidth=".8" />
            <text textAnchor="middle" y="0.5" fontSize="5.5" fill="#f0bf64">{label}</text>
          </g>
        ))}
      </g>
    </svg>
  );
}

function OrbitPivotDemo() {
  return (
    <svg className="hd" viewBox="0 0 320 180" role="img" aria-label="Middle-click sets the orbit center, then drag orbits around it">
      <rect x="1" y="1" width="318" height="178" rx="6" fill="#0b1419" stroke="#344b55" />
      <g fill="#1a2c35">
        {Array.from({ length: 11 }, (_, r) => Array.from({ length: 19 }, (_, c) => <circle key={`${r}-${c}`} cx={22 + c * 15} cy={20 + r * 13} r=".8" />))}
      </g>
      <g className="hd-orbit-board" transform="translate(160 92)">
        <g transform="skewY(-6)">
          <rect x="-70" y="-34" width="140" height="68" rx="6" fill="#14453a" stroke="#1d5a4a" strokeWidth="1.4" />
          <path d="M-52 16 L-6 16 L-6 -10 L54 -10" stroke="#d98d47" strokeWidth="3.4" fill="none" strokeLinecap="round" />
          <rect x="-64" y="-26" width="16" height="12" rx="1.5" fill="#16262f" stroke="#3a515b" />
          <rect x="34" y="-2" width="22" height="16" rx="2" fill="#16262f" stroke="#3a515b" />
        </g>
      </g>
      <g className="hd-pivot">
        <circle cx="160" cy="92" r="7" fill="none" stroke="#58cbbb" strokeWidth="1" />
        <circle cx="160" cy="92" r="2" fill="#58cbbb" />
      </g>
      <g className="hd-orbit-cursor">
        <circle cx="0" cy="0" r="5" fill="none" stroke="#f0bf64" strokeWidth="1.4" />
        <circle cx="0" cy="0" r="1.2" fill="#f0bf64" />
        <text x="9" y="-7" fontSize="6.5" fill="#f0bf64">middle-click</text>
      </g>
      <g className="hd-orbit-hint">
        <rect x="98" y="150" width="124" height="14" rx="7" fill="#20333c" stroke="#4f8791" strokeWidth=".8" />
        <text x="160" y="159.5" textAnchor="middle" fontSize="6.5" fill="#8ed1d1">orbit now pivots here</text>
      </g>
    </svg>
  );
}

function WireConnectDemo() {
  return (
    <svg className="hd" viewBox="0 0 320 180" role="img" aria-label="Click OUT, then IN to connect a directed wire between blocks">
      <rect x="1" y="1" width="318" height="178" rx="6" fill="#0b1419" stroke="#344b55" />
      <text x="14" y="20" fontSize="7" fill="#718993">POWER TREE</text>
      <g>
        <rect x="48" y="48" width="88" height="48" rx="5" fill="#16262f" stroke="#3a515b" />
        <text x="58" y="68" fontSize="8" fill="#dbe6e9">VRM 12 V</text>
        <text x="58" y="80" fontSize="6" fill="#718993">source</text>
        <circle className="hd-port hd-port-out" cx="136" cy="72" r="4.5" fill="#0b1419" stroke="#e0a443" strokeWidth="1.6" />
        <text x="120" y="64" fontSize="6" fill="#f0bf64">OUT</text>
      </g>
      <g>
        <rect x="188" y="96" width="88" height="48" rx="5" fill="#16262f" stroke="#3a515b" />
        <text x="198" y="116" fontSize="8" fill="#dbe6e9">MCU 1.2 V</text>
        <text x="198" y="128" fontSize="6" fill="#718993">load</text>
        <circle className="hd-port hd-port-in" cx="188" cy="108" r="4.5" fill="#0b1419" stroke="#58cbbb" strokeWidth="1.6" />
        <text x="196" y="100" fontSize="6" fill="#8ed1d1">IN</text>
      </g>
      <path className="hd-wire-path" d="M136 72 C166 72 158 108 184 108" pathLength="100" fill="none" stroke="#e0a443" strokeWidth="2" strokeLinecap="round" />
      <path className="hd-wire-arrow" d="M180 104 L186 108 L180 112" fill="none" stroke="#e0a443" strokeWidth="2" strokeLinecap="round" />
      <circle className="hd-wire-dot" cx="136" cy="72" r="3" fill="#f0bf64" />
      <g className="hd-orbit-cursor hd-wire-cursor">
        <circle cx="0" cy="0" r="5" fill="none" stroke="#f0bf64" strokeWidth="1.4" />
        <circle cx="0" cy="0" r="1.2" fill="#f0bf64" />
      </g>
      <g className="hd-connected-chip">
        <rect x="216" y="52" width="76" height="16" rx="8" fill="#142922" stroke="#5fc58e" strokeWidth=".9" />
        <path d="M226 60 l3 3 l5 -6" stroke="#5fc58e" strokeWidth="1.4" fill="none" />
        <text x="238" y="63" fontSize="6.5" fill="#62c88f">connected</text>
      </g>
      <text className="hd-wire-hint" x="160" y="164" textAnchor="middle" fontSize="6.5" fill="#718993">click OUT → click IN · Esc cancels the wire</text>
    </svg>
  );
}

function PulseAnatomyDemo() {
  return (
    <svg className="hd" viewBox="0 0 320 180" role="img" aria-label="Pulse parameters TD, TR, PW, TF and PER on a waveform">
      <rect x="1" y="1" width="318" height="178" rx="6" fill="#0b1419" stroke="#344b55" />
      <line x1="34" y1="118" x2="302" y2="118" stroke="#344b55" strokeWidth="1" />
      <line x1="34" y1="30" x2="34" y2="126" stroke="#344b55" strokeWidth="1" />
      <text x="14" y="34" fontSize="6" fill="#718993">V(t)</text>
      <path
        className="hd-pulse-wave"
        d="M34 118 L74 118 L114 46 L206 46 L246 118 L286 118"
        pathLength="100"
        fill="none" stroke="#58cbbb" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round"
      />
      <path d="M286 118 L300 118" stroke="#58cbbb" strokeWidth="2.2" strokeDasharray="3 4" opacity=".45" strokeLinecap="round" />
      <g fontFamily="ui-monospace, monospace" fontSize="6.5" fill="#f0bf64">
        <g className="hd-lbl" style={{ animationDelay: "1.6s" }}>
          <line x1="40" y1="130" x2="68" y2="130" stroke="#e0a443" strokeWidth=".9" />
          <text x="49" y="139">TD</text>
        </g>
        <g className="hd-lbl" style={{ animationDelay: "2.1s" }}>
          <line x1="76" y1="38" x2="112" y2="38" stroke="#e0a443" strokeWidth=".9" />
          <text x="89" y="33">TR</text>
        </g>
        <g className="hd-lbl" style={{ animationDelay: "2.6s" }}>
          <line x1="116" y1="38" x2="204" y2="38" stroke="#e0a443" strokeWidth=".9" />
          <text x="155" y="33">PW</text>
        </g>
        <g className="hd-lbl" style={{ animationDelay: "3.1s" }}>
          <line x1="208" y1="38" x2="244" y2="38" stroke="#e0a443" strokeWidth=".9" />
          <text x="221" y="33">TF</text>
        </g>
        <g className="hd-lbl" style={{ animationDelay: "3.6s" }}>
          <line x1="34" y1="152" x2="300" y2="152" stroke="#e0a443" strokeWidth=".9" />
          <line x1="34" y1="148" x2="34" y2="156" stroke="#e0a443" strokeWidth=".9" />
          <line x1="300" y1="148" x2="300" y2="156" stroke="#e0a443" strokeWidth=".9" />
          <text x="158" y="163">PER ≥ TR + PW + TF</text>
        </g>
      </g>
    </svg>
  );
}

function MeshRefineDemo() {
  const cells = [
    { id: "coarse", label: "~120 cells", step: 25 },
    { id: "nominal", label: "~480 cells", step: 12.5 },
    { id: "fine", label: "~1.9k cells", step: 6.25 },
  ];
  return (
    <svg className="hd" viewBox="0 0 320 180" role="img" aria-label="Mesh refinement from coarse to fine over a trace">
      <defs>
        {cells.map(cell => (
          <pattern key={cell.id} id={`hd-grid-${cell.id}`} width={cell.step} height={cell.step} patternUnits="userSpaceOnUse">
            <path d={`M ${cell.step} 0 L 0 0 0 ${cell.step}`} fill="none" stroke="#58cbbb" strokeWidth=".45" opacity=".85" />
          </pattern>
        ))}
      </defs>
      <rect x="1" y="1" width="318" height="178" rx="6" fill="#0b1419" stroke="#344b55" />
      <rect x="62" y="32" width="196" height="116" rx="6" fill="#14453a" stroke="#1d5a4a" />
      <path d="M84 106 L138 106 L138 66 L236 66" stroke="#d98d47" strokeWidth="5" fill="none" strokeLinecap="round" />
      {cells.map((cell, i) => (
        <g key={cell.id} className={`hd-mesh-${i}`}>
          <rect x="62" y="32" width="196" height="116" fill={`url(#hd-grid-${cell.id})`} />
        </g>
      ))}
      <g fontFamily="ui-monospace, monospace" fontSize="7">
        {cells.map((cell, i) => (
          <g key={cell.id} className={`hd-mesh-${i}`}>
            <rect x="102" y="154" width="116" height="16" rx="8" fill="#122029" stroke="#344b55" />
            <text x="160" y="165" textAnchor="middle" fill="#8ed1d1">{cell.label}</text>
          </g>
        ))}
      </g>
      <text x="160" y="24" textAnchor="middle" fontSize="6.5" fill="#718993">convergence study: compare at least three mesh densities</text>
    </svg>
  );
}

function ProbeDemo() {
  return (
    <svg className="hd" viewBox="0 0 320 180" role="img" aria-label="Universal probe reading field values at clicked points">
      <defs>
        <radialGradient id="hd-field-a" cx=".38" cy=".42" r=".55">
          <stop offset="0%" stopColor="#e06b61" stopOpacity=".85" /><stop offset="55%" stopColor="#e0a443" stopOpacity=".38" /><stop offset="100%" stopColor="#e06b61" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="hd-field-b" cx=".68" cy=".62" r=".5">
          <stop offset="0%" stopColor="#5fc58e" stopOpacity=".8" /><stop offset="60%" stopColor="#58cbbb" stopOpacity=".3" /><stop offset="100%" stopColor="#5fc58e" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="hd-scale" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#5fc58e" /><stop offset="50%" stopColor="#e0a443" /><stop offset="100%" stopColor="#e06b61" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="318" height="178" rx="6" fill="#0b1419" stroke="#344b55" />
      <rect x="40" y="22" width="240" height="120" rx="6" fill="#14453a" stroke="#1d5a4a" />
      <rect x="40" y="22" width="240" height="120" rx="6" fill="url(#hd-field-a)" className="hd-field-a" />
      <rect x="40" y="22" width="240" height="120" rx="6" fill="url(#hd-field-b)" className="hd-field-b" />
      <path d="M64 112 L128 112 L128 58 L252 58" stroke="#d98d47" strokeWidth="4" fill="none" strokeLinecap="round" opacity=".85" />
      <g className="hd-probe" >
        <circle cx="0" cy="0" r="8" fill="none" stroke="#ffffff" strokeWidth="1" opacity=".9" />
        <line x1="-13" y1="0" x2="-5" y2="0" stroke="#fff" strokeWidth="1" /><line x1="5" y1="0" x2="13" y2="0" stroke="#fff" strokeWidth="1" />
        <line x1="0" y1="-13" x2="0" y2="-5" stroke="#fff" strokeWidth="1" /><line x1="0" y1="5" x2="0" y2="13" stroke="#fff" strokeWidth="1" />
      </g>
      <g className="hd-readout hd-read-a">
        <rect x="86" y="42" width="58" height="15" rx="3" fill="#122029" stroke="#4f8791" />
        <text x="115" y="53" textAnchor="middle" fontSize="7" fill="#8ed1d1" fontFamily="ui-monospace, monospace">V 0.94 V</text>
      </g>
      <g className="hd-readout hd-read-b">
        <rect x="182" y="118" width="58" height="15" rx="3" fill="#122029" stroke="#4f8791" />
        <text x="211" y="129" textAnchor="middle" fontSize="7" fill="#8ed1d1" fontFamily="ui-monospace, monospace">V 0.61 V</text>
      </g>
      <g>
        <rect x="64" y="156" width="192" height="8" rx="4" fill="url(#hd-scale)" opacity=".85" />
        <text x="64" y="174" fontSize="6" fill="#718993">min</text>
        <text x="250" y="174" fontSize="6" fill="#718993">max</text>
      </g>
    </svg>
  );
}

function TerminalPlacementDemo() {
  return (
    <svg className="hd" viewBox="0 0 320 180" role="img" aria-label="Source and load anchors placed on exact copper with an explicit return">
      <rect x="1" y="1" width="318" height="178" rx="6" fill="#0b1419" stroke="#344b55" />
      <rect x="46" y="30" width="228" height="120" rx="6" fill="#14453a" stroke="#1d5a4a" />
      <text x="56" y="46" fontSize="6.5" fill="#7fae9f">+12V rail</text>
      <path d="M78 96 L242 96" stroke="#d98d47" strokeWidth="6" strokeLinecap="round" />
      <path d="M96 96 L96 118 L224 118 L224 96" stroke="#d98d47" strokeWidth="3" fill="none" opacity=".65" strokeLinecap="round" />
      <rect x="72" y="90" width="12" height="12" rx="1.5" fill="#16262f" stroke="#d98d47" />
      <rect x="236" y="90" width="12" height="12" rx="1.5" fill="#16262f" stroke="#d98d47" />
      <g className="hd-anchor hd-anchor-src">
        <circle cx="78" cy="96" r="6.5" fill="#142922" stroke="#5fc58e" strokeWidth="1.6" />
        <text x="78" y="98.8" textAnchor="middle" fontSize="6.5" fill="#62c88f" fontWeight="700">S</text>
        <text x="78" y="82" textAnchor="middle" fontSize="6" fill="#62c88f">source anchor</text>
      </g>
      <g className="hd-anchor hd-anchor-load">
        <circle cx="242" cy="96" r="6.5" fill="#2d1e1d" stroke="#e06b61" strokeWidth="1.6" />
        <text x="242" y="98.8" textAnchor="middle" fontSize="6.5" fill="#eb746a" fontWeight="700">L</text>
        <text x="242" y="82" textAnchor="middle" fontSize="6" fill="#eb746a">load anchor</text>
      </g>
      <g className="hd-return">
        <path d="M96 118 L224 118" stroke="#8ed1d1" strokeWidth="1.4" strokeDasharray="4 3" fill="none" />
        <text x="160" y="131" textAnchor="middle" fontSize="6" fill="#8ed1d1">explicit return net</text>
      </g>
      <g className="hd-anchor-check">
        <rect x="128" y="52" width="64" height="14" rx="7" fill="#142922" stroke="#5fc58e" strokeWidth=".9" />
        <path d="M137 59 l2.6 2.6 l4.6 -5.4" stroke="#5fc58e" strokeWidth="1.3" fill="none" />
        <text x="149" y="62" fontSize="6.3" fill="#62c88f">preflight ok</text>
      </g>
    </svg>
  );
}

export {
  WorkspaceTourDemo,
  OrbitPivotDemo,
  WireConnectDemo,
  PulseAnatomyDemo,
  MeshRefineDemo,
  ProbeDemo,
  TerminalPlacementDemo,
};
