const els = {
  search: document.getElementById("search"),
  sort: document.getElementById("sort"),
  filterAge: document.getElementById("filterAge"),
  patientsGrid: document.getElementById("patientsGrid"),
  patientCountBadge: document.getElementById("patientCountBadge"),
  dataSourceLabel: document.getElementById("dataSourceLabel"),
  addPatientForm: document.getElementById("addPatientForm"),
  addPatientFieldset: document.getElementById("addPatientFieldset"),
  addPatientSubmit: document.getElementById("addPatientSubmit"),
  addPatientMsg: document.getElementById("addPatientMsg"),
  newName: document.getElementById("newName"),
  newAge: document.getElementById("newAge"),
  newGender: document.getElementById("newGender"),
  newMrType: document.getElementById("newMrType"),
  newFinding: document.getElementById("newFinding"),
  newRecentDays: document.getElementById("newRecentDays"),
  newMrImage: document.getElementById("newMrImage"),
  newAccent: document.getElementById("newAccent"),
  mrModal: document.getElementById("mrModal"),
  mrModalTitle: document.getElementById("mrModalTitle"),
  mrModalSubtitle: document.getElementById("mrModalSubtitle"),
  mrImage: document.getElementById("mrImage"),
};

const state = {
  patients: [],
  /** @type {"mongo"|"offline"} */
  source: "offline",
};

function initialsFromName(name) {
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase()).join("");
}

function escapeXml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;");
}

