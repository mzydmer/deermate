/* Original vector artwork for the README design study.
   Palette resolves from the repository's generated design.md tokens. */
(() => {
  "use strict";
  const rootStyle = getComputedStyle(document.documentElement);
  const token = (name) => rootStyle.getPropertyValue("--ds-" + name).trim();
  const C = {
    bg: token("colors-canvas"), soft: token("colors-canvas-soft"), soft2: token("colors-canvas-soft-2"),
    ink: token("colors-ink"), body: token("colors-body"), mute: token("colors-mute"), line: token("colors-hairline"), strong: token("colors-hairline-strong"),
    blue: token("colors-gradient-develop-start"), cyan: token("colors-gradient-develop-end"), violet: token("colors-gradient-preview-start"), pink: token("colors-gradient-preview-end"),
    link: token("colors-link"), lavender: token("colors-violet-deep"),
    sans: token("fontFamilies-sans") || "Geist, Inter, system-ui, -apple-system, sans-serif",
    mono: token("fontFamilies-mono") || "Geist Mono, ui-monospace, SFMono-Regular, Menlo, monospace",
  };
  const esc = (s) => String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll('"', "&quot;");
  const text = (x, y, value, size = 16, color = C.ink, extra = "") => `<text x="${x}" y="${y}" font-size="${size}" fill="${color}" ${extra}>${esc(value)}</text>`;
  const mono = (x, y, value, size = 12, color = C.mute, extra = "") => text(x, y, value, size, color, `font-family="${C.mono}" ${extra}`);
  const center = (x, y, value, size = 16, color = C.ink, extra = "") => text(x, y, value, size, color, `text-anchor="middle" ${extra}`);
  const line = (d, stroke = C.line, width = 1, extra = "") => `<path d="${d}" fill="none" stroke="${stroke}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round" ${extra}/>`;
  const rect = (x, y, w, h, fill = C.soft, stroke = C.line, r = 12, extra = "") => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" ${extra}/>`;
  const dot = (x, y, r = 4, color = C.cyan, extra = "") => `<circle cx="${x}" cy="${y}" r="${r}" fill="${color}" ${extra}/>`;
  const ring = (x, y, r, color = C.cyan, extra = "") => `<circle cx="${x}" cy="${y}" r="${r}" fill="none" stroke="${color}" ${extra}/>`;
  const mark = (x, y, size = 44, color = C.ink) => `<svg x="${x}" y="${y}" width="${size}" height="${size}" viewBox="0 0 128 128" fill="none"><g stroke="${color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><path d="M46 51 37 37 37 20M37 36 24 29M37 27 46 18M82 51 91 37 91 20M91 36 104 29M91 27 82 18"/><path d="M44 54 30 46 35 66 45 70M84 54 98 46 93 66 83 70M45 54Q64 44 83 54L81 84Q77 102 64 107Q51 102 47 84Z"/><path d="m60 91 4 4 4-4" stroke-width="3"/></g><circle cx="55" cy="75" r="3" fill="${color}"/><circle cx="73" cy="75" r="3" fill="${color}"/></svg>`;
  function defs(id) {
    return `<defs>
      <linearGradient id="${id}-signal" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${C.blue}"/><stop offset="1" stop-color="${C.cyan}"/></linearGradient>
      <linearGradient id="${id}-memory" x1="0" y1="0" x2="1" y2="1"><stop stop-color="${C.violet}"/><stop offset="1" stop-color="${C.pink}"/></linearGradient>
      <linearGradient id="${id}-metal" x1="0" y1="0" x2="0" y2="1"><stop stop-color="${C.soft2}"/><stop offset=".45" stop-color="${C.soft}"/><stop offset="1" stop-color="${C.bg}"/></linearGradient>
      <radialGradient id="${id}-blue-halo"><stop stop-color="${C.blue}" stop-opacity=".28"/><stop offset="1" stop-color="${C.blue}" stop-opacity="0"/></radialGradient>
      <radialGradient id="${id}-purple-halo"><stop stop-color="${C.violet}" stop-opacity=".25"/><stop offset="1" stop-color="${C.violet}" stop-opacity="0"/></radialGradient>
      <filter id="${id}-glow" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="5"/></filter>
      <filter id="${id}-soft-glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="15"/></filter>
      <pattern id="${id}-grid" width="36" height="36" patternUnits="userSpaceOnUse"><path d="M36 0H0V36" fill="none" stroke="${C.line}" stroke-width=".6" opacity=".5"/></pattern>
      <marker id="${id}-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="m1 1 6 3-6 3" fill="none" stroke="${C.cyan}" stroke-width="1.3"/></marker>
      <marker id="${id}-arrow-v" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="m1 1 6 3-6 3" fill="none" stroke="${C.lavender}" stroke-width="1.3"/></marker>
    </defs>`;
  }
  function svg(w, h, content, id = "art", label = "DeerMate architecture concept") {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}" style="font-family:${C.sans};background:${C.bg}">${defs(id)}<rect width="${w}" height="${h}" fill="${C.bg}"/>${content}</svg>`;
  }
  function packet(x, y, id, color = C.cyan, size = 4) { return dot(x, y, size * 2.5, color, `opacity=".23" filter="url(#${id}-glow)"`) + dot(x, y, size, color); }
  function pill(x, y, label, color = C.body, width = null) {
    const w = width || label.length * 7 + 24;
    return rect(x, y, w, 28, C.soft, C.line, 6) + mono(x + 12, y + 18, label, 11, color);
  }
  function floor(id, x = 0, y = 0, scale = 1) {
    let s = `<g transform="translate(${x} ${y}) scale(${scale})" opacity=".32">`;
    for (let i = -8; i <= 8; i++) s += line(`M${600 + i * 45} 260  ${600 + i * 115} 650`, C.line, .6);
    for (let i = 0; i < 7; i++) s += line(`M${230 - i * 30} ${300 + i * 47}H${970 + i * 30}`, C.line, .6);
    return s + "</g>";
  }
  function core(x, y, scale = 1, id = "art", intensity = 1) {
    return `<g transform="translate(${x} ${y}) scale(${scale})">
      <ellipse cx="0" cy="50" rx="198" ry="113" fill="url(#${id}-blue-halo)"/>
      <ellipse cx="15" cy="78" rx="133" ry="44" fill="none" stroke="${C.blue}" opacity=".2"/>
      <ellipse cx="15" cy="78" rx="162" ry="55" fill="none" stroke="${C.blue}" opacity=".12"/>
      <path d="M0-74 122-3 0 69-122-3Z" fill="url(#${id}-metal)" stroke="${C.strong}" stroke-opacity=".45"/>
      <path d="M-122-3V17L0 89V69Z" fill="${C.soft}" stroke="${C.line}"/>
      <path d="M122-3V17L0 89V69Z" fill="${C.bg}" stroke="${C.line}"/>
      <path d="M0-95 122-24 0 48-122-24Z" fill="${C.soft}" stroke="url(#${id}-signal)" stroke-opacity=".7"/>
      <path d="M-122-24V-4L0 68V48Z" fill="${C.soft2}" stroke="${C.blue}" stroke-opacity=".25"/>
      <path d="M122-24V-4L0 68V48Z" fill="${C.soft}" stroke="${C.blue}" stroke-opacity=".3"/>
      <path d="M0-116 122-45 0 27-122-45Z" fill="url(#${id}-metal)" stroke="url(#${id}-signal)"/>
      <path d="M0-116 122-45 0 27-122-45Z" fill="none" stroke="${C.cyan}" opacity="${.22 * intensity}" filter="url(#${id}-glow)" stroke-width="4"/>
      <path d="M-122-45V-25L0 47V27Z" fill="${C.soft2}" stroke="${C.blue}" stroke-opacity=".45"/>
      <path d="M122-45V-25L0 47V27Z" fill="${C.soft}" stroke="${C.cyan}" stroke-opacity=".35"/>
      ${mark(-47, -103, 94, C.ink)}
      ${center(0, 73, "GO / ADMISSION", 12, C.cyan, `font-family="${C.mono}"`)}
      ${line("M-90 105H90", C.cyan, 1, 'opacity=".4"')}
      ${dot(-90, 105, 2, C.cyan)}${dot(90, 105, 2, C.cyan)}
    </g>`;
  }
  function router(x, y, id, label = true) {
    return `<g transform="translate(${x} ${y})">${ring(0, 0, 27, C.blue, 'stroke-width="1"')}${ring(0, 0, 18, C.cyan, 'stroke-width="1" opacity=".8"')}${line("M-10 0H10M0-10V10", C.cyan, 1.5)}${dot(0, 0, 3, C.ink)}${[-1, 1].map(s => dot(s * 37, 0, 2, C.blue)).join("")}${label ? center(0, 53, "DeerFlow Router", 16, C.ink, 'font-weight="500"') : ""}</g>`;
  }
  function native(x, y, id, label = true) {
    return `<g transform="translate(${x} ${y})">${rect(-55, -35, 110, 70, `url(#${id}-metal)`, C.strong, 8)}${line("M-55-13H55", C.line)}${dot(-40, -24, 2, C.cyan)}${line("M-34 5l9 7-9 7M-16 19H5", C.cyan, 2)}${text(12, 15, "λ", 24, C.ink)}${line("M-33 35v10h66V35", C.line)}${label ? center(0, 72, "Python Worker", 16, C.ink, 'font-weight="500"') + center(0, 96, "Codex native session", 12, C.body) : ""}</g>`;
  }
  function memory(x, y, id, label = true) {
    return `<g transform="translate(${x} ${y})">${line("M-24 18 0-23 30 14-24 18M0-23 0 25M-24 18 30 14", C.violet, 1.3)}${ring(-24, 18, 5, C.lavender)}${ring(0, -23, 7, C.lavender)}${dot(30, 14, 5, C.pink)}${dot(0, 25, 3, C.lavender)}${label ? center(0, 61, "DeerMem + FTS5", 16, C.ink, 'font-weight="500"') + center(0, 84, "Source-bound memory", 12, C.body) : ""}</g>`;
  }
  function evidence(x, y, id, label = true) {
    return `<g transform="translate(${x} ${y})">${[-1, 0, 1].map((i) => rect(-32 + i * 12, -30 + i * 3, 64, 70, C.soft, i === 1 ? C.cyan : C.line, 5) + line(`M${-18 + i * 12} ${-10 + i * 3}H${11 + i * 12}M${-18 + i * 12} ${2 + i * 3}H${18 + i * 12}M${-18 + i * 12} ${14 + i * 3}H${7 + i * 12}`, C.body, 1, 'opacity=".6"')).join("")}${label ? center(0, 73, "Evidence ledger", 16, C.ink, 'font-weight="500"') : ""}</g>`;
  }

  function heroSvg() {
    const id = "hero";
    let s = `<ellipse cx="871" cy="349" rx="379" ry="296" fill="url(#${id}-blue-halo)"/><ellipse cx="993" cy="541" rx="205" ry="139" fill="url(#${id}-purple-halo)"/>`;
    s += floor(id, 220, 160, 1);
    s += mark(54, 45, 38) + text(105, 73, "DeerMate", 24, C.ink, 'font-weight="600" letter-spacing="-.96"');
    s += mono(64, 166, "PERSONAL AGENT CONTROL PLANE", 12, C.link);
    s += text(60, 236, "Your agents.", 48, C.ink, 'font-weight="600" letter-spacing="-2.4"');
    s += text(60, 292, "One control plane.", 48, C.ink, 'font-weight="600" letter-spacing="-2.4"');
    s += text(64, 340, "One conversation. Persistent sessions.", 18, C.body);
    s += text(64, 368, "Work you can verify.", 18, C.body);
    s += pill(64, 414, "Go × DeerFlow × Python", C.ink, 218);
    s += mono(64, 586, "MIT  /  SELF-HOSTED  /  ALPHA", 12, C.body);
    s += text(64, 620, "Your agents. Your machines. Your control.", 14, C.mute);
    // All signals are illustrative, not live run telemetry.
    s += `<g>${line("M663 212C715 212 745 252 813 270", C.blue, 1.5)}${line("M775 276C735 268 725 235 680 230", C.blue, 1, 'stroke-dasharray="3 6" opacity=".45"')}${line("M942 365C1031 365 1037 363 1070 370", C.cyan, 1.6)}${line("M1070 398C1040 433 1008 457 983 480", C.blue, 1.5)}${line("M935 488C892 489 871 449 850 415", C.blue, 1, 'stroke-dasharray="3 6" opacity=".65"')}${line("M800 426C759 477 728 499 699 504", C.violet, 1.5)}${line("M656 474C668 409 692 347 789 313", C.violet, 1, 'stroke-dasharray="3 6" opacity=".7"')}</g>`;
    s += router(634, 193, id);
    s += mono(653, 282, "ROUTE PROPOSAL", 10, C.body);
    s += core(830, 346, 1.05, id);
    s += mono(830, 487, "scope · budget · op-id", 11, C.body, 'text-anchor="middle"');
    s += native(1090, 374, id);
    s += mono(1090, 300, "YOUR MACHINE", 11, C.link, 'text-anchor="middle"');
    s += ring(1012, 365, 12, C.cyan, 'stroke-width="1" opacity=".7"');
    s += mono(1008, 343, "SCOPED LINK", 10, C.body, 'text-anchor="middle"');
    s += memory(666, 510, id) + evidence(979, 523, id);
    s += packet(742, 241, id) + packet(1012, 365, id) + packet(744, 480, id, C.lavender, 3);
    s += line("M64 664H1136", C.line) + mono(64, 691, "ARCHITECTURE CONCEPT / ILLUSTRATIVE FLOW", 10, C.mute) + mono(1136, 691, "DEERMATE / V3", 10, C.mute, 'text-anchor="end"');
    return svg(1200, 720, s, id, "DeerMate: a Go admission core coordinating a Router, private memory, and Codex on your machine");
  }

  function mobileHeroSvg() {
    const id = "mobilehero";
    let s = `<ellipse cx="240" cy="195" rx="230" ry="180" fill="url(#${id}-blue-halo)"/>`;
    s += line("M90 103 210 154M324 227H393M226 286 131 340", C.blue, 1.5);
    s += router(75, 88, id, false) + center(75, 139, "Router", 18);
    s += core(240, 211, .72, id);
    s += native(397, 230, id, false) + center(397, 302, "Worker", 18);
    s += memory(109, 340, id, false) + center(109, 390, "Memory", 18);
    s += mono(240, 330, "Go admission", 14, C.cyan, 'text-anchor="middle"');
    return svg(480, 422, s, id);
  }

  function architectureSvg() {
    const id = "architecture";
    let s = `<ellipse cx="489" cy="330" rx="470" ry="280" fill="url(#${id}-blue-halo)"/><ellipse cx="237" cy="639" rx="258" ry="150" fill="url(#${id}-purple-halo)"/>`;
    s += mono(56, 58, "DEERMATE / SYSTEM MAP", 12, C.link);
    s += text(56, 108, "Coordination, with explicit authority.", 32, C.ink, 'font-weight="600" letter-spacing="-1.28"');
    s += text(56, 142, "Go admits work. DeerFlow coordinates. Your machine executes.", 16, C.body);
    s += rect(255, 191, 586, 247, "none", C.line, 16, 'stroke-dasharray="4 6"') + mono(277, 219, "CLOUD CONTROL", 12, C.body);
    s += rect(910, 191, 234, 403, "none", C.line, 16, 'stroke-dasharray="4 6"') + mono(933, 219, "YOUR MACHINE", 12, C.body);
    s += rect(56, 267, 156, 100, C.soft, C.strong, 12) + center(134, 307, "You", 24, C.ink, 'font-weight="500"') + center(134, 339, "Intent + next turn", 12, C.body);
    s += line("M212 317H283", C.cyan, 1.7, `marker-end="url(#${id}-arrow)"`);
    s += rect(283, 253, 222, 151, `url(#${id}-metal)`, C.blue, 12);
    s += text(305, 285, "Go control plane", 20, C.ink, 'font-weight="600"');
    s += text(305, 314, "Identity, scope, budgets", 14, C.body) + text(305, 339, "Durable op-id + records", 14, C.body);
    s += line("M305 363H483", C.line) + mono(305, 385, "ADMISSION BOUNDARY", 11, C.cyan);
    s += rect(578, 253, 236, 151, `url(#${id}-metal)`, C.strong, 12) + router(613, 289, id, false);
    s += text(654, 287, "DeerFlow", 20, C.ink, 'font-weight="600"') + text(654, 314, "Router", 20, C.ink, 'font-weight="600"') + text(601, 351, "Persistent coordination", 14, C.body) + mono(601, 383, "TYPED ROUTE PROPOSALS", 11, C.body);
    s += line("M578 291H505", C.cyan, 1.5, `marker-end="url(#${id}-arrow)"`) + mono(541, 278, "propose", 11, C.body, 'text-anchor="middle"');
    s += line("M505 353H578", C.blue, 1.5) + mono(541, 376, "context", 11, C.body, 'text-anchor="middle"');
    s += rect(934, 263, 186, 94, `url(#${id}-metal)`, C.cyan, 12) + center(1027, 301, "Python Worker", 18, C.ink, 'font-weight="500"') + center(1027, 328, "Project + lifecycle limits", 12, C.body);
    s += rect(934, 396, 186, 100, `url(#${id}-metal)`, C.strong, 12) + center(1027, 437, "Codex", 24, C.ink, 'font-weight="600"') + center(1027, 468, "Native execution session", 12, C.body);
    s += line("M1027 357V396", C.cyan, 1.5) + mono(1045, 382, "native I/O", 10, C.body);
    s += line("M394 404V462Q394 474 406 474H865Q878 474 878 461V322Q878 310 890 310H934", C.cyan, 1.5, `marker-end="url(#${id}-arrow)"`);
    s += mono(627, 459, "ADMITTED WORK · RUNTIME + SCOPED RELAY", 11, C.cyan, 'text-anchor="middle"');
    s += line("M934 447H885Q869 447 869 463V542Q869 554 857 554H400Q384 554 384 538V404", C.blue, 1.5, 'stroke-dasharray="4 5"');
    s += mono(624, 539, "ASSOCIATED EVENTS RETURN TO THE ORIGINAL WORK", 11, C.link, 'text-anchor="middle"');
    s += rect(934, 522, 186, 49, C.soft, C.line, 8) + mono(1027, 542, "topic α", 11, C.body, 'text-anchor="middle"') + mono(1027, 559, "→ native root α", 11, C.cyan, 'text-anchor="middle"');
    s += rect(56, 604, 334, 145, `url(#${id}-metal)`, C.violet, 12) + memory(101, 650, id, false);
    s += text(147, 640, "Private memory", 20, C.ink, 'font-weight="500"') + text(147, 668, "DeerMem files + FTS5", 14, C.body);
    s += mono(81, 720, "source → fact → allowed context", 12, C.lavender);
    s += line("M319 604V567Q319 554 332 554H359V404", C.violet, 1.4) + mono(165, 578, "policy / provenance", 11, C.lavender);
    s += line("M390 652H704Q720 652 720 636V404", C.lavender, 1.3, `marker-end="url(#${id}-arrow-v)"`) + mono(527, 638, "bounded authorized context", 11, C.lavender, 'text-anchor="middle"');
    s += rect(476, 692, 368, 97, C.soft, C.strong, 12) + text(498, 721, "Work evidence", 20, C.ink, 'font-weight="500"');
    s += pill(498, 742, "diff", C.link, 69) + pill(577, 742, "validation", C.link, 104) + pill(691, 742, "source", C.link, 84);
    s += line("M1027 594V741H844", C.blue, 1.4);
    s += mono(1021, 662, "Execution and validation", 11, C.body, 'text-anchor="middle"') + mono(1021, 683, "are separate records.", 11, C.body, 'text-anchor="middle"');
    s += rect(56, 819, 1088, 45, "none", C.line, 8, 'stroke-dasharray="4 6"');
    s += mono(56, 851, "PLANNED ADAPTERS", 11, C.mute) + mono(241, 851, "Claude / ACP  ·  DeepSeek Harness  ·  Hermesh", 11, C.body);
    s += mono(56, 882, "HTTPS / SSH terminate at trusted endpoints. Architecture concept; not live telemetry.", 10, C.mute);
    return svg(1200, 912, s, id, "DeerMate system architecture with Go admission, Router coordination, native Worker, private memory and separate work evidence");
  }

  const scenes = [
    { start: 0, end: 4, label: "意图进入系统", title: "One intent. A connected system.", subtitle: "A private control plane for your personal agents.", description: "从一个意图开始，把协调、执行与上下文连成系统。" },
    { start: 4, end: 10, label: "范围先于行动", title: "Route intent. Keep authority explicit.", subtitle: "A proposal crosses an admission boundary before work begins.", description: "路由提议先经过身份、范围、预算和操作身份接纳。" },
    { start: 10, end: 16, label: "协调与工作并行", title: "The secretary stays present.", subtitle: "Independent workers keep going in their own sessions.", description: "Router 继续接待新请求，Worker 在独立会话推进原工作。" },
    { start: 16, end: 22, label: "接回同一个原生根", title: "Same topic. Same native root.", subtitle: "Reconcile, then resume the original operation.", description: "跨设备不丢会话身份；中断后先核对原操作。" },
    { start: 22, end: 28, label: "记忆带着来源", title: "Context with a source.", subtitle: "Private facts enter context through scope and policy checks.", description: "来源进入事实，事实进入获准上下文；旧路径可以退出。" },
    { start: 28, end: 36, label: "带回可检查的证据", title: "Bring back evidence.", subtitle: "A patch, a validation record, and the source behind the result.", description: "执行、独立验证和引用分别记录，再带回同一工作脉络。" },
  ];
  function sceneAt(t) { return Math.min(5, scenes.findIndex((s) => t >= s.start && t < s.end) < 0 ? 5 : scenes.findIndex((s) => t >= s.start && t < s.end)); }
  function pointAlong(points, p) {
    const lengths = points.slice(1).map((q, i) => Math.hypot(q[0] - points[i][0], q[1] - points[i][1]));
    let remaining = lengths.reduce((a, b) => a + b, 0) * Math.max(0, Math.min(1, p));
    for (let i = 0; i < lengths.length; i++) { if (remaining <= lengths[i]) { const q = remaining / lengths[i]; return [points[i][0] + (points[i + 1][0] - points[i][0]) * q, points[i][1] + (points[i + 1][1] - points[i][1]) * q]; } remaining -= lengths[i]; }
    return points.at(-1);
  }
  function filmSvg(t, options = {}) {
    t = Math.max(0, Math.min(36, Number(t) || 0));
    const n = sceneAt(t), info = scenes[n], p = options.reduced ? .65 : (t - info.start) / (info.end - info.start), id = options.id || "film";
    let s = `<ellipse cx="758" cy="390" rx="530" ry="273" fill="url(#${id}-blue-halo)"/><ellipse cx="952" cy="461" rx="239" ry="173" fill="url(#${id}-purple-halo)"/>`;
    s += mark(46, 30, 36) + text(94, 57, "DeerMate", 24, C.ink, 'font-weight="600"');
    s += mono(1232, 52, "ARCHITECTURE CONCEPT", 12, C.mute, 'text-anchor="end"');
    s += mono(56, 127, `0${n + 1} / FROM INTENT TO EVIDENCE`, 12, C.link);
    s += text(54, 188, info.title, 48, C.ink, 'font-weight="600" letter-spacing="-2.4"');
    s += text(56, 226, info.subtitle, 18, C.body);
    if (n === 0) {
      s += floor(id, 0, 0, 1.05) + core(678, 410, 1.18, id);
      s += router(360, 394, id) + native(1008, 402, id) + memory(497, 537, id, false) + evidence(855, 528, id, false);
      s += line("M399 394H527M821 416H946M538 532 590 501M800 505 828 525", C.blue, 1.5);
      const [x, y] = pointAlong([[360, 394], [526, 394], [678, 410]], p); s += packet(x, y, id);
      s += mono(360, 514, "ONE INTENT", 12, C.body, 'text-anchor="middle"') + mono(678, 603, "GO × DEERFLOW × PYTHON", 12, C.cyan, 'text-anchor="middle"');
    } else if (n === 1) {
      s += mono(192, 333, "USER INTENT", 12, C.body, 'text-anchor="middle"') + ring(192, 420, 37, C.blue, 'stroke-width="1.5"') + line("M174 420H210M192 402V438", C.link, 1.5);
      s += line("M230 420H1036", C.line, 2);
      const gx = 508; s += `<path d="M${gx} 322 688 352V520L${gx} 552Z" fill="${C.soft}" stroke="url(#${id}-signal)" stroke-width="1.4"/>`;
      s += text(533, 385, "Go", 32, C.ink, 'font-weight="600"') + mono(533, 413, "ADMISSION", 12, C.cyan);
      s += text(533, 451, "scope", 16, C.body) + text(533, 479, "budget", 16, C.body) + text(533, 507, "op-id", 16, C.body);
      s += router(349, 420, id) + native(1074, 420, id);
      const [x, y] = pointAlong([[240, 420], [500, 420], [1030, 420]], p); s += packet(x, y, id, C.cyan, 6);
      s += mono(787, 391, "ADMITTED WORK", 12, C.cyan) + mono(790, 560, "AUTHORITY STAYS IN THE CONTROL PLANE", 12, C.body, 'text-anchor="middle"');
    } else if (n === 2) {
      s += mono(170, 321, "COORDINATION", 12, C.link) + mono(170, 509, "EXECUTION", 12, C.body);
      s += line("M170 374H1110", C.blue, 2) + line("M170 555H1110", C.cyan, 2);
      s += router(444, 374, id, false) + center(444, 426, "DeerFlow Router", 18);
      s += native(765, 548, id, false) + center(765, 622, "Native Worker session", 18);
      for (let i = 0; i < 3; i++) { const q = (p * 1.6 + i / 3) % 1; s += packet(170 + q * 940, 374, id, C.link, 4); }
      s += packet(170 + p * 940, 555, id, C.cyan, 5) + pill(891, 334, "NEXT REQUEST", C.link, 148);
      s += mono(178, 596, "topic α", 12, C.body) + mono(1106, 596, "native root α", 12, C.cyan, 'text-anchor="end"');
      s += line("M444 410V505Q444 524 464 524H673", C.line, 1, 'stroke-dasharray="4 5"');
    } else if (n === 3) {
      s += rect(102, 309, 359, 255, "none", C.line, 16, 'stroke-dasharray="4 6"') + mono(125, 338, "CLOUD CONTROL", 12, C.body);
      s += rect(807, 309, 368, 255, "none", C.line, 16, 'stroke-dasharray="4 6"') + mono(832, 338, "YOUR MACHINE", 12, C.body);
      s += core(283, 433, .65, id) + native(991, 408, id);
      s += line("M365 415H809", C.cyan, 2, p > .38 && p < .65 ? 'stroke-dasharray="4 14" opacity=".45"' : "");
      s += mono(635, 386, "AUTHORIZED HTTPS / SSH", 12, C.link, 'text-anchor="middle"');
      s += rect(843, 489, 296, 42, C.soft, C.cyan, 8) + mono(991, 516, "topic α → native root α", 14, C.cyan, 'text-anchor="middle"');
      s += line("M155 608H1124", C.blue, 1.5) + mono(178, 636, "OPERATION ID IS RETAINED", 12, C.body) + mono(1120, 636, "RECONCILE, THEN RESUME", 12, C.link, 'text-anchor="end"');
      s += packet(365 + p * 444, 415, id, C.cyan, 5);
      if (p > .38 && p < .65) s += mono(635, 457, "connection interrupted", 12, C.body, 'text-anchor="middle"');
    } else if (n === 4) {
      const nodes = [[201, 421, "Source", "authenticated input"], [596, 421, "Fact", "DeerMem + FTS5"], [1052, 421, "Context", "scope + policy checked"]];
      s += line("M239 421H1008", C.violet, 1.5);
      nodes.forEach(([x, y, title, detail], i) => { s += ring(x, y, i === 1 ? 58 : 37, i === 1 ? C.lavender : C.violet, 'stroke-width="1.3"'); if (i === 1) s += memory(x, y, id, false); else s += dot(x, y, 5, C.lavender); s += center(x, y + 101, title, 24, C.ink, 'font-weight="500"') + center(x, y + 132, detail, 14, C.body); });
      s += packet(239 + p * 769, 421, id, C.lavender, 5);
      s += line("M596 480V606H878", C.line, 1.2, 'stroke-dasharray="3 7" opacity=".7"') + ring(913, 606, 14, C.strong) + mono(948, 610, "OLD PATH EXCLUDED", 12, C.body);
      s += line("M899 593 927 620M900 620 927 593", C.strong, 1.2);
    } else if (n === 5) {
      if (t >= 34) {
        const q = Math.min(1, (t - 34) / 2); s = `<ellipse cx="640" cy="310" rx="500" ry="370" fill="url(#${id}-blue-halo)"/>`;
        s += mark(569, 114, 142) + center(640, 335, "DeerMate", 48, C.ink, 'font-weight="600" letter-spacing="-2.4"') + center(640, 393, "Your agents. Your machines. Your control.", 24, C.body) + center(640, 481, "github.com/mzydmer/deermate", 20, C.link) + center(640, 540, "Go × DeerFlow × Python  /  MIT  /  Self-hosted Alpha", 14, C.body);
        s += ring(640, 204, 112 + q * 20, C.blue, 'opacity=".18"');
      } else {
        const columns = [[281, "diff", "The patch"], [640, "validation", "The independent record"], [1000, "source", "The supporting reference"]];
        columns.forEach(([x, label, detail], i) => { const raise = (1 - Math.min(1, Math.max(0, p * 1.7 - i * .13))) * 35; s += `<g transform="translate(0 ${raise})">${evidence(x, 389, id, false)}${center(x, 478, label, 24, C.ink, 'font-weight="500"')}${center(x, 511, detail, 14, C.body)}</g>`; });
        s += line("M281 552V579H1000V552M640 552V614", C.blue, 1.5) + pill(499, 616, "EXECUTION / VALIDATION", C.cyan, 282);
      }
    }
    s += line("M48 677H1232", C.line) + mono(48, 703, "ILLUSTRATIVE FLOW · NOT LIVE TASK TELEMETRY", 10, C.mute) + mono(1232, 703, "DEERMATE / PERSONAL AGENT SYSTEMS", 10, C.mute, 'text-anchor="end"');
    s += `<rect x="0" y="716" width="${1280 * t / 36}" height="4" fill="url(#${id}-signal)"/>`;
    return svg(1280, 720, s, id, info.title + " Architecture concept.");
  }

  function storyboardSvg() {
    const id = "storyboard"; let s = mono(40, 48, "DEERMATE / FROM INTENT TO EVIDENCE", 12, C.link) + text(40, 98, "A 36-second architecture story.", 32, C.ink, 'font-weight="600" letter-spacing="-1.28"');
    scenes.forEach((scene, i) => {
      const col = i % 3, row = Math.floor(i / 3), x = 40 + col * 459, y = 142 + row * 367, frame = filmSvg(scene.start + Math.min(2.7, (scene.end - scene.start) * .6), { id: `sb${i}` });
      s += `<g transform="translate(${x} ${y})"><svg width="422" height="237.375" viewBox="0 0 1280 720">${frame.replace(/^<svg[^>]*>/, "").replace(/<\/svg>$/, "")}</svg>${rect(0, 0, 422, 237.375, "none", C.line, 8)}${mono(0, 268, `${String(scene.start).padStart(2, "0")}–${String(scene.end).padStart(2, "0")}s`, 12, C.link)}${text(0, 301, scene.label, 20, C.ink, 'font-weight="500"')}${text(0, 331, ["一个意图，连接完整系统。", "路由提议先经过接纳边界。", "前台响应与长任务分开。", "断线不改变原生会话身份。", "有来源、范围和退出路径。", "结果与独立验证分别记录。"][i], 14, C.body)}</g>`;
    });
    s += line("M40 884H1380", C.line) + mono(40, 916, "ARCHITECTURE CONCEPT / SIX VISUAL BEATS / NO STAGED EXECUTION", 11, C.mute);
    return svg(1420, 942, s, id, "Six storyboard frames for DeerMate's 36-second architecture film");
  }

  function iconSvg(kind) {
    let s = "";
    if (kind === "routing") s = line("M10 35H41M41 35 70 13M41 35 70 57", C.blue, 1.5) + ring(10, 35, 4, C.cyan) + dot(70, 13, 4, C.cyan) + dot(70, 57, 4, C.blue) + ring(41, 35, 10, C.cyan);
    if (kind === "session") s = line("M7 35H81", C.cyan, 1.5) + [15, 44, 73].map(x => ring(x, 35, 9, C.blue) + dot(x, 35, 2, C.cyan)).join("") + line("M15 53H73", C.line);
    if (kind === "scope") s = line("M21 12 64 20V48L21 60Z", C.cyan, 1.5) + line("M5 35H78", C.blue, 1.2) + ring(44, 35, 8, C.cyan) + dot(44, 35, 2, C.ink);
    if (kind === "memory") s = line("M15 49 40 14 72 43 43 62 15 49M40 14 43 62", C.violet, 1.5) + [[15, 49], [40, 14], [72, 43]].map(([x, y]) => ring(x, y, 5, C.lavender)).join("") + dot(43, 62, 3, C.pink);
    return svg(88, 72, s, `icon-${kind}`);
  }

  const exports = { hero: heroSvg, architecture: architectureSvg, storyboard: storyboardSvg, film: () => filmSvg(0) };
  window.assetSvg = (name) => exports[name]?.();
  const params = new URLSearchParams(location.search), mode = params.get("export"), exportRoot = document.getElementById("export-root");
  let filmTarget;
  if (exports[mode]) {
    document.body.classList.add("export-mode"); exportRoot.hidden = false;
    const sizes = { hero: [1600, 960], architecture: [1600, 1216], storyboard: [1800, 1195], film: [1280, 720] };
    exportRoot.style.width = sizes[mode][0] + "px"; exportRoot.style.height = sizes[mode][1] + "px";
    exportRoot.innerHTML = exports[mode](); if (mode === "film") filmTarget = exportRoot;
  } else {
    document.getElementById("header-mark").innerHTML = mark(0, 0, 28);
    document.getElementById("hero-stage").innerHTML = heroSvg();
    document.getElementById("mobile-hero-art").innerHTML = mobileHeroSvg();
    document.getElementById("architecture-stage").innerHTML = architectureSvg();
    document.getElementById("storyboard-stage").innerHTML = storyboardSvg();
    document.querySelectorAll("[data-icon]").forEach(el => el.innerHTML = iconSvg(el.dataset.icon));
    document.getElementById("mobile-storyboard").innerHTML = scenes.map((s, i) => `<article>${filmSvg(s.start + 2, { id: `ms${i}` })}<h3>${esc(s.label)}</h3><span>${String(s.start).padStart(2, "0")}–${String(s.end).padStart(2, "0")}s</span><p>${esc(s.description)}</p></article>`).join("");
    filmTarget = document.getElementById("film-stage");
  }
  const play = document.getElementById("play"), slider = document.getElementById("timeline"), timecode = document.getElementById("timecode"), reduce = document.getElementById("reduce-motion");
  let playing = false, time = 0, lastStamp = null, reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const format = t => "00:" + String(Math.floor(t)).padStart(2, "0");
  window.renderFrame = (seconds, options = {}) => {
    time = Math.max(0, Math.min(36, Number(seconds) || 0));
    if (filmTarget) filmTarget.innerHTML = filmSvg(time, { reduced: options.reduced ?? reduced });
    slider.value = time; timecode.textContent = format(time) + " / 00:36";
    const current = sceneAt(time); document.querySelectorAll(".chapter-nav button").forEach((b, i) => b.setAttribute("aria-pressed", String(i === current)));
    return { time, scene: current, width: 1280, height: 720 };
  };
  window.setReducedMotion = value => { reduced = !!value; reduce.checked = reduced; window.renderFrame(time); };
  function setPlaying(value) { playing = value; lastStamp = null; play.querySelector(".play-symbol").textContent = value ? "Ⅱ" : "▶"; document.getElementById("play-label").textContent = value ? "暂停" : "播放概念片"; play.setAttribute("aria-label", value ? "暂停架构概念片" : "播放架构概念片"); if (value) requestAnimationFrame(tick); }
  function tick(stamp) { if (!playing) return; if (lastStamp !== null) window.renderFrame(time + (stamp - lastStamp) / 1000); lastStamp = stamp; if (time >= 36) setPlaying(false); else requestAnimationFrame(tick); }
  play.addEventListener("click", () => { if (time >= 36) window.renderFrame(0); setPlaying(!playing); });
  slider.addEventListener("input", () => { setPlaying(false); window.renderFrame(slider.value); });
  reduce.addEventListener("change", () => window.setReducedMotion(reduce.checked));
  const nav = document.querySelector(".chapter-nav"); scenes.forEach((s, i) => { const b = document.createElement("button"); b.type = "button"; b.textContent = `0${i + 1} / ${s.label}`; b.setAttribute("aria-pressed", String(i === 0)); b.addEventListener("click", () => { setPlaying(false); window.renderFrame(s.start + .25); }); nav.append(b); });
  window.setReducedMotion(reduced); window.renderFrame(params.has("time") ? Number(params.get("time")) : 0);
  window.deermateDesign = { version: "readme-tech-v3", modes: { hero: [1600, 960], architecture: [1600, 1216], storyboard: [1800, 1195], film: [1280, 720] }, scenes, palette: C, ready: true };
})();
