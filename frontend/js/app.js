import {
  calcCapitalGains,
  calcIncomeTax,
  fetchConfig,
  runDsbVsRate,
  runPerYearOptimize,
  runSimulation,
  runSweep,
} from "./api.js";
import {
  ORDER_COLORS,
  fmtCurrency,
  fmtPct,
  fmtShortCurrency,
  renderBarChart,
  renderLineChart,
} from "./charts.js";

const state = {
  config: null,
  simulation: null,
  sweep: null,
  perYearResult: null,
  dtbOverrides: null,
  legacyExcelRmd: false,
  colView: "core",
  simAbort: null,
  optAbort: null,
};

const PERCENT_FIELDS = new Set([
  "brkg_rate",
  "brkg_gain_pct",
  "brkg_turnover_rate",
  "k401_rate",
  "roth_rate",
  "inflation_rate",
]);

/* ---------- Theme Toggle (dark-mode-toggle) ---------- */
function initThemeToggle() {
  const meta = document.querySelector('meta[name="color-scheme"]');
  const btn = document.getElementById("theme-toggle");
  const mq = window.matchMedia("(prefers-color-scheme: dark)");

  function getStored() {
    try {
      return localStorage.getItem("color-scheme");
    } catch {
      return null;
    }
  }

  function applyScheme(stored) {
    if (meta) meta.content = stored ?? "light dark";
  }

  btn?.addEventListener("click", () => {
    const system = mq.matches ? "dark" : "light";
    const stored = getStored();
    const rendered = stored ?? system;
    const target = rendered === "dark" ? "light" : "dark";
    try {
      if (target !== system) {
        localStorage.setItem("color-scheme", target);
        applyScheme(target);
      } else {
        localStorage.removeItem("color-scheme");
        applyScheme(null);
      }
    } catch {
      applyScheme(target);
    }
  });

  window.addEventListener("storage", (e) => {
    if (e.key === "color-scheme") {
      applyScheme(e.newValue);
    }
  });
}

/* ---------- Tabs & Scrollability Hints ---------- */
function initTabs() {
  const tablist = document.querySelector('[role="tablist"]');
  const tabs = Array.from(tablist.querySelectorAll('[role="tab"]'));
  const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));

  function selectTab(targetTab, focusTab = false) {
    tabs.forEach((tab, idx) => {
      const selected = tab === targetTab;
      tab.ariaSelected = String(selected);
      tab.tabIndex = selected ? 0 : -1;
      const panel = panels[idx];
      if (selected) {
        panel.hidden = false;
        panel.tabIndex = 0;
      } else {
        panel.hidden = "until-found";
        panel.removeAttribute("tabindex");
      }
    });
    targetTab.scrollIntoView({ block: "nearest", inline: "nearest", container: "nearest" });
    if (focusTab) targetTab.focus();
  }

  tabs.forEach((tab, idx) => {
    tab.tabIndex = idx === 0 ? 0 : -1;
    tab.addEventListener("click", () => selectTab(tab));
    tab.addEventListener("keydown", (ev) => {
      let nextIdx = idx;
      if (ev.key === "ArrowRight") nextIdx = (idx + 1) % tabs.length;
      else if (ev.key === "ArrowLeft") nextIdx = (idx - 1 + tabs.length) % tabs.length;
      else if (ev.key === "Home") nextIdx = 0;
      else if (ev.key === "End") nextIdx = tabs.length - 1;
      else return;
      ev.preventDefault();
      selectTab(tabs[nextIdx], true);
    });
  });

  panels.forEach((panel, idx) => {
    panel.addEventListener("beforematch", () => {
      selectTab(tabs[idx]);
    });
  });

  if (!CSS.supports("animation-timeline", "scroll()") && tablist.firstElementChild) {
    const first = tablist.firstElementChild;
    const last = tablist.lastElementChild;
    const obs = new IntersectionObserver(
      (entries) => {
        for (const { target, intersectionRatio } of entries) {
          tablist.classList.toggle(
            target === first ? "more-start" : "more-end",
            intersectionRatio < 1
          );
        }
      },
      { root: tablist, threshold: 1, rootMargin: "1px" }
    );
    obs.observe(first);
    obs.observe(last);
  }
}

/* ---------- Form Population & Validation ---------- */
function applyPresetParams(params) {
  const form = document.getElementById("scenario-form");
  for (const [key, val] of Object.entries(params)) {
    const input = form.elements.namedItem(key);
    if (!input) continue;
    if (PERCENT_FIELDS.has(key)) {
      input.value = String(Number((val * 100).toFixed(4)));
    } else {
      input.value = String(val);
    }
    clearFieldError(input);
  }
  state.legacyExcelRmd = Boolean(params.legacy_excel_rmd);
  state.dtbOverrides = null;
  updateOverrideBadge();
  syncCustomSsVisibility();
}

