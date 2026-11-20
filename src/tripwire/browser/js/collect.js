// Tripwire in-page collector. Runs once per frame, reads only, changes nothing on the page.
// Returns raw measurements; Python turns them into Trace models and does all judging.
() => {
  const vw = window.innerWidth, vh = window.innerHeight;
  const sx = window.scrollX, sy = window.scrollY;
  const docW = Math.max(document.documentElement.scrollWidth, vw);
  const docH = Math.max(document.documentElement.scrollHeight, vh);

  // ---- traversal (open shadow roots included) ---------------------------------------
  const all = [];
  const walk = (root) => {
    for (const el of root.querySelectorAll("*")) {
      all.push(el);
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  };
  walk(document);
  const parentOf = (el) => el.parentElement || (el.getRootNode() instanceof ShadowRoot ? el.getRootNode().host : null);
  const ancestors = function* (el) { for (let p = parentOf(el); p; p = parentOf(p)) yield p; };
  const inShadow = (el) => el.getRootNode() instanceof ShadowRoot;
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();

  // ---- roles and accessible names (a pragmatic subset of ARIA / accname) -------------
  const INPUT_ROLES = { checkbox: "checkbox", radio: "radio", submit: "button", button: "button", reset: "button",
    image: "button", range: "slider", search: "searchbox", number: "spinbutton" };
  const roleOf = (el) => {
    const explicit = (el.getAttribute("role") || "").split(" ")[0];
    if (explicit && explicit !== "presentation" && explicit !== "none") return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === "a" && el.hasAttribute("href")) return "link";
    if (tag === "button" || tag === "summary") return "button";
    if (tag === "select") return el.multiple || el.size > 1 ? "listbox" : "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") return INPUT_ROLES[el.type] || (el.type === "hidden" ? null : "textbox");
    return null;
  };
  const isInteractive = (el) => {
    const tag = el.tagName.toLowerCase();
    if (tag === "input" && el.type === "hidden") return false;
    if (roleOf(el)) return ["link", "button", "checkbox", "radio", "switch", "textbox", "searchbox", "combobox",
      "listbox", "slider", "spinbutton", "tab", "menuitem", "menuitemcheckbox", "option", "menuitemradio"].includes(roleOf(el));
    return el.hasAttribute("onclick") || (el.hasAttribute("tabindex") && el.tabIndex >= 0);
  };
  const textWithoutControls = (node) => {
    const copy = node.cloneNode(true);
    copy.querySelectorAll("input,select,textarea").forEach((c) => c.remove());
    return clean(copy.textContent);
  };
  const nameOf = (el) => {
    const root = el.getRootNode();
    const byId = (id) => (root.getElementById ? root.getElementById(id) : document.getElementById(id));
    const labelledby = el.getAttribute("aria-labelledby");
    if (labelledby) {
      const t = labelledby.split(/\s+/).map((id) => byId(id)).filter(Boolean).map((n) => clean(n.textContent)).join(" ");
      if (t) return t;
    }
    if (clean(el.getAttribute("aria-label"))) return clean(el.getAttribute("aria-label"));
    const tag = el.tagName.toLowerCase();
    if (["input", "select", "textarea"].includes(tag)) {
      if (tag === "input" && ["submit", "button", "reset"].includes(el.type)) return clean(el.value);
      if (el.labels && el.labels.length) {
        const t = [...el.labels].map(textWithoutControls).join(" ");
        if (t) return t;
      }
      if (clean(el.placeholder)) return clean(el.placeholder);
      return clean(el.title) || null;
    }
    const content = clean(el.innerText || el.textContent);
    return content || clean(el.title) || clean(el.getAttribute("alt")) || null;
  };

  // ---- style helpers -------------------------------------------------------------------
  const style = (el) => getComputedStyle(el);
  const bgLayers = (el) => {
    const layers = [];
    let image = false;
    for (let n = el; n; n = parentOf(n)) {
      const s = style(n);
      if (s.backgroundImage && s.backgroundImage !== "none") { image = true; break; }
      layers.push(s.backgroundColor);
      const m = s.backgroundColor.match(/rgba?\(([^)]+)\)/);
      const alpha = m && m[1].split(/[ ,/]+/).length === 4 ? parseFloat(m[1].split(/[ ,/]+/)[3]) : 1;
      if (alpha >= 1 && s.backgroundColor !== "transparent") break;
    }
    return { layers, image };
  };
  const effectiveOpacity = (el) => {
    let o = 1;
    for (let n = el; n; n = parentOf(n)) o *= parseFloat(style(n).opacity);
    return o;
  };
  const isVisible = (el, r) => {
    const s = style(el);
    if (s.visibility === "hidden" || s.visibility === "collapse" || s.display === "none") return false;
    if (r.width === 0 || r.height === 0) return false;
    if (effectiveOpacity(el) === 0) return false;
    for (const a of ancestors(el)) if (a.hidden) return false;
    return true;
  };
  const zOf = (el) => {
    for (let n = el; n; n = parentOf(n)) {
      const s = style(n);
      if (s.position !== "static" && s.zIndex !== "auto") return parseInt(s.zIndex, 10) || 0;
    }
    return 0;
  };
  const SEMANTIC = new Set(["main", "nav", "header", "footer", "aside", "section", "article", "form", "ul", "ol", "li",
    "table", "tr", "td", "dialog", "fieldset", "details", "menu"]);
  const treeDepth = (el) => {
    let d = 0;
    for (const a of ancestors(el)) {
      const role = a.getAttribute("role");
      if (SEMANTIC.has(a.tagName.toLowerCase()) || (role && !["presentation", "none", "generic"].includes(role))) d++;
    }
    return d;
  };
  const SECTIONING = new Set(["article", "aside", "main", "nav", "section"]);
  const LANDMARK_ROLES = new Set(["banner", "contentinfo", "navigation", "main", "complementary", "region", "form", "search"]);
  const landmarkOf = (el) => {
    for (const a of ancestors(el)) {
      const role = a.getAttribute("role");
      if (role && LANDMARK_ROLES.has(role)) return role;
      const tag = a.tagName.toLowerCase();
      const scoped = () => [...ancestors(a)].some((x) => SECTIONING.has(x.tagName.toLowerCase()));
      if (tag === "footer" && !scoped()) return "contentinfo";
      if (tag === "header" && !scoped()) return "banner";
      if (tag === "nav") return "navigation";
      if (tag === "main") return "main";
      if (tag === "aside") return "complementary";
    }
    return null;
  };
  const struckTexts = (el) => [el, ...el.querySelectorAll("*")]
    .filter((n) => ["del", "s", "strike"].includes(n.tagName.toLowerCase()) || style(n).textDecorationLine.includes("line-through"))
    .map((n) => clean(n.textContent)).filter(Boolean);
  const box = (r) => ({ x: r.left + sx, y: r.top + sy, width: r.width, height: r.height });
  const offScreen = (r) => {
    const b = box(r);
    return b.x + b.width <= 0 || b.y + b.height <= 0 || b.x >= docW || b.y >= docH || (r.width <= 1 && r.height <= 1);
  };

  // ---- interactive elements --------------------------------------------------------
  const ids = new Map();
  const elements = [];
  for (const el of all) {
    if (!isInteractive(el)) continue;
    const r = el.getBoundingClientRect();
    const s = style(el);
    const bg = bgLayers(el);
    const id = "e" + (elements.length + 1);
    ids.set(el, id);
    const isInput = ["input", "select", "textarea"].includes(el.tagName.toLowerCase());
    elements.push({
      id, role: roleOf(el) || "generic", tag: el.tagName.toLowerCase(),
      text: isInput ? "" : clean(el.innerText || el.textContent),
      name: nameOf(el),
      bbox: box(r), visible: isVisible(el, r), offScreen: offScreen(r),
      inViewport: r.right > 0 && r.bottom > 0 && r.left < vw && r.top < vh,
      fontSize: parseFloat(s.fontSize), color: s.color, bgLayers: bg.layers, bgImage: bg.image,
      opacity: effectiveOpacity(el),
      checked: "checked" in el && ["checkbox", "radio"].includes(el.type) ? el.checked
        : (el.getAttribute("aria-checked") ? el.getAttribute("aria-checked") === "true" : null),
      selected: el.getAttribute("aria-selected") ? el.getAttribute("aria-selected") === "true" : null,
      disabled: !!el.disabled || el.getAttribute("aria-disabled") === "true",
      z: zOf(el), depth: treeDepth(el), landmark: landmarkOf(el), inShadow: inShadow(el),
      inputType: el.type || null, autocomplete: el.getAttribute("autocomplete"), fieldName: el.name || null,
    });
  }
  const idOf = (el) => ids.get(el) || null;

  // ---- overlays: fixed/sticky layers above the page ---------------------------------
  const candidates = all.filter((el) => {
    const s = style(el);
    if (s.position !== "fixed" && s.position !== "sticky") return false;
    const tag = el.tagName.toLowerCase(), role = el.getAttribute("role");
    const dialogish = role === "dialog" || role === "alertdialog" || el.getAttribute("aria-modal") === "true" || tag === "dialog";
    if (!dialogish && (["header", "nav"].includes(tag) || ["banner", "navigation"].includes(role))) return false;
    const r = el.getBoundingClientRect();
    if (!isVisible(el, r)) return false;
    const area = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0)) * Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));
    return dialogish || area / (vw * vh) >= 0.05;
  });
  const outermost = candidates.filter((el) => ![...ancestors(el)].some((a) => candidates.includes(a)));
  const contains = (outer, node) => { for (let n = node; n; n = parentOf(n)) if (n === outer) return true; return false; };
  const overlays = outermost.map((el, i) => {
    const r = el.getBoundingClientRect();
    const area = Math.max(0, Math.min(r.right, vw) - Math.max(r.left, 0)) * Math.max(0, Math.min(r.bottom, vh) - Math.max(r.top, 0));
    let hits = 0, total = 0;
    for (const fx of [0.1, 0.5, 0.9]) for (const fy of [0.1, 0.5, 0.9]) {
      total++;
      let hit = document.elementFromPoint(vw * fx, vh * fy);
      while (hit && hit.shadowRoot) { const deeper = hit.shadowRoot.elementFromPoint(vw * fx, vh * fy); if (!deeper || deeper === hit) break; hit = deeper; }
      if (hit && contains(el, hit)) hits++;
    }
    const controls = [...ids.entries()].filter(([node]) => contains(el, node)).map(([, id]) => id);
    return {
      id: "o" + (i + 1), tag: el.tagName.toLowerCase(), role: el.getAttribute("role"),
      ariaModal: el.getAttribute("aria-modal") === "true", label: el.getAttribute("aria-label"),
      bbox: box(r), coverage: Math.min(1, area / (vw * vh)), blocks: hits === total, z: zOf(el),
      text: clean(el.innerText).slice(0, 600), controls, isFrame: el.tagName.toLowerCase() === "iframe",
    };
  });

  // ---- forms -----------------------------------------------------------------------
  const forms = all.filter((el) => el.tagName.toLowerCase() === "form").map((f, i) => {
    const fields = [...f.elements].filter((c) => !["button", "fieldset", "output", "object"].includes(c.tagName.toLowerCase())
      && !["submit", "button", "reset", "image"].includes(c.type));
    const submit = [...f.elements].find((c) => ["submit", "image"].includes(c.type) || (c.tagName.toLowerCase() === "button" && c.type === "submit"));
    return {
      id: "f" + (i + 1), action: f.getAttribute("action"), method: (f.getAttribute("method") || "GET").toUpperCase(),
      submitId: submit ? idOf(submit) : null,
      fields: fields.map((c) => {
        const r = c.getBoundingClientRect();
        const type = c.tagName.toLowerCase() === "input" ? c.type : c.tagName.toLowerCase();
        return {
          name: c.name || "", type, label: nameOf(c), defaultValue: c.tagName.toLowerCase() === "select" ? c.value : (["checkbox", "radio"].includes(type) ? c.value : c.defaultValue),
          prechecked: ["checkbox", "radio"].includes(type) ? c.checked : false,
          hidden: type === "hidden" || !isVisible(c, r), offScreen: type !== "hidden" && offScreen(r),
          required: !!c.required, elementId: idOf(c), autocomplete: c.getAttribute("autocomplete"),
        };
      }),
    };
  });

  // ---- timers: countdown-like text --------------------------------------------------
  const timers = [];
  const CLOCK = /\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b/;
  const SCARCITY = /\b(only\s+\d+\s+left|\d+\s+left\s+in\s+stock|ends\s+in|offer\s+ends|expires\s+in|hurry)\b/i;
  for (const el of all) {
    if (el.children.length || !el.textContent) continue;
    const t = clean(el.textContent);
    if (t.length > 120) continue;
    const r = el.getBoundingClientRect();
    if (!isVisible(el, r)) continue;
    const c = t.match(CLOCK), s = t.match(SCARCITY);
    if (!c && !s) continue;
    let seconds = null, pattern = "other";
    if (c) {
      const [a, b, d] = [parseInt(c[1], 10), parseInt(c[2], 10), c[3] ? parseInt(c[3], 10) : null];
      seconds = d === null ? a * 60 + b : a * 3600 + b * 60 + d;
      pattern = d === null ? "mm:ss" : "hh:mm:ss";
    } else if (/left/i.test(s[0])) pattern = "only N left";
    else pattern = "ends in";
    timers.push({ elementId: idOf(el), text: t, pattern, seconds });
  }

  // ---- price candidates (for the commerce ledger) -----------------------------------
  const CURRENCY = /(₹|Rs\.?\s?\d|INR|US\$|\$|€|£|¥|USD|EUR|GBP|\bfree\b)/i;
  const MONEY = /(₹|Rs\.?\s?\d|INR|US\$|\$|€|£|¥|USD|EUR|GBP)/i;
  const TERMS = /(renew|auto-?renew|after your .{0,30}trial|billed (monthly|annually|yearly)|per (month|year) from|you (will )?pay .{0,40}from|cancel any ?time)/i;
  const prices = [];
  for (const el of all) {
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(" ");
    if (!CURRENCY.test(own) && !(el.children.length === 0 && CURRENCY.test(el.textContent || ""))) continue;
    const r = el.getBoundingClientRect();
    if (!isVisible(el, r)) continue;
    const text = clean(el.innerText || el.textContent);
    if (text.length > 120) continue;
    // "free" counts as a price only when it stands nearly alone ("Delivery: Free"),
    // not inside marketing copy ("14 days free").
    if (!MONEY.test(text) && text.length > 24) continue;
    // Renewal sentences are terms, recorded with their legibility, not ledger lines.
    if (TERMS.test(text)) continue;
    // The label is the nearest short row around the price; big containers are not labels.
    const parent = el.parentElement;
    let row = parent && clean(parent.innerText).length <= 120 ? parent : el;
    let rowText = clean(row.innerText);
    const cell = el.closest("td,th");
    const description = el.closest("dd");
    if (cell && cell.parentElement?.cells?.length === 2 && cell.cellIndex === 1) {
      row = cell.parentElement;
      rowText = clean(row.innerText);
    } else if (description) {
      row = description;
      let term = description.previousElementSibling;
      while (term?.tagName === "DD") term = term.previousElementSibling;
      rowText = term?.tagName === "DT" ? clean(term.innerText + " " + row.innerText) : clean(row.innerText);
    }
    prices.push({ text, rowText, struck: struckTexts(row), bbox: box(r),
      inControl: !!el.closest("label,button,a,select,option,[role=button],[role=checkbox]") });
  }

  // ---- renewal / trial terms: plain text whose legibility matters -------------------
  const terms = [];
  for (const el of all) {
    if (!["p", "span", "small", "div", "li", "label", "td"].includes(el.tagName.toLowerCase())) continue;
    if ([...el.children].some((c) => TERMS.test(c.textContent || ""))) continue; // innermost only
    const t = clean(el.innerText || el.textContent);
    if (!t || t.length > 400 || !TERMS.test(t)) continue;
    const r = el.getBoundingClientRect();
    const s = style(el);
    const bg = bgLayers(el);
    terms.push({ text: t, fontSize: parseFloat(s.fontSize), color: s.color, bgLayers: bg.layers,
      bgImage: bg.image, opacity: effectiveOpacity(el), visible: isVisible(el, r) });
  }

  return { url: location.href, title: document.title, viewport: { width: vw, height: vh },
    elements, overlays, forms, timers, prices, terms };
}