function makeMrSvgDataUri({ name, age, accent }) {
  const safeName = escapeXml(name);
  const safeAge = escapeXml(age);
  const a = accent;

  const svg = `<?xml version="1.0" encoding="UTF-8"?>
  <svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720">
    <defs>
      <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#f7fbff"/>
        <stop offset="60%" stop-color="#ffffff"/>
        <stop offset="100%" stop-color="#f3f6fb"/>
      </linearGradient>
      <radialGradient id="glow" cx="30%" cy="35%" r="65%">
        <stop offset="0%" stop-color="${a}" stop-opacity="0.30"/>
        <stop offset="60%" stop-color="${a}" stop-opacity="0.10"/>
        <stop offset="100%" stop-color="${a}" stop-opacity="0"/>
      </radialGradient>
      <filter id="blur10" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur stdDeviation="10"/>
      </filter>
    </defs>

    <rect width="1200" height="720" fill="url(#bg)"/>
    <rect width="1200" height="720" fill="url(#glow)"/>

    <!-- Grid -->
    <g opacity="0.35" stroke="#0f172a" stroke-opacity="0.12">
      ${Array.from({ length: 16 })
        .map((_, i) => {
          const x = 60 + i * 70;
          return `<line x1="${x}" y1="0" x2="${x}" y2="720"/>`;
        })
        .join("")}
      ${Array.from({ length: 10 })
        .map((_, i) => {
          const y = 40 + i * 70;
          return `<line x1="0" y1="${y}" x2="1200" y2="${y}"/>`;
        })
        .join("")}
    </g>

    <!-- Blob layers -->
    <g filter="url(#blur10)">
      <circle cx="420" cy="300" r="160" fill="${a}" fill-opacity="0.25"/>
      <circle cx="640" cy="390" r="190" fill="${a}" fill-opacity="0.18"/>
      <circle cx="780" cy="270" r="120" fill="${a}" fill-opacity="0.14"/>
      <circle cx="520" cy="470" r="130" fill="${a}" fill-opacity="0.10"/>
    </g>

    <!-- Center "slice" -->
    <g>
      <rect x="260" y="150" width="680" height="420" rx="28" fill="#ffffff" fill-opacity="0.78" stroke="#0f172a" stroke-opacity="0.10"/>
      <g opacity="0.55">
        <path d="M310 540 C 400 430, 460 600, 560 480 S 720 360, 860 470" stroke="${a}" stroke-width="10" fill="none" stroke-linecap="round"/>
        <path d="M320 420 C 430 330, 520 470, 610 400 S 760 340, 870 360" stroke="#0f172a" stroke-opacity="0.16" stroke-width="6" fill="none" stroke-linecap="round"/>
      </g>
    </g>

    <!-- Footer label -->
    <g font-family="Segoe UI, Arial, sans-serif">
      <rect x="70" y="630" width="1060" height="60" rx="18" fill="#ffffff" fill-opacity="0.8" stroke="#0f172a" stroke-opacity="0.10"/>
      <text x="110" y="668" font-size="22" font-weight="800" fill="#0f172a">MR — ${safeName}</text>
      <text x="110" y="695" font-size="16" font-weight="700" fill="#5b6b85">Yaş: ${safeAge}</text>
    </g>
  </svg>`;

  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function getAgeGroup(age) {
  if (age <= 17) return "child";
  if (age <= 64) return "adult";
  return "senior";
}

function formatCount(n) {
  if (n === 1) return "1 hasta";
  return `${n} hasta`;
}

function normalizePatientFromApi(doc) {
  const id = String(doc._id ?? doc.id ?? "");
  const name = doc.name;
  const age = Number(doc.age);
  const accent = doc.accent || "#0078d4";
  const mrStored = doc.mrImage && String(doc.mrImage).trim();
  const mrImage = mrStored ? doc.mrImage : makeMrSvgDataUri({ name, age, accent });
  return {
    id,
    name,
    age,
    gender: doc.gender || "",
    mrType: doc.mrType || "MR",
    finding: doc.finding || "",
    recentDaysAgo: Number(doc.recentDaysAgo ?? 0),
    accent,
    mrImage,
  };
}

function render() {
  const query = (els.search.value || "").trim().toLowerCase();
  const sortBy = els.sort.value;
  const ageFilter = els.filterAge.value;

  let list = [...state.patients];

  if (query) {
    list = list.filter((p) => {
      const inName = p.name.toLowerCase().includes(query);
      const inAge = String(p.age).includes(query);
      return inName || inAge;
    });
  }

  if (ageFilter !== "all") {
    list = list.filter((p) => getAgeGroup(p.age) === ageFilter);
  }

  list.sort((a, b) => {
    if (sortBy === "name") return a.name.localeCompare(b.name, "tr");
    if (sortBy === "age") return b.age - a.age;
    if (sortBy === "recent") return b.recentDaysAgo - a.recentDaysAgo;
    return 0;
  });

  els.patientCountBadge.textContent = formatCount(list.length);
  els.patientsGrid.innerHTML = "";

  if (list.length === 0) {
    const empty = document.createElement("div");
    empty.className = "patient";
    empty.style.gridColumn = "1 / -1";
    const noFilters = !query && ageFilter === "all";
    const offlineEmpty = state.source === "offline" && noFilters;
    const emptyDb = state.source === "mongo" && state.patients.length === 0 && noFilters;
    let title = "Sonuç bulunamadı";
    let sub = "Arama veya filtreleri değiştirin.";
    if (offlineEmpty) {
      title = "Bağlantı yok";
      sub = "";
    } else if (emptyDb) {
      title = "Henüz hasta kaydı yok";
      sub = "";
    }
    const subHtml = sub
      ? `<div class="patient__small">${sub}</div>`
      : "";
    empty.innerHTML = `
      <div class="patient__meta" style="margin-top: 6px;">
        <div class="patient__name">${title}</div>
        ${subHtml}
      </div>
    `;
    els.patientsGrid.appendChild(empty);
    return;
  }

  for (const p of list) {
    const card = document.createElement("article");
    card.className = "patient";
    card.setAttribute("data-patient-id", p.id);
    card.innerHTML = `
      <div class="patient__top">
        <div class="patient__id" style="background: rgba(0,120,212,.10); border-color: rgba(0,120,212,.25);">${initialsFromName(p.name)}</div>
        <div class="patient__meta">
          <div class="patient__name">${p.name}</div>
          <div class="patient__small">
            <span>${p.age} yaş</span>
            <span>${p.gender}</span>
          </div>
        </div>
        <div class="tag" title="MR tipi">
          <span class="tag__dot" aria-hidden="true"></span>
          ${p.mrType}
        </div>
      </div>

      <div class="patient__body">
        <div class="kv">
          <div class="kv__k">Son inceleme</div>
          <div class="kv__v">${p.recentDaysAgo} gün önce</div>
        </div>
        <div class="kv">
          <div class="kv__k">Bulgular</div>
          <div class="kv__v">${p.finding}</div>
        </div>
      </div>

      <div class="patient__actions">
        <button class="btn btn--primary" type="button" data-action="open-mr">
          MR görüntüle
        </button>
      </div>
    `;

    const btn = card.querySelector('[data-action="open-mr"]');
    btn.addEventListener("click", () => openMr(p));

    els.patientsGrid.appendChild(card);
  }
}

function openMr(patient) {
  els.mrModal.classList.add("modal--open");
  els.mrModal.setAttribute("aria-hidden", "false");

  els.mrModalTitle.textContent = "MR Görüntüsü";
  els.mrModalSubtitle.textContent = `${patient.name} • ${patient.age} yaş • ${patient.mrType}`;
  els.mrImage.src = patient.mrImage;
  els.mrImage.alt = `MR görüntüsü — ${patient.name}`;

  const closeBtn = els.mrModal.querySelector('[data-close="true"]');
  closeBtn?.focus?.();
}

function closeMr() {
  els.mrModal.classList.remove("modal--open");
  els.mrModal.setAttribute("aria-hidden", "true");
  els.mrImage.src = "";
}

function wireEvents() {
  els.search.addEventListener("input", render);
  els.sort.addEventListener("change", render);
  els.filterAge.addEventListener("change", render);

  els.mrModal.addEventListener("click", (e) => {
    const target = e.target;
    const closeEl =
      target instanceof HTMLElement
        ? target.closest('[data-close="true"]')
        : null;

    if (closeEl) {
      closeMr();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && els.mrModal.classList.contains("modal--open")) {
      closeMr();
    }
  });

  els.addPatientForm?.addEventListener("submit", submitNewPatient);
}

async function loadPatientsFromApi() {
  const r = await fetch("/api/patients");
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const data = await r.json();
  if (!Array.isArray(data)) throw new Error("Geçersiz yanıt");
  state.patients = data.map(normalizePatientFromApi);
  state.source = "mongo";
  if (els.dataSourceLabel) els.dataSourceLabel.textContent = "MongoDB";
}

function setAddPatientFormEnabled(enabled) {
  if (els.addPatientFieldset) els.addPatientFieldset.disabled = !enabled;
}

function setAddPatientMessage(text, kind) {
  if (!els.addPatientMsg) return;
  els.addPatientMsg.textContent = text;
  els.addPatientMsg.className =
    kind === "ok" ? "form-msg form-msg--ok" : kind === "err" ? "form-msg form-msg--err" : "form-msg";
}

async function submitNewPatient(ev) {
  ev.preventDefault();
  if (state.source !== "mongo") {
    setAddPatientMessage("Bağlantı yok.", "err");
    return;
  }

  const name = (els.newName?.value || "").trim();
  const age = Number(els.newAge?.value);
  if (!name || !Number.isFinite(age) || age < 0) {
    setAddPatientMessage("Ad ve geçerli bir yaş girin.", "err");
    return;
  }

  const payload = {
    name,
    age,
    gender: (els.newGender?.value || "").trim(),
    mrType: (els.newMrType?.value || "").trim(),
    finding: (els.newFinding?.value || "").trim(),
    recentDaysAgo: Number(els.newRecentDays?.value) || 0,
    mrImage: (els.newMrImage?.value || "").trim(),
    accent: (els.newAccent?.value || "").trim() || "#0078d4",
  };

  if (els.addPatientSubmit) els.addPatientSubmit.disabled = true;
  setAddPatientMessage("Kaydediliyor…", "");

  try {
    const r = await fetch("/api/patients", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) {
      throw new Error(body.error || `HTTP ${r.status}`);
    }
    await loadPatientsFromApi();
    render();
    els.addPatientForm?.reset();
    if (els.newAccent) els.newAccent.value = "#0078d4";
    setAddPatientMessage("Hasta kaydedildi.", "ok");
  } catch (e) {
    setAddPatientMessage(e.message || "Kayıt başarısız.", "err");
  } finally {
    if (els.addPatientSubmit) els.addPatientSubmit.disabled = false;
  }
}

async function init() {
  wireEvents();
  if (els.dataSourceLabel) els.dataSourceLabel.textContent = "Bağlanıyor…";
  try {
    await loadPatientsFromApi();
    setAddPatientFormEnabled(true);
    if (els.addPatientMsg) {
      els.addPatientMsg.textContent = "";
      els.addPatientMsg.className = "form-msg";
    }
  } catch {
    state.patients = [];
    state.source = "offline";
    if (els.dataSourceLabel) els.dataSourceLabel.textContent = "Bağlantı yok";
    setAddPatientFormEnabled(false);
    if (els.addPatientMsg) {
      els.addPatientMsg.textContent = "";
      els.addPatientMsg.className = "form-msg";
    }
  }
  render();
}

init();

