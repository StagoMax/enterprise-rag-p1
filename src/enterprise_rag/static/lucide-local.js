/* Locally vendored Lucide icon subset used by the P2 workbench. */
(function () {
  "use strict";

  const icons = {
    search: [
      ["circle", { cx: "11", cy: "11", r: "8" }],
      ["path", { d: "m21 21-4.3-4.3" }],
    ],
    library: [
      ["path", { d: "m16 6 4 14" }],
      ["path", { d: "M12 6v14" }],
      ["path", { d: "M8 8v12" }],
      ["path", { d: "M4 4v16" }],
    ],
    network: [
      ["rect", { x: "16", y: "16", width: "6", height: "6", rx: "1" }],
      ["rect", { x: "2", y: "16", width: "6", height: "6", rx: "1" }],
      ["rect", { x: "9", y: "2", width: "6", height: "6", rx: "1" }],
      ["path", { d: "M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3" }],
      ["path", { d: "M12 12V8" }],
    ],
    "chart-no-axes-combined": [
      ["path", { d: "M12 16v5" }],
      ["path", { d: "M16 14v7" }],
      ["path", { d: "M20 10v11" }],
      ["path", { d: "M4 18v3" }],
      ["path", { d: "M8 14v7" }],
      ["path", { d: "m3 3 5 5 4-4 5 5 4-4" }],
    ],
    "shield-check": [
      ["path", { d: "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.68 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" }],
      ["path", { d: "m9 12 2 2 4-4" }],
    ],
    "arrow-up": [
      ["path", { d: "m5 12 7-7 7 7" }],
      ["path", { d: "M12 19V5" }],
    ],
    "thumbs-up": [
      ["path", { d: "M7 10v12" }],
      ["path", { d: "M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2h0a3.13 3.13 0 0 1 3 3.88Z" }],
    ],
    "thumbs-down": [
      ["path", { d: "M17 14V2" }],
      ["path", { d: "M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22h0a3.13 3.13 0 0 1-3-3.88Z" }],
    ],
    "file-warning": [
      ["path", { d: "M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" }],
      ["polyline", { points: "14 2 14 8 20 8" }],
      ["path", { d: "M12 9v4" }],
      ["path", { d: "M12 17h.01" }],
    ],
    "shield-alert": [
      ["path", { d: "M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.68 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" }],
      ["path", { d: "M12 8v4" }],
      ["path", { d: "M12 16h.01" }],
    ],
    upload: [
      ["path", { d: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" }],
      ["polyline", { points: "17 8 12 3 7 8" }],
      ["line", { x1: "12", y1: "3", x2: "12", y2: "15" }],
    ],
  };

  function createIcons(options = {}) {
    const namespace = "http://www.w3.org/2000/svg";
    document.querySelectorAll("[data-lucide]").forEach((placeholder) => {
      const name = placeholder.getAttribute("data-lucide");
      const definition = icons[name];
      if (!definition) return;

      const svg = document.createElementNS(namespace, "svg");
      const attributes = {
        xmlns: namespace,
        width: "24",
        height: "24",
        viewBox: "0 0 24 24",
        fill: "none",
        stroke: "currentColor",
        "stroke-width": "2",
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
        class: `lucide lucide-${name}`,
        ...(options.attrs || {}),
      };
      Object.entries(attributes).forEach(([key, value]) => svg.setAttribute(key, value));

      definition.forEach(([tag, childAttributes]) => {
        const child = document.createElementNS(namespace, tag);
        Object.entries(childAttributes).forEach(([key, value]) => child.setAttribute(key, value));
        svg.append(child);
      });
      placeholder.replaceWith(svg);
    });
  }

  window.lucide = { createIcons };
}());