function updateOverrideBadge() {
  const active = Boolean(state.dtbOverrides && Object.keys(state.dtbOverrides).length > 0);
  document.getElementById("override-badge").hidden = !active;
  document.getElementById("btn-clear-overrides").hidden = !active;
}

function syncCustomSsVisibility() {
  const sel = document.getElementById("ss_profile");
  const panel = document.getElementById("custom-ss-panel");
  const isCustom = sel.value === "Custom";
  panel.hidden = !isCustom;
  sel.setAttribute("aria-expanded", String(isCustom));
}

function readScenarioPayload() {
  const form = document.getElementById("scenario-form");
  const getNum = (name) => Number(form.elements.namedItem(name).value);
  const ssProf = form.elements.namedItem("ss_profile").value;

  const payload = {
    primary_age: Math.round(getNum("primary_age")),
    secondary_age: Math.round(getNum("secondary_age")),
    eval_age: Math.round(getNum("eval_age")),
    brkg_balance: getNum("brkg_balance"),
    brkg_rate: getNum("brkg_rate") / 100,
    brkg_gain_pct: getNum("brkg_gain_pct") / 100,
    brkg_turnover_rate: getNum("brkg_turnover_rate") / 100,
    primary_401k_balance: getNum("primary_401k_balance"),
    secondary_401k_balance: getNum("secondary_401k_balance"),
    k401_rate: getNum("k401_rate") / 100,
    roth_balance: getNum("roth_balance"),
    roth_rate: getNum("roth_rate") / 100,
    dsb: getNum("dsb"),
    dtb: getNum("dtb"),
    inflation_rate: getNum("inflation_rate") / 100,
    withdraw_order: form.elements.namedItem("withdraw_order").value,
    ss_profile: ssProf === "Custom" ? "None" : ssProf,
    legacy_excel_rmd: Boolean(state.legacyExcelRmd),
  };

  if (ssProf === "Custom") {
    payload.custom_ss = {
      primary_start_age: Math.round(getNum("custom_p_start")),
      primary_annual: getNum("custom_p_amt"),
      secondary_start_age: Math.round(getNum("custom_s_start")),
      secondary_annual: getNum("custom_s_amt"),
      wage_annual: getNum("custom_wage_amt"),
      wage_end_age: Math.round(getNum("custom_wage_end")),
    };
  }

  if (state.dtbOverrides && Object.keys(state.dtbOverrides).length > 0) {
    payload.dtb_overrides = state.dtbOverrides;
  }

  return payload;
}

function validateInput(input) {
  input.setCustomValidity("");
  if (input.name === "eval_age") {
    const pAge = Number(document.getElementById("primary_age").value);
    const eAge = Number(input.value);
    if (!Number.isNaN(pAge) && !Number.isNaN(eAge)) {
      if (eAge <= pAge) {
        input.setCustomValidity(`Evaluation age must exceed Primary Age (${pAge}).`);
      } else if (eAge > pAge + 80) {
        input.setCustomValidity(`Evaluation age cannot exceed Primary Age + 80 (${pAge + 80}).`);
      }
    }
  }
  const errEl = document.getElementById(`err-${input.id}`);
  const valid = input.checkValidity();
  if (!valid) {
    input.setAttribute("aria-invalid", "true");
    if (errEl) {
      errEl.textContent = input.validationMessage;
      errEl.hidden = false;
    }
  } else {
    input.removeAttribute("aria-invalid");
    if (errEl) {
      errEl.textContent = "";
      errEl.hidden = true;
    }
  }
  return valid;
}

function clearFieldError(input) {
  input.setCustomValidity("");
  input.removeAttribute("aria-invalid");
  const errEl = document.getElementById(`err-${input.id}`);
  if (errEl) {
    errEl.textContent = "";
    errEl.hidden = true;
  }
}

function validateScenarioForm() {
  const form = document.getElementById("scenario-form");
  const summaryEl = document.getElementById("form-error-summary");
  const controls = Array.from(form.querySelectorAll("input, select"));
  const invalids = [];

  for (const ctrl of controls) {
    if (!ctrl.closest("[hidden]") && !validateInput(ctrl)) {
      invalids.push(ctrl);
    }
  }

  if (invalids.length > 0) {
    summaryEl.textContent = `Please correct ${invalids.length} input field(s) before running the simulation.`;
    summaryEl.hidden = false;
    invalids[0].focus();
    return false;
  }
  summaryEl.hidden = true;
  summaryEl.textContent = "";
  return true;
}

/* ---------- Table Helpers (responsive-table labels) ---------- */
function applyStackableLabels(table) {
  const ths = Array.from(table.querySelectorAll("thead th"));
  ths.forEach((th, idx) => {
    if (idx >= 1) {
      table.style.setProperty(`--label-${idx + 1}`, JSON.stringify(th.textContent.trim()));
    }
  });
}

