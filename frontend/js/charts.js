/**
 * Zero-dependency responsive SVG charts with hover crosshairs and tooltips.
 */

const SVG_NS = "http://www.w3.org/2000/svg";

export const ORDER_COLORS = {
  "ROTH-BRKG-401K": "#0f766e",
  "ROTH-401K-BRKG": "#2563eb",
  "BRKG-ROTH-401K": "#7c3aed",
  "401K-BRKG-ROTH": "#d97706",
  "401K-ROTH-BRKG": "#dc2626",
  "BRKG-401K-ROTH": "#64748b",
};

export function fmtCurrency(val) {
  if (val === null || val === undefined || Number.isNaN(val)) return "--";
  const sign = val < 0 ? "-" : "";
  return `${sign}$${Math.round(Math.abs(val)).toLocaleString("en-US")}`;
}

export function fmtShortCurrency(val) {
  if (val === null || val === undefined || Number.isNaN(val)) return "--";
  const abs = Math.abs(val);
  const sign = val < 0 ? "-" : "";
  if (abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(0)}k`;
  return `${sign}$${Math.round(abs)}`;
}

export function fmtPct(val, digits = 1) {
  if (val === null || val === undefined || Number.isNaN(val)) return "--";
  return `${(val * 100).toFixed(digits)}%`;
}

function el(tag, attrs = {}, text = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) {
    node.setAttribute(k, String(v));
  }
  if (text !== null) {
    node.textContent = text;
  }
  return node;
}

function createLegend(host, items) {
  const wrap = document.createElement("div");
  wrap.className = "chart-legend";
  for (const item of items) {
    const entry = document.createElement("span");
    entry.className = "legend-item";
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.background = item.color;
    entry.append(swatch, document.createTextNode(item.name));
    wrap.appendChild(entry);
  }
  host.appendChild(wrap);
}

function showTooltip(clientX, clientY, lines) {
  const tip = document.getElementById("chart-tooltip");
  if (!tip) return;
  tip.replaceChildren();
  lines.forEach((line, idx) => {
    const row = document.createElement("div");
    if (idx === 0) row.style.fontWeight = "700";
    if (line.color) {
      const dot = document.createElement("span");
      dot.textContent = "● ";
      dot.style.color = line.color;
      row.appendChild(dot);
    }
    row.appendChild(document.createTextNode(line.text));
    tip.appendChild(row);
  });
  tip.hidden = false;
  const pad = 14;
  const x = Math.min(window.innerWidth - 270, clientX + pad);
  const y = Math.max(12, clientY - 16);
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
}

function hideTooltip() {
  const tip = document.getElementById("chart-tooltip");
  if (tip) tip.hidden = true;
}

function niceBounds(values, forceZeroMin = false) {
  let minV = forceZeroMin ? 0 : Math.min(...values);
  let maxV = Math.max(...values);
  if (forceZeroMin) minV = Math.min(0, minV);
  if (Math.abs(maxV - minV) < 1e-6) {
    maxV = minV + 1;
  }
  const span = maxV - minV;
  const paddedMax = maxV + span * 0.06;
  const paddedMin = forceZeroMin && minV === 0 ? 0 : minV - span * 0.04;
  return [paddedMin, paddedMax];
}

export function renderLineChart(host, config) {
  host.replaceChildren();
  const {
    series,
    xLabel = "",
    yLabel = "",
    xTickFmt = (v) => String(Math.round(v)),
    yTickFmt = fmtShortCurrency,
    refX = null,
    refLabel = "",
    forceZeroY = true,
    showPeakStars = false,
  } = config;

  const validSeries = series.filter((s) => s.points && s.points.length > 0);
  if (!validSeries.length) {
    const p = document.createElement("p");
    p.className = "card-sub";
    p.textContent = "No chart data available.";
    host.appendChild(p);
    return;
  }

  createLegend(host, validSeries);

  const W = 720;
  const H = 310;
  const m = { top: 18, right: 20, bottom: 42, left: 74 };
  const plotW = W - m.left - m.right;
  const plotH = H - m.top - m.bottom;

  const allX = validSeries.flatMap((s) => s.points.map((p) => p.x));
  const allY = validSeries.flatMap((s) => s.points.map((p) => p.y));
  const [xMin, xMax] = [Math.min(...allX), Math.max(...allX)];
  const [yMin, yMax] = niceBounds(allY, forceZeroY);

  const sx = (x) =>
    m.left + ((xMax === xMin ? 0.5 : (x - xMin) / (xMax - xMin)) * plotW);
  const sy = (y) =>
    m.top + plotH - ((y - yMin) / (yMax - yMin)) * plotH;

  const svg = el("svg", {
    class: "chart-svg",
    viewBox: `0 0 ${W} ${H}`,
    role: "img",
    "aria-label": `${yLabel} vs ${xLabel}`.trim(),
  });

  // Gridlines & Y ticks
  const yTicks = 5;
  for (let i = 0; i <= yTicks; i++) {
    const val = yMin + ((yMax - yMin) * i) / yTicks;
    const py = sy(val);
    svg.appendChild(
      el("line", {
        x1: m.left,
        y1: py,
        x2: W - m.right,
        y2: py,
        stroke: "currentColor",
        "stroke-opacity": i === 0 ? "0.28" : "0.11",
        "stroke-width": "1",
      })
    );
    svg.appendChild(
      el(
        "text",
        {
          x: m.left - 8,
          y: py + 4,
          "text-anchor": "end",
          fill: "currentColor",
          "fill-opacity": "0.72",
          "font-size": "11",
        },
        yTickFmt(val)
      )
    );
  }

  // X ticks
  const xTicks = 6;
  for (let i = 0; i <= xTicks; i++) {
    const val = xMin + ((xMax - xMin) * i) / xTicks;
    const px = sx(val);
    svg.appendChild(
      el("line", {
        x1: px,
        y1: m.top,
        x2: px,
        y2: m.top + plotH,
        stroke: "currentColor",
        "stroke-opacity": "0.08",
      })
    );
    svg.appendChild(
      el(
        "text",
        {
          x: px,
          y: m.top + plotH + 18,
          "text-anchor": "middle",
          fill: "currentColor",
          "fill-opacity": "0.72",
          "font-size": "11",
        },
        xTickFmt(val)
      )
    );
  }

  if (xLabel) {
    svg.appendChild(
      el(
        "text",
        {
          x: m.left + plotW / 2,
          y: H - 5,
          "text-anchor": "middle",
          fill: "currentColor",
          "fill-opacity": "0.75",
          "font-size": "11.5",
          "font-weight": "600",
        },
        xLabel
      )
    );
  }

  // Vertical reference line (e.g. Evaluation Age)
  if (refX !== null && refX >= xMin && refX <= xMax) {
    const rx = sx(refX);
    svg.appendChild(
      el("line", {
        x1: rx,
        y1: m.top,
        x2: rx,
        y2: m.top + plotH,
        stroke: "var(--accent)",
        "stroke-dasharray": "5 4",
        "stroke-width": "1.5",
      })
    );
    if (refLabel) {
      svg.appendChild(
        el(
          "text",
          {
            x: Math.min(rx + 5, W - m.right - 70),
            y: m.top + 12,
            fill: "var(--accent)",
            "font-size": "11",
            "font-weight": "700",
          },
          refLabel
        )
      );
    }
  }

  // Series lines
  for (const s of validSeries) {
    const d = s.points
      .map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`)
      .join(" ");
    svg.appendChild(
      el("path", {
        d,
        fill: "none",
        stroke: s.color,
        "stroke-width": s.width || "2.3",
        "stroke-dasharray": s.dash || "",
        "stroke-linejoin": "round",
        "stroke-linecap": "round",
      })
    );

    if (showPeakStars) {
      const peak = s.points.reduce((a, b) => (b.y > a.y ? b : a), s.points[0]);
      svg.appendChild(
        el("circle", {
          cx: sx(peak.x),
          cy: sy(peak.y),
          r: 4.8,
          fill: s.color,
          stroke: "var(--surface-card)",
          "stroke-width": "1.5",
        })
      );
    }
  }

  // Crosshair + interactive overlay
  const vLine = el("line", {
    x1: m.left,
    y1: m.top,
    x2: m.left,
    y2: m.top + plotH,
    stroke: "currentColor",
    "stroke-opacity": "0.45",
    "stroke-dasharray": "3 3",
    visibility: "hidden",
  });
  svg.appendChild(vLine);

  const hoverGroup = el("g", { visibility: "hidden" });
  const dots = validSeries.map((s) => {
    const c = el("circle", {
      r: 4,
      fill: s.color,
      stroke: "var(--surface-card)",
      "stroke-width": "1.5",
    });
    hoverGroup.appendChild(c);
    return c;
  });
  svg.appendChild(hoverGroup);

  const hitRect = el("rect", {
    x: m.left,
    y: m.top,
    width: plotW,
    height: plotH,
    fill: "transparent",
    style: "cursor: crosshair;",
  });

  hitRect.addEventListener("pointermove", (ev) => {
    const rect = svg.getBoundingClientRect();
    const relX = ((ev.clientX - rect.left) / rect.width) * W;
    const relY = ((ev.clientY - rect.top) / rect.height) * H;
    const xVal = xMin + ((relX - m.left) / plotW) * (xMax - xMin);
    const yVal = yMin + ((m.top + plotH - relY) / plotH) * (yMax - yMin);

    if (config.scatterSnap) {
      let best = null;
      let bestDist = Infinity;
      const xSpan = xMax - xMin || 1;
      const ySpan = yMax - yMin || 1;
      for (const s of validSeries) {
        for (const p of s.points) {
          const dx = (p.x - xVal) / xSpan;
          const dy = (p.y - yVal) / ySpan;
          const dist = dx * dx + dy * dy;
          if (dist < bestDist) {
            bestDist = dist;
            best = { s, p };
          }
        }
      }
      if (!best) return;
      const px = sx(best.p.x);
      vLine.setAttribute("x1", px);
      vLine.setAttribute("x2", px);
      vLine.setAttribute("visibility", "visible");
      hoverGroup.setAttribute("visibility", "visible");
      dots.forEach((dot, idx) => {
        if (validSeries[idx] === best.s) {
          dot.setAttribute("cx", px);
          dot.setAttribute("cy", sy(best.p.y));
          dot.setAttribute("visibility", "visible");
        } else {
          dot.setAttribute("visibility", "hidden");
        }
      });
      const lines = [
        { text: `${best.s.name}` },
        { text: `${xLabel || "X"}: ${xTickFmt(best.p.x)}`, color: best.s.color },
        { text: `${yLabel || "Y"}: ${fmtCurrency(best.p.y)}`, color: best.s.color },
      ];
      if (best.p.meta) lines.push({ text: best.p.meta });
      showTooltip(ev.clientX, ev.clientY, lines);
      return;
    }

    // Snap by closest X across first series
    let snapX = validSeries[0].points[0].x;
    let minDx = Infinity;
    for (const s of validSeries) {
      for (const p of s.points) {
        const dx = Math.abs(p.x - xVal);
        if (dx < minDx) {
          minDx = dx;
          snapX = p.x;
        }
      }
    }
    const px = sx(snapX);
    vLine.setAttribute("x1", px);
    vLine.setAttribute("x2", px);
    vLine.setAttribute("visibility", "visible");
    hoverGroup.setAttribute("visibility", "visible");

    const lines = [{ text: `${xLabel || "X"}: ${xTickFmt(snapX)}` }];
    validSeries.forEach((s, idx) => {
      let nearest = s.points[0];
      let nd = Infinity;
      for (const p of s.points) {
        const d = Math.abs(p.x - snapX);
        if (d < nd) {
          nd = d;
          nearest = p;
        }
      }
      dots[idx].setAttribute("cx", sx(nearest.x));
      dots[idx].setAttribute("cy", sy(nearest.y));
      dots[idx].setAttribute("visibility", "visible");
      lines.push({
        text: `${s.name}: ${yTickFmt(nearest.y)} (${fmtCurrency(nearest.y)})`,
        color: s.color,
      });
    });
    showTooltip(ev.clientX, ev.clientY, lines);
  });

  hitRect.addEventListener("pointerleave", () => {
    vLine.setAttribute("visibility", "hidden");
    hoverGroup.setAttribute("visibility", "hidden");
    hideTooltip();
  });

  svg.appendChild(hitRect);
  host.appendChild(svg);
}

