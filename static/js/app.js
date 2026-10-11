/* Momentum — small, dependency-free enhancements. Every page works without this file. */
(function () {
  "use strict";
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const root = document.documentElement;

  /* ---------- Theme ---------- */
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)");
  const currentTheme = () => root.getAttribute("data-theme") || (prefersDark.matches ? "dark" : "light");
  function paintThemeButtons() {
    const dark = currentTheme() === "dark";
    $$("[data-theme-toggle]").forEach((btn) => {
      const use = btn.querySelector("use");
      if (use) use.setAttribute("href", dark ? "#i-sun" : "#i-moon");
      const label = btn.querySelector("[data-theme-label]");
      if (label) label.textContent = dark ? "Light" : "Dark";
      btn.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
    });
  }
  $$("[data-theme-toggle]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem("momentum-theme", next); } catch (e) { /* storage blocked: theme lasts this page only */ }
      paintThemeButtons();
      redrawCharts();
    })
  );
  paintThemeButtons();

  /* ---------- Mobile navigation ---------- */
  const navToggle = $("[data-nav-toggle]");
  if (navToggle) {
    const setOpen = (open) => {
      document.body.classList.toggle("nav-open", open);
      navToggle.setAttribute("aria-expanded", String(open));
    };
    navToggle.addEventListener("click", () => setOpen(!document.body.classList.contains("nav-open")));
    document.addEventListener("click", (e) => {
      if (document.body.classList.contains("nav-open") && !e.target.closest(".sidebar") && !e.target.closest("[data-nav-toggle]")) setOpen(false);
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
  }

  /* ---------- Quick-log menu: close on outside click / Escape ---------- */
  $$("details.quicklog").forEach((menu) => {
    document.addEventListener("click", (e) => { if (!menu.contains(e.target)) menu.removeAttribute("open"); });
    menu.addEventListener("keydown", (e) => { if (e.key === "Escape") { menu.removeAttribute("open"); menu.querySelector("summary").focus(); } });
  });

  /* ---------- Toasts ---------- */
  $$(".toast").forEach((toast, i) => {
    const close = () => toast.remove();
    toast.querySelector("[data-dismiss]")?.addEventListener("click", close);
    if (!toast.classList.contains("toast-error")) setTimeout(close, 6000 + i * 800);
  });

  /* ---------- Password fields ---------- */
  $$("[data-pw-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = btn.parentElement.querySelector("input");
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
      btn.style.color = show ? "var(--cobalt)" : "";
    });
  });
  $$("[data-pw-meter]").forEach((meter) => {
    const input = document.getElementById(meter.dataset.pwMeter);
    const hint = meter.parentElement.querySelector("[data-pw-hint]");
    const original = hint ? hint.textContent : "";
    if (!input) return;
    input.addEventListener("input", () => {
      const v = input.value;
      let score = 0;
      if (v.length >= 8) score++;
      if (v.length >= 12) score++;
      if (/[A-Z]/.test(v) && /[a-z]/.test(v)) score++;
      if (/\d/.test(v) && /[^A-Za-z0-9]/.test(v)) score++;
      if (/^\d+$/.test(v)) score = Math.min(score, 1);
      score = v ? Math.max(1, score) : 0;
      meter.dataset.score = score;
      if (hint) hint.textContent = !v ? original : ["", "Weak: add length and variety", "Fair: a little longer would help", "Good", "Strong"][score];
    });
  });

  /* ---------- Exercise formset ---------- */
  $$("[data-formset]").forEach((box) => {
    const prefix = box.dataset.formset;
    const total = box.querySelector(`#id_${prefix}-TOTAL_FORMS`);
    const body = box.querySelector("[data-formset-body]");
    const tpl = box.querySelector("[data-formset-template]");
    const bindRemove = (row) => {
      const btn = row.querySelector("[data-formset-remove]");
      if (!btn) return;
      btn.addEventListener("click", () => {
        const del = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
        const isNew = !row.querySelector('input[name$="-id"]')?.value;
        const name = row.querySelector('input[name$="-name"]');
        if (del) del.checked = true;
        if (isNew && name) name.value = ""; // unchanged extra forms are ignored by Django
        row.classList.add("removed");
      });
    };
    $$("[data-formset-row]", body).forEach(bindRemove);
    box.querySelector("[data-formset-add]")?.addEventListener("click", () => {
      const index = parseInt(total.value, 10);
      const html = tpl.innerHTML.replace(/__prefix__/g, index);
      body.insertAdjacentHTML("beforeend", html);
      total.value = index + 1;
      const row = body.lastElementChild;
      bindRemove(row);
      row.querySelector('input[name$="-name"]')?.focus();
    });
  });

  /* ---------- Food quick-fill ---------- */
  const foodData = $("#food-data");
  if (foodData) {
    const foods = JSON.parse(foodData.textContent);
    const form = $("[data-food-form]");
    const set = (name, value) => { const el = form && form.querySelector(`[name$="${name}"]`); if (el) el.value = value; };
    const fill = (f) => {
      set("name", f[0]); set("quantity", f[1]); set("calories", f[2]);
      set("protein_g", f[3]); set("carbs_g", f[4]); set("fat_g", f[5]);
      form.querySelector('[name$="calories"]')?.focus();
    };
    $$("[data-food]").forEach((btn) => btn.addEventListener("click", () => fill(foods[Number(btn.dataset.food)])));
    const nameInput = form && form.querySelector('[name$="name"]');
    nameInput?.addEventListener("change", () => {
      const match = foods.find((f) => f[0].toLowerCase() === nameInput.value.trim().toLowerCase());
      const kcal = form.querySelector('[name$="calories"]');
      if (match && kcal && !kcal.value) fill(match);
    });
  }

  /* ---------- Charts ---------- */
  const charts = [];
  const css = (name) => getComputedStyle(root).getPropertyValue(name).trim();
  function baseOptions(extra = {}) {
    return Object.assign({
      responsive: true,
      maintainAspectRatio: false,
      animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 500 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: css("--ink-2"), boxWidth: 10, boxHeight: 10, usePointStyle: true, font: { family: "Manrope", weight: 600 } } },
        tooltip: { backgroundColor: css("--ink"), titleColor: css("--paper"), bodyColor: css("--paper"), padding: 10, cornerRadius: 8, titleFont: { family: "Manrope", weight: 700 }, bodyFont: { family: "Manrope" } },
      },
      scales: {
        x: { grid: { display: false }, border: { color: css("--line") }, ticks: { color: css("--muted"), font: { family: "Manrope" }, maxRotation: 0, autoSkipPadding: 12 } },
        y: { grid: { color: css("--line") }, border: { display: false }, ticks: { color: css("--muted"), font: { family: "Manrope" }, maxTicksLimit: 5 } },
      },
    }, extra);
  }
  function emptyNote(canvas, text) {
    const box = canvas.parentElement;
    if (box.querySelector(".chart-empty")) return;
    const note = document.createElement("div");
    note.className = "chart-empty";
    note.textContent = text;
    box.appendChild(note);
  }
  const hasData = (arr) => Array.isArray(arr) && arr.some((v) => v);

  function drawCharts() {
    const dataEl = $("#chart-data");
    if (!dataEl || !window.Chart) return;
    const data = JSON.parse(dataEl.textContent);
    const cobalt = css("--cobalt"), amber = css("--amber"), teal = css("--teal");

    const energy = (id, series) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (!hasData(series.eaten) && !hasData(series.burned)) return emptyNote(el, "Log meals and workouts to see your calorie balance.");
      charts.push(new Chart(el, {
        type: "bar",
        data: { labels: series.labels, datasets: [
          { label: "Eaten", data: series.eaten, backgroundColor: amber, borderRadius: 6, maxBarThickness: 26 },
          { label: "Burned", data: series.burned, backgroundColor: cobalt, borderRadius: 6, maxBarThickness: 26 },
        ] },
        options: baseOptions(),
      }));
    };
    const weight = (id, series) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (!series.values.length) return emptyNote(el, "Log your weight to start a trend line.");
      charts.push(new Chart(el, {
        type: "line",
        data: { labels: series.labels, datasets: [{ label: "Weight (kg)", data: series.values, borderColor: cobalt, backgroundColor: cobalt, tension: 0.3, pointRadius: series.values.length > 40 ? 0 : 3, pointHoverRadius: 5, borderWidth: 2.5 }] },
        options: baseOptions({ plugins: Object.assign(baseOptions().plugins, { legend: { display: false } }) }),
      }));
    };

    if (data.energy) energy("chart-energy", data.energy);
    if (data.weight) weight("chart-weight", data.weight);
    if (document.getElementById("chart-weight-long")) weight("chart-weight-long", data);
    if (document.getElementById("chart-report-energy")) energy("chart-report-energy", data.energy);

    const weekly = document.getElementById("chart-weekly");
    if (weekly && data.weekly) {
      const opts = baseOptions({ plugins: Object.assign(baseOptions().plugins, { legend: { display: false } }) });
      opts.scales.y.display = false;
      opts.scales.x.ticks.font = { family: "Manrope", size: 10 };
      opts.maintainAspectRatio = true;
      charts.push(new Chart(weekly, {
        type: "bar",
        data: { labels: data.weekly.labels, datasets: [{ label: "Minutes", data: data.weekly.values, backgroundColor: data.weekly.values.map((_, i, a) => (i === a.length - 1 ? cobalt : css("--line-strong"))), borderRadius: 4 }] },
        options: opts,
      }));
    }

    const types = document.getElementById("chart-report-types");
    if (types && data.types) {
      const palette = [cobalt, amber, teal, css("--ink-2"), css("--rose"), css("--muted"), css("--line-strong")];
      charts.push(new Chart(types, {
        type: "doughnut",
        data: { labels: data.types.labels, datasets: [{ data: data.types.values, backgroundColor: palette, borderColor: css("--surface"), borderWidth: 3 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "right", labels: { color: css("--ink-2"), usePointStyle: true, boxWidth: 8, font: { family: "Manrope", weight: 600 } } }, tooltip: { callbacks: { label: (c) => ` ${c.label}: ${c.parsed} min` } } } },
      }));
    }

    const targetLine = (value) => ({ label: "Target", data: data.labels.map(() => value), type: "line", borderColor: css("--muted"), borderDash: [5, 5], borderWidth: 1.5, pointRadius: 0, fill: false });
    const steps = document.getElementById("chart-steps");
    if (steps && data.steps) {
      if (!hasData(data.steps)) emptyNote(steps, "No steps logged in the last 2 weeks.");
      else charts.push(new Chart(steps, { type: "bar", data: { labels: data.labels, datasets: [{ label: "Steps", data: data.steps, backgroundColor: data.steps.map((v) => (v >= data.steps_target ? teal : cobalt)), borderRadius: 4 }, targetLine(data.steps_target)] }, options: baseOptions({ plugins: Object.assign(baseOptions().plugins, { legend: { display: false } }) }) }));
    }
    const sleep = document.getElementById("chart-sleep");
    if (sleep && data.sleep) {
      if (!data.sleep.some((v) => v !== null)) emptyNote(sleep, "No sleep logged in the last 2 weeks.");
      else charts.push(new Chart(sleep, { type: "line", data: { labels: data.labels, datasets: [{ label: "Sleep", data: data.sleep, borderColor: cobalt, backgroundColor: cobalt, spanGaps: true, tension: 0.3, pointRadius: 3 }, targetLine(data.sleep_target)] }, options: baseOptions({ plugins: Object.assign(baseOptions().plugins, { legend: { display: false } }) }) }));
    }
  }
  function redrawCharts() {
    while (charts.length) charts.pop().destroy();
    drawCharts();
  }
  drawCharts();
  prefersDark.addEventListener?.("change", () => { if (!root.getAttribute("data-theme")) { paintThemeButtons(); redrawCharts(); } });
})();