function makeCell(tag, text, cls = "") {
  const cell = document.createElement(tag);
  cell.textContent = text;
  if (tag === "th") cell.scope = "row";
  if (cls) cell.className = cls;
  return cell;
}

/* ---------- Render Simulation Results ---------- */
function renderSimulation(sim, inflationRate = 0) {
  state.simulation = sim;
  const s = sim.summary;

  document.getElementById("kpi-nw0").textContent = fmtCurrency(s.net_worth_year0);
  document.getElementById("kpi-yr0-ret").textContent = `Yr 0 return: ${fmtCurrency(s.year0_return)}`;
  document.getElementById("kpi-nw-eval-label").textContent = `Net Worth @ Age ${s.eval_age}`;
  document.getElementById("kpi-nw-eval").textContent = fmtCurrency(s.net_worth_at_eval);
  const p0Age = sim.projections[0]?.primary_age ?? 0;
  const evalYrs = Math.max(0, s.eval_age - p0Age);
  if (inflationRate > 0 && evalYrs > 0) {
    const realNw = s.net_worth_at_eval / Math.pow(1 + inflationRate, evalYrs);
    document.getElementById("kpi-wo-sub").textContent = `Order: ${s.withdraw_order} · Today's $: ${fmtCurrency(realNw)}`;
  } else {
    document.getElementById("kpi-wo-sub").textContent = `Order: ${s.withdraw_order}`;
  }
  document.getElementById("kpi-acc-tax-tv").textContent = fmtCurrency(s.acc_tax_tv_at_eval);
  document.getElementById("kpi-acc-tax-nom").textContent = `Nominal: ${fmtCurrency(s.acc_tax_at_eval)}`;
  document.getElementById("kpi-roth-conv").textContent = fmtCurrency(s.total_roth_converted);
  document.getElementById("kpi-cg-tax-tv").textContent = `Cap Gain TV: ${fmtCurrency(s.acc_cg_tax_tv_at_eval)}`;
  document.getElementById("kpi-shortfall").textContent = s.shortfall_age ? `Age ${s.shortfall_age}` : "None (>80 yrs)";
  document.getElementById("kpi-depletion").textContent = s.depletion_age ? `Zero bal: Age ${s.depletion_age}` : "Zero bal: >80 yrs";
  document.getElementById("kpi-irmaa-tier").textContent = `Tier ${s.peak_irmaa_tier}`;
  document.getElementById("kpi-irmaa-total").textContent = `80-yr IRMAA: ${fmtCurrency(s.total_irmaa_surcharge)}`;

  // Balance & Net Worth line chart
  renderLineChart(document.getElementById("chart-balances"), {
    xLabel: "Primary Age",
    yLabel: "Balance ($)",
    refX: s.eval_age,
    refLabel: `Eval ${s.eval_age}`,
    series: [
      {
        name: "Net Worth",
        color: "var(--series-nw)",
        width: "2.8",
        points: sim.projections.map((r) => ({ x: r.primary_age, y: r.net_worth })),
      },
      {
        name: "Brokerage",
        color: "var(--series-brkg)",
        points: sim.projections.map((r) => ({ x: r.primary_age, y: r.brkg_balance })),
      },
      {
        name: "401(k) Combined",
        color: "var(--series-401k)",
        points: sim.projections.map((r) => ({ x: r.primary_age, y: r.k401_balance })),
      },
      {
        name: "Roth IRA",
        color: "var(--series-roth)",
        points: sim.projections.map((r) => ({ x: r.primary_age, y: r.roth_balance })),
      },
    ],
  });

  // Cash flow bar chart (Years 1..45)
  const cfRows = sim.projections.slice(1, 46);
  renderBarChart(document.getElementById("chart-cashflow"), {
    categories: cfRows.map((r) => r.primary_age),
    xLabel: "Primary Age",
    series: [
      {
        name: "Actual Spending",
        color: "var(--series-nw)",
        values: cfRows.map((r) => r.actual_spending),
      },
      {
        name: "Roth Conversion",
        color: "var(--series-roth)",
        values: cfRows.map((r) => r.roth_conv_deposit),
      },
      {
        name: "Total Federal Tax",
        color: "var(--series-tax)",
        values: cfRows.map((r) => r.total_tax),
      },
    ],
  });

  // Milestone table
  const mTable = document.getElementById("milestone-table");
  applyStackableLabels(mTable);
  const mBody = mTable.querySelector("tbody");
  mBody.replaceChildren();
  for (const r of sim.quick_summary) {
    const tr = document.createElement("tr");
    if (r.primary_age === s.eval_age) tr.className = "row-eval-highlight";
    tr.append(
      makeCell("th", String(r.primary_age)),
      makeCell("td", String(r.year)),
      makeCell("td", fmtCurrency(r.brkg_balance)),
      makeCell("td", fmtCurrency(r.k401_balance)),
      makeCell("td", fmtCurrency(r.roth_balance)),
      makeCell("td", fmtCurrency(r.net_worth)),
      makeCell("td", fmtCurrency(r.roth_conv_deposit)),
      makeCell("td", fmtCurrency(r.total_tax)),
      makeCell("td", fmtPct(r.effective_tax_rate)),
      makeCell("td", `Tier ${r.irmaa_tier}`)
    );
    mBody.appendChild(tr);
  }

  renderProjectionMatrix();
}

