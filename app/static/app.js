const state = { assets: [], selected: null, user: null };

function authHeaders() {
  const token = localStorage.getItem("gs_token");
  if (!token) {
    location.href = "/login";
    throw new Error("Not authenticated");
  }
  return { Authorization: `Bearer ${token}` };
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}), ...authHeaders() };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    localStorage.removeItem("gs_token");
    location.href = "/login";
    throw new Error("Session expired");
  }
  if (!res.ok) {
    let detail = await res.text();
    try { detail = JSON.parse(detail).detail || detail; } catch (_) {}
    throw new Error(detail || res.statusText);
  }
  if (res.status === 204) return null;
  return res.json();
}

function bandClass(band) {
  return `band ${band || "Low"}`;
}

function renderKpis(summary) {
  const t = summary.totals || {};
  const cards = [
    ["Assets", t.assets ?? 0],
    ["DTRs", t.dtrs ?? 0],
    ["Feeders", t.feeders ?? 0],
    ["Critical + High", (t.critical_n || 0) + (t.high_n || 0)],
    ["Avg risk", t.avg_risk ?? "—"],
  ];
  document.getElementById("kpis").innerHTML = cards
    .map(([label, value]) => `<article class="kpi"><span>${label}</span><strong>${value}</strong></article>`)
    .join("");

  const m = summary.model || {};
  const auc = m.roc_auc != null ? Number(m.roc_auc).toFixed(3) : "n/a";
  document.getElementById("modelMeta").textContent =
    `${summary.organization || "Organization"} · model ${m.version || "—"} · ROC-AUC ${auc} · ${m.n_assets || 0} training assets`;

  document.getElementById("circleGrid").innerHTML = (summary.by_circle || [])
    .map(
      (c) => `
      <article class="circle-card">
        <strong>${c.circle}</strong>
        <span>${c.assets} assets · ${c.at_risk || 0} at risk · avg ${c.avg_risk ?? "—"}</span>
      </article>`
    )
    .join("");
}

function renderTable(assets) {
  const body = document.getElementById("assetTable");
  body.innerHTML = assets
    .map((a) => {
      const active = state.selected === a.equipment_id ? "active" : "";
      return `
      <tr class="${active}" data-id="${a.equipment_id}">
        <td>
          <div>${a.equipment_id}</div>
          <div style="color:var(--muted);font-size:0.78rem">${a.name || ""}</div>
        </td>
        <td>${a.circle || ""}</td>
        <td>${a.asset_type || ""}</td>
        <td class="mono">${a.risk_score != null ? Number(a.risk_score).toFixed(2) : "—"}</td>
        <td><span class="${bandClass(a.risk_band)}">${a.risk_band || "—"}</span></td>
      </tr>`;
    })
    .join("");
  body.querySelectorAll("tr").forEach((row) => {
    row.addEventListener("click", () => selectAsset(row.dataset.id));
  });
}

function sparkline(readings) {
  if (!readings.length) return "<p class='placeholder'>No load readings.</p>";
  const values = readings.map((r) => Number(r.load_kw) / Math.max(Number(r.rated_kw), 1));
  const w = 320;
  const h = 110;
  const max = Math.max(1.2, ...values);
  const step = w / Math.max(values.length - 1, 1);
  const points = values
    .map((v, i) => `${i * step},${h - (v / max) * (h - 10) - 5}`)
    .join(" ");
  const thresholdY = h - (1 / max) * (h - 10) - 5;
  return `
    <svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Load factor trend">
      <line x1="0" y1="${thresholdY}" x2="${w}" y2="${thresholdY}" stroke="#e2a93b55" stroke-dasharray="4 4" />
      <polyline fill="none" stroke="#3dba84" stroke-width="2.2" points="${points}" />
    </svg>
    <p class="meta" style="text-align:left">Load factor (last ${readings.length} days). Dashed line = rated capacity.</p>`;
}