export function renderBarChart(host, config) {
  host.replaceChildren();
  const { categories, series, xLabel = "Age", yTickFmt = fmtShortCurrency } = config;
  if (!categories.length || !series.length) {
    return;
  }

  createLegend(host, series);

  const W = 720;
  const H = 310;
  const m = { top: 18, right: 16, bottom: 42, left: 74 };
  const plotW = W - m.left - m.right;
  const plotH = H - m.top - m.bottom;

  const allVals = series.flatMap((s) => s.values);
  const yMax = Math.max(1, ...allVals) * 1.06;
  const sy = (v) => m.top + plotH - (v / yMax) * plotH;

  const svg = el("svg", {
    class: "chart-svg",
    viewBox: `0 0 ${W} ${H}`,
    role: "img",
    "aria-label": "Annual Cash Flow, Taxes and Roth Conversions",
  });

  for (let i = 0; i <= 5; i++) {
    const val = (yMax * i) / 5;
    const py = sy(val);
    svg.appendChild(
      el("line", {
        x1: m.left,
        y1: py,
        x2: W - m.right,
        y2: py,
        stroke: "currentColor",
        "stroke-opacity": i === 0 ? "0.28" : "0.11",
      })
    );
    svg.appendChild(
      el(
        "text",
        {
          x: m.left - 8,
          y: py + 4,
          "text-anchor": "end",
          fill: "currentColor",
          "fill-opacity": "0.72",
          "font-size": "11",
        },
        yTickFmt(val)
      )
    );
  }

  const slotW = plotW / categories.length;
  const barW = Math.max(1.5, (slotW * 0.78) / series.length);
  const labelEvery = Math.max(1, Math.ceil(categories.length / 9));

  categories.forEach((cat, idx) => {
    const baseX = m.left + idx * slotW + slotW * 0.11;
    series.forEach((s, sIdx) => {
      const val = Math.max(0, s.values[idx] || 0);
      const bh = Math.max(0, m.top + plotH - sy(val));
      svg.appendChild(
        el("rect", {
          x: (baseX + sIdx * barW).toFixed(1),
          y: sy(val).toFixed(1),
          width: Math.max(1.2, barW - 0.6).toFixed(1),
          height: bh.toFixed(1),
          fill: s.color,
          rx: "1",
        })
      );
    });

    if (idx % labelEvery === 0) {
      svg.appendChild(
        el(
          "text",
          {
            x: (m.left + (idx + 0.5) * slotW).toFixed(1),
            y: m.top + plotH + 18,
            "text-anchor": "middle",
            fill: "currentColor",
            "fill-opacity": "0.72",
            "font-size": "11",
          },
          String(cat)
        )
      );
    }

    const colHit = el("rect", {
      x: (m.left + idx * slotW).toFixed(1),
      y: m.top,
      width: slotW.toFixed(1),
      height: plotH,
      fill: "transparent",
      style: "cursor: pointer;",
    });
    colHit.addEventListener("pointermove", (ev) => {
      const lines = [{ text: `${xLabel} ${cat}` }];
      series.forEach((s) => {
        lines.push({
          text: `${s.name}: ${fmtCurrency(s.values[idx] || 0)}`,
          color: s.color,
        });
      });
      showTooltip(ev.clientX, ev.clientY, lines);
    });
    colHit.addEventListener("pointerleave", hideTooltip);
    svg.appendChild(colHit);
  });

  svg.appendChild(
    el(
      "text",
      {
        x: m.left + plotW / 2,
        y: H - 5,
        "text-anchor": "middle",
        fill: "currentColor",
        "fill-opacity": "0.75",
        "font-size": "11.5",
        "font-weight": "600",
      },
      xLabel
    )
  );

  host.appendChild(svg);
}