const PROJECTION_COLUMNS = {
  core: [
    ["Age", (r) => String(r.primary_age)],
    ["Year", (r) => String(r.year)],
    ["Earned Inc", (r) => fmtCurrency(r.earned_income)],
    ["BRKG Flow", (r) => fmtCurrency(r.brkg_cashflow)],
    ["BRKG Bal", (r) => fmtCurrency(r.brkg_balance)],
    ["401k RMD", (r) => fmtCurrency(r.k401_rmd)],
    ["401k Conv", (r) => fmtCurrency(r.k401_conv_wd)],
    ["401k Bal", (r) => fmtCurrency(r.k401_balance)],
    ["Roth Conv", (r) => fmtCurrency(r.roth_conv_deposit)],
    ["Roth WD", (r) => fmtCurrency(r.roth_wd)],
    ["Roth Bal", (r) => fmtCurrency(r.roth_balance)],
    ["Net Worth", (r) => fmtCurrency(r.net_worth)],
    ["Spending", (r) => fmtCurrency(r.actual_spending)],
    ["Fed Tax", (r) => fmtCurrency(r.total_tax)],
  ],
  tax: [
    ["Age", (r) => String(r.primary_age)],
    ["Year", (r) => String(r.year)],
    ["DTB", (r) => fmtCurrency(r.dtb_applied)],
    ["Ord Income", (r) => fmtCurrency(r.ordinary_income)],
    ["Ord Tax", (r) => fmtCurrency(r.ordinary_tax)],
    ["Marg Rate", (r) => fmtPct(r.ordinary_marginal_rate, 0)],
    ["Cap Gains", (r) => fmtCurrency(r.capital_gains)],
    ["CG Rate", (r) => fmtPct(r.cap_gain_tax_rate, 0)],
    ["CG Tax", (r) => fmtCurrency(r.cap_gain_tax)],
    ["NIIT", (r) => fmtCurrency(r.niit_tax)],
    ["Total Tax", (r) => fmtCurrency(r.total_tax)],
    ["Eff Rate", (r) => fmtPct(r.effective_tax_rate)],
    ["Acc Tax TV", (r) => fmtCurrency(r.acc_tax_tv)],
    ["IRMAA Tier", (r) => `T${r.irmaa_tier} (${fmtCurrency(r.irmaa_annual_surcharge)})`],
  ],
  all: [
    ["Age", (r) => String(r.primary_age)],
    ["Yr#", (r) => String(r.year_index)],
    ["Year", (r) => String(r.year)],
    ["Spouse", (r) => String(r.secondary_age)],
    ["Earned Inc", (r) => fmtCurrency(r.earned_income)],
    ["DTB", (r) => fmtCurrency(r.dtb_applied)],
    ["BRKG Flow", (r) => fmtCurrency(r.brkg_cashflow)],
    ["BRKG Bal", (r) => fmtCurrency(r.brkg_balance)],
    ["401k WD", (r) => fmtCurrency(r.k401_total_wd)],
    ["401k RMD", (r) => fmtCurrency(r.k401_rmd)],
    ["401k Conv", (r) => fmtCurrency(r.k401_conv_wd)],
    ["401k Bal", (r) => fmtCurrency(r.k401_balance)],
    ["Roth Bal", (r) => fmtCurrency(r.roth_balance)],
    ["Net Worth", (r) => fmtCurrency(r.net_worth)],
    ["Spending", (r) => fmtCurrency(r.actual_spending)],
    ["Ord Tax", (r) => fmtCurrency(r.ordinary_tax)],
    ["CG Tax", (r) => fmtCurrency(r.cap_gain_tax)],
    ["NIIT", (r) => fmtCurrency(r.niit_tax)],
    ["Fed Tax", (r) => fmtCurrency(r.total_tax)],
    ["Acc Tax TV", (r) => fmtCurrency(r.acc_tax_tv)],
    ["Audit Diff", (r) => fmtCurrency(r.funding_diff)],
  ],
};