async function selectAsset(id) {
  state.selected = id;
  renderTable(state.assets);
  const data = await api(`/api/v1/assets/${encodeURIComponent(id)}`);
  const a = data.asset;
  const drivers = (a.top_drivers || [])
    .map(
      (d) => `
      <div class="driver">
        <span>${d.feature.replaceAll("_", " ")}</span>
        <strong class="mono">${d.value}</strong>
      </div>`
    )
    .join("");
  const notifs = (data.notifications || [])
    .slice(0, 5)
    .map((n) => `<li>${n.created_on} · ${n.notification_type} · ${n.damage_code || n.short_text}</li>`)
    .join("") || "<li>No recent notifications</li>";
  const orders = (data.work_orders || [])
    .slice(0, 5)
    .map((o) => `<li>${o.created_on} · ${o.order_type} · ₹${Number(o.cost_inr || 0).toLocaleString("en-IN")}</li>`)
    .join("") || "<li>No recent work orders</li>";

  document.getElementById("detail").innerHTML = `
    <h3>${a.equipment_id}</h3>
    <p class="sub">${a.name} · ${a.circle} · ${a.division}<br>${a.functional_location}</p>
    <p><span class="${bandClass(a.risk_band)}">${a.risk_band || "—"}</span>
       <strong class="mono" style="margin-left:0.6rem">${Number(a.risk_score || 0).toFixed(2)}</strong>
       risk · model ${a.model_version || "—"}</p>
    <div class="action"><strong>Recommended intervention</strong><br>${a.recommended_action || "—"}</div>
    <h2 style="font-size:1.05rem;margin-bottom:0.4rem">Top risk drivers</h2>
    <div class="drivers">${drivers || "<p class='placeholder'>No drivers</p>"}</div>
    <h2 style="font-size:1.05rem;margin-bottom:0.2rem">Loading pattern</h2>
    ${sparkline(data.load_readings || [])}
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.8rem">
      <div>
        <h2 style="font-size:1.05rem">SAP PM notifications</h2>
        <ul class="mini-list">${notifs}</ul>
      </div>
      <div>
        <h2 style="font-size:1.05rem">Work orders</h2>
        <ul class="mini-list">${orders}</ul>
      </div>
    </div>`;
}

async function loadAssets() {
  const params = new URLSearchParams();
  const type = document.getElementById("typeFilter").value;
  const band = document.getElementById("bandFilter").value;
  const q = document.getElementById("search").value.trim();
  if (type) params.set("asset_type", type);
  if (band) params.set("band", band);
  if (q) params.set("q", q);
  params.set("page_size", "120");
  const data = await api(`/api/v1/assets?${params}`);
  state.assets = data.items || [];
  renderTable(state.assets);
  if (!state.selected && state.assets.length) {
    await selectAsset(state.assets[0].equipment_id);
  } else if (state.selected) {
    const still = state.assets.find((a) => a.equipment_id === state.selected);
    if (still) await selectAsset(state.selected);
  }
}

function applyRoleGates() {
  const role = state.user?.role;
  const canOps = role === "admin" || role === "analyst";
  document.getElementById("retrainBtn").hidden = !canOps;
  document.getElementById("seedBtn").hidden = !canOps;
}

async function boot() {
  if (!localStorage.getItem("gs_token")) {
    location.href = "/login";
    return;
  }
  const stored = localStorage.getItem("gs_user");
  state.user = stored ? JSON.parse(stored) : await api("/api/v1/auth/me");
  document.getElementById("userChip").textContent =
    `${state.user.full_name} · ${state.user.role} · ${state.user.organization || ""}`;
  applyRoleGates();
  const summary = await api("/api/v1/assets/summary");
  renderKpis(summary);
  await loadAssets();
}

document.getElementById("typeFilter").addEventListener("change", loadAssets);
document.getElementById("bandFilter").addEventListener("change", loadAssets);
document.getElementById("search").addEventListener("input", () => {
  clearTimeout(window.__searchTimer);
  window.__searchTimer = setTimeout(loadAssets, 220);
});

document.getElementById("logoutBtn").addEventListener("click", () => {
  localStorage.removeItem("gs_token");
  localStorage.removeItem("gs_user");
  location.href = "/login";
});

document.getElementById("retrainBtn").addEventListener("click", async () => {
  const btn = document.getElementById("retrainBtn");
  btn.disabled = true;
  btn.textContent = "Training…";
  try {
    await api("/api/v1/ops/retrain", { method: "POST" });
    await boot();
  } catch (err) {
    alert(err.message || String(err));
  } finally {
    btn.disabled = false;
    btn.textContent = "Retrain & rescore";
  }
});

document.getElementById("seedBtn").addEventListener("click", async () => {
  const btn = document.getElementById("seedBtn");
  btn.disabled = true;
  btn.textContent = "Seeding…";
  try {
    await api("/api/v1/ops/seed", { method: "POST" });
    await boot();
  } catch (err) {
    alert(err.message || String(err));
  } finally {
    btn.disabled = false;
    btn.textContent = "Load demo fleet";
  }
});

boot().catch((err) => {
  console.error(err);
  document.getElementById("kpis").innerHTML =
    `<article class="kpi"><span>Error</span><strong style="font-size:1rem">${err.message || err}</strong></article>`;
});