function renderProjectionMatrix() {
  if (!state.simulation) return;
  const cols = PROJECTION_COLUMNS[state.colView] || PROJECTION_COLUMNS.core;
  const table = document.getElementById("projection-table");
  const thead = table.querySelector("thead");
  const tbody = table.querySelector("tbody");

  const hr = document.createElement("tr");
  cols.forEach(([label]) => {
    const th = document.createElement("th");
    th.scope = "col";
    th.textContent = label;
    hr.appendChild(th);
  });
  thead.replaceChildren(hr);
  tbody.replaceChildren();

  const evalAge = state.simulation.summary.eval_age;
  for (const row of state.simulation.projections) {
    const tr = document.createElement("tr");
    if (row.primary_age === evalAge) tr.className = "row-eval-highlight";
    cols.forEach(([, getter], idx) => {
      tr.appendChild(makeCell(idx === 0 ? "th" : "td", getter(row)));
    });
    tbody.appendChild(tr);
  }
}

/* ---------- Strategy Optimizer (6 Orders × DTB) ---------- */
async function executeSweep() {
  if (!validateScenarioForm()) return;
  if (state.optAbort) state.optAbort.abort();
  state.optAbort = new AbortController();

  const btn = document.getElementById("btn-run-sweep");
  const meta = document.getElementById("sweep-meta");
  btn.disabled = true;
  meta.textContent = "Running 3-stage DTB sweep across all 6 withdrawal orders...";

  try {
    const base = readScenarioPayload();
    delete base.dtb_overrides;
    const dtbMax = Number(document.getElementById("sweep_dtb_max").value) || 2000000;
    const res = await runSweep({ ...base, dtb_max: dtbMax }, state.optAbort.signal);
    state.sweep = res;
    renderSweepResults(res);
  } catch (err) {
    if (err.name !== "AbortError") {
      meta.textContent = `Sweep error: ${err.message}`;
    }
  } finally {
    btn.disabled = false;
  }
}

function renderSweepResults(res) {
  document.getElementById("sweep-meta").textContent =
    `Evaluated ${res.total_evaluations} simulations across 6 withdrawal orders in ${res.elapsed_ms.toFixed(0)} ms (${res.mean_ms_per_eval.toFixed(2)} ms/eval). Eval Age: ${res.eval_age}.`;

  const table = document.getElementById("sweep-summary-table");
  applyStackableLabels(table);
  const tbody = table.querySelector("tbody");
  tbody.replaceChildren();

  for (const item of res.summaries) {
    const tr = document.createElement("tr");
    if (item.rank === 1) tr.className = "row-eval-highlight";

    const actionTd = document.createElement("td");
    const applyBtn = document.createElement("button");
    applyBtn.type = "button";
    applyBtn.className = "btn btn-secondary btn-sm";
    applyBtn.textContent = "Apply";
    applyBtn.addEventListener("click", () => {
      document.getElementById("withdraw_order").value = item.withdraw_order;
      document.getElementById("dtb").value = String(item.best_dtb);
      state.dtbOverrides = null;
      updateOverrideBadge();
      document.getElementById("tab-projection").click();
      executeSimulation();
    });
    actionTd.appendChild(applyBtn);

    tr.append(
      makeCell("th", `#${item.rank}`),
      makeCell("td", item.withdraw_order),
      makeCell("td", fmtCurrency(item.best_dtb)),
      makeCell("td", fmtCurrency(item.net_worth_at_eval)),
      makeCell("td", fmtCurrency(item.acc_tax_tv)),
      makeCell("td", fmtCurrency(item.total_roth_converted)),
      actionTd
    );
    tbody.appendChild(tr);
  }

  const orders = Object.keys(res.curves);
  renderLineChart(document.getElementById("chart-sweep-dtb"), {
    xLabel: "Desired Tax Bracket (DTB)",
    yLabel: `Net Worth @ Age ${res.eval_age}`,
    xTickFmt: fmtShortCurrency,
    showPeakStars: true,
    series: orders.map((wo) => ({
      name: wo,
      color: ORDER_COLORS[wo] || "#64748b",
      points: res.curves[wo].map((p) => ({ x: p.dtb, y: p.net_worth })),
    })),
  });

  renderLineChart(document.getElementById("chart-sweep-tax"), {
    xLabel: "Time-Valued Accumulated Tax",
    yLabel: `Net Worth @ Age ${res.eval_age}`,
    xTickFmt: fmtShortCurrency,
    forceZeroY: false,
    scatterSnap: true,
    series: orders.map((wo) => ({
      name: wo,
      color: ORDER_COLORS[wo] || "#64748b",
      points: res.curves[wo].map((p) => ({
        x: p.acc_tax_tv,
        y: p.net_worth,
        meta: `DTB: ${fmtCurrency(p.dtb)}`,
      })),
    })),
  });
}

/* ---------- Per-Year Fine-Tune & Rate Sensitivity ---------- */
async function executePerYearOptimize() {
  if (!validateScenarioForm()) return;
  const btn = document.getElementById("btn-run-peryear");
  const applyBtn = document.getElementById("btn-apply-peryear");
  const meta = document.getElementById("peryear-meta");
  btn.disabled = true;
  applyBtn.disabled = true;
  meta.textContent = "Running per-year coordinate ascent on DTB schedule...";

  try {
    const base = readScenarioPayload();
    const delta = Number(document.getElementById("opt_delta").value) || 50000;
    const step = Number(document.getElementById("opt_step").value) || 5000;
    const res = await runPerYearOptimize({ ...base, delta, step, max_passes: 2 });
    state.perYearResult = res;
    applyBtn.disabled = false;

    const sign = res.net_worth_gain >= 0 ? "+" : "";
    meta.textContent = `Baseline: ${fmtCurrency(res.baseline_net_worth)} -> Optimized: ${fmtCurrency(res.optimized_net_worth)} (${sign}${fmtCurrency(res.net_worth_gain)}) in ${res.total_evaluations} evals (${res.elapsed_ms.toFixed(0)} ms).`;

    const rows = res.optimized_simulation.projections.slice(1, 51);
    renderLineChart(document.getElementById("chart-peryear"), {
      xLabel: "Primary Age",
      yLabel: "DTB / Conversion ($)",
      series: [
        {
          name: "Optimized Yearly DTB",
          color: "var(--series-nw)",
          points: rows.map((r) => ({ x: r.primary_age, y: r.dtb_applied })),
        },
        {
          name: "Roth Converted",
          color: "var(--series-roth)",
          points: rows.map((r) => ({ x: r.primary_age, y: r.roth_conv_deposit })),
        },
        {
          name: "401(k) Remaining",
          color: "var(--series-401k)",
          dash: "4 3",
          points: rows.map((r) => ({ x: r.primary_age, y: r.k401_balance })),
        },
      ],
    });
  } catch (err) {
    meta.textContent = `Optimization error: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
}

async function executeDsbVsRate() {
  if (!validateScenarioForm()) return;
  const btn = document.getElementById("btn-run-dsb-rate");
  const meta = document.getElementById("dsb-rate-meta");
  btn.disabled = true;
  meta.textContent = "Computing max sustainable DSB across 0% - 10% return rates...";

  try {
    const base = readScenarioPayload();
    delete base.dtb_overrides;
    const res = await runDsbVsRate(base);
    meta.textContent = `Completed 21 return-rate levels (${res.total_evaluations} simulations) in ${res.elapsed_ms.toFixed(0)} ms using withdrawal order ${res.withdraw_order}.`;

    renderLineChart(document.getElementById("chart-dsb-rate"), {
      xLabel: "Uniform Return Rate (%)",
      yLabel: "Max Sustainable DSB ($/yr)",
      xTickFmt: (v) => `${v.toFixed(1)}%`,
      series: [
        {
          name: "Max Sustainable DSB",
          color: "var(--series-nw)",
          points: res.points.map((p) => ({
            x: p.return_rate * 100,
            y: p.max_dsb,
          })),
        },
        {
          name: "Optimal DTB",
          color: "var(--series-roth)",
          dash: "5 3",
          points: res.points.map((p) => ({
            x: p.return_rate * 100,
            y: p.optimal_dtb,
          })),
        },
      ],
    });

    const table = document.getElementById("dsb-rate-table");
    applyStackableLabels(table);
    const tbody = table.querySelector("tbody");
    tbody.replaceChildren();
    for (const pt of res.points) {
      const tr = document.createElement("tr");
      tr.append(
        makeCell("th", fmtPct(pt.return_rate, 1)),
        makeCell("td", fmtCurrency(pt.max_dsb)),
        makeCell("td", fmtCurrency(pt.optimal_dtb)),
        makeCell("td", fmtCurrency(pt.net_worth_at_eval))
      );
      tbody.appendChild(tr);
    }
  } catch (err) {
    meta.textContent = `Sensitivity error: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
}

/* ---------- Calculators & Reference Tables ---------- */
function renderKvBox(host, pairs) {
  const grid = document.createElement("div");
  grid.className = "calc-kv-grid";
  for (const [label, val] of pairs) {
    const box = document.createElement("div");
    box.className = "calc-kv";
    const span = document.createElement("span");
    span.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = val;
    box.append(span, strong);
    grid.appendChild(box);
  }
  host.replaceChildren(grid);
}

async function runIncomeTaxCalc(ev) {
  ev?.preventDefault();
  const form = document.getElementById("income-tax-form");
  const mode = form.querySelector('input[name="it_mode"]:checked').value;
  const amount = Number(document.getElementById("it_amount").value);
  const enrolled = Number(document.getElementById("it_enrolled").value);
  const applyStd = document.getElementById("it_std_ded").checked;
  const out = document.getElementById("income-tax-result");

  try {
    const res = await calcIncomeTax({
      mode,
      amount,
      apply_std_deduction: applyStd,
      num_enrolled_medicare: enrolled,
    });
    renderKvBox(out, [
      ["Gross Income", fmtCurrency(res.gross_income)],
      ["Taxable Income", fmtCurrency(res.taxable_income)],
      ["Federal Tax", fmtCurrency(res.federal_tax)],
      ["Income + Tax", fmtCurrency(res.income_plus_tax)],
      ["Effective / Marginal", `${fmtPct(res.effective_rate)} / ${fmtPct(res.marginal_rate, 0)}`],
      ["2026 IRMAA", `Tier ${res.irmaa_tier} (${fmtCurrency(res.irmaa_annual_surcharge)}/yr)`],
    ]);
  } catch (err) {
    out.textContent = err.message;
  }
}

async function runCapGainCalc(ev) {
  ev?.preventDefault();
  const ord = Number(document.getElementById("cg_ord").value);
  const cg = Number(document.getElementById("cg_gain").value);
  const rec = document.getElementById("cg_recursive").checked;
  const dwd = Number(document.getElementById("cg_dwd").value);
  const cgp = Number(document.getElementById("cg_cgp").value);
  const out = document.getElementById("cap-gain-result");

  try {
    const res = await calcCapitalGains({
      ordinary_income: ord,
      capital_gain: cg,
      solve_recursive: rec,
      desired_withdrawal: dwd,
      cgp,
    });
    const pairs = [
      ["Gross Income", fmtCurrency(res.gross_income)],
      ["LTCG Rate", fmtPct(res.cap_gain_tax_rate, 0)],
      ["Capital Gains Tax", fmtCurrency(res.cap_gain_tax)],
      ["3.8% NIIT Tax", fmtCurrency(res.niit_tax)],
      ["Total CG + NIIT", fmtCurrency(res.total_cap_gain_and_niit_tax)],
    ];
    if (res.grossed_up_withdrawal !== null) {
      pairs.push(["Grossed-Up BRKG WD", fmtCurrency(res.grossed_up_withdrawal)]);
    }
    renderKvBox(out, pairs);
  } catch (err) {
    out.textContent = err.message;
  }
}

function renderReferenceTables(cfg) {
  const bTable = document.getElementById("ref-brackets-table");
  applyStackableLabels(bTable);
  const bBody = bTable.querySelector("tbody");
  bBody.replaceChildren();
  for (const b of cfg.ordinary_brackets_mfj) {
    const tr = document.createElement("tr");
    tr.append(
      makeCell("th", fmtPct(b.rate, 0)),
      makeCell("td", fmtCurrency(b.lower)),
      makeCell("td", b.upper ? fmtCurrency(b.upper) : "No Limit"),
      makeCell("td", fmtCurrency(b.base_tax))
    );
    bBody.appendChild(tr);
  }

  const iTable = document.getElementById("ref-irmaa-table");
  applyStackableLabels(iTable);
  const iBody = iTable.querySelector("tbody");
  iBody.replaceChildren();
  for (const tier of cfg.irmaa_brackets_2026) {
    const tr = document.createElement("tr");
    const range = tier.mfj_max
      ? `${fmtCurrency(tier.mfj_min)} - ${fmtCurrency(tier.mfj_max)}`
      : `Over ${fmtCurrency(tier.mfj_min - 1)}`;
    tr.append(
      makeCell("th", `Tier ${tier.tier}`),
      makeCell("td", range),
      makeCell("td", `$${tier.part_b_monthly.toFixed(2)}`),
      makeCell("td", `$${tier.part_d_monthly.toFixed(2)}`)
    );
    iBody.appendChild(tr);
  }

  const hist = cfg.historic_returns;
  const cagr30 = hist.cagr["30y"];
  const cagr10 = hist.cagr["10y"];
  document.getElementById("historic-cagr-summary").textContent =
    `30Y CAGR: S&P 500 ${fmtPct(cagr30.sp500, 2)} | DJIA ${fmtPct(cagr30.djia, 2)} | Nasdaq-100 ${fmtPct(cagr30.nasdaq100, 2)} · 10Y CAGR: ${fmtPct(cagr10.sp500, 2)} / ${fmtPct(cagr10.djia, 2)} / ${fmtPct(cagr10.nasdaq100, 2)}`;

  const hTable = document.getElementById("ref-historic-table");
  applyStackableLabels(hTable);
  const hBody = hTable.querySelector("tbody");
  hBody.replaceChildren();
  for (const r of [...hist.rows].reverse()) {
    const tr = document.createElement("tr");
    tr.append(
      makeCell("th", String(r.year)),
      makeCell("td", fmtPct(r.sp500, 2)),
      makeCell("td", fmtPct(r.djia, 2)),
      makeCell("td", fmtPct(r.nasdaq100, 2))
    );
    hBody.appendChild(tr);
  }
}

/* ---------- Simulation Execution & CSV Export ---------- */
async function executeSimulation() {
  if (!validateScenarioForm()) return;
  if (state.simAbort) state.simAbort.abort();
  state.simAbort = new AbortController();

  const btn = document.getElementById("btn-run-sim");
  const status = document.getElementById("form-status");
  btn.disabled = true;
  status.textContent = "Calculating 80-year projection...";

  try {
    const payload = readScenarioPayload();
    const sim = await runSimulation(payload, state.simAbort.signal);
    renderSimulation(sim, payload.inflation_rate);
    const inflTxt = payload.inflation_rate > 0 ? `, ${(payload.inflation_rate * 100).toFixed(1)}% inflation` : "";
    status.textContent = `Updated projection (${sim.summary.withdraw_order}, Eval @ Age ${sim.summary.eval_age}${inflTxt}).`;
  } catch (err) {
    if (err.name !== "AbortError") {
      status.textContent = `Error: ${err.message}`;
    }
  } finally {
    btn.disabled = false;
  }
}

function exportProjectionCsv() {
  if (!state.simulation) return;
  const cols = [
    "year_index", "year", "primary_age", "secondary_age", "earned_income",
    "dtb_applied", "brkg_cashflow", "brkg_balance", "k401_rmd", "k401_conv_wd",
    "k401_vol_wd", "k401_balance", "roth_conv_deposit", "roth_wd", "roth_balance",
    "net_worth", "actual_spending", "ordinary_income", "ordinary_tax",
    "capital_gains", "cap_gain_tax", "niit_tax", "total_tax", "effective_tax_rate",
    "acc_tax_tv", "irmaa_tier", "irmaa_annual_surcharge",
  ];
  const lines = [cols.join(",")];
  for (const row of state.simulation.projections) {
    lines.push(cols.map((c) => row[c]).join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `roth-projection-${state.simulation.summary.withdraw_order}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/* ---------- Boot ---------- */
async function init() {
  initThemeToggle();
  initTabs();

  const scenarioForm = document.getElementById("scenario-form");
  const dirtyFields = new Set();

  scenarioForm.addEventListener("input", (ev) => {
    const target = ev.target;
    if (target instanceof HTMLInputElement || target instanceof HTMLSelectElement) {
      dirtyFields.add(target);
      clearFieldError(target);
    }
  });

  scenarioForm.addEventListener("focusout", (ev) => {
    const target = ev.target;
    if ((target instanceof HTMLInputElement || target instanceof HTMLSelectElement) && dirtyFields.has(target)) {
      validateInput(target);
    }
  });

  scenarioForm.addEventListener("submit", (ev) => {
    ev.preventDefault();
    executeSimulation();
  });

  document.getElementById("ss_profile").addEventListener("change", syncCustomSsVisibility);

  document.querySelectorAll("[data-preset]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const preset = state.config?.presets?.[btn.dataset.preset];
      if (preset) {
        applyPresetParams(preset.params);
        executeSimulation();
      }
    });
  });

  document.getElementById("btn-quick-sweep").addEventListener("click", () => {
    document.getElementById("tab-optimizer").click();
    executeSweep();
  });

  document.getElementById("btn-run-sweep").addEventListener("click", executeSweep);
  document.getElementById("btn-run-peryear").addEventListener("click", executePerYearOptimize);
  document.getElementById("btn-apply-peryear").addEventListener("click", () => {
    if (!state.perYearResult) return;
    state.dtbOverrides = state.perYearResult.optimized_dtb_by_year;
    updateOverrideBadge();
    document.getElementById("tab-projection").click();
    executeSimulation();
  });

  document.getElementById("btn-clear-overrides").addEventListener("click", () => {
    state.dtbOverrides = null;
    updateOverrideBadge();
    executeSimulation();
  });

  document.getElementById("btn-run-dsb-rate").addEventListener("click", executeDsbVsRate);

  document.querySelectorAll('input[name="col_view"]').forEach((radio) => {
    radio.addEventListener("change", (ev) => {
      state.colView = ev.target.value;
      renderProjectionMatrix();
    });
  });

  document.getElementById("btn-export-csv").addEventListener("click", exportProjectionCsv);

  document.getElementById("income-tax-form").addEventListener("submit", runIncomeTaxCalc);
  document.getElementById("cap-gain-form").addEventListener("submit", runCapGainCalc);
  document.getElementById("cg_recursive").addEventListener("change", (ev) => {
    document.getElementById("cg-rec-fields").hidden = !ev.target.checked;
  });

  try {
    state.config = await fetchConfig();
    applyPresetParams(state.config.presets.model3_default.params);
    renderReferenceTables(state.config);
    await Promise.all([executeSimulation(), runIncomeTaxCalc(), runCapGainCalc()]);
  } catch (err) {
    document.getElementById("form-status").textContent = `Initialization error: ${err.message}`;
  }
}

init();
