// custom_components/travaux_besancon/lovelace/travaux-besancon-card.js
// Carte Lovelace Travaux Besançon — fil des arrêtés de voirie sur les zones suivies.
// Deux modes : « flux » (liste détaillée) et « compact » (compteur + dernières alertes).

const TB_VERSION = "1.1.0";

const COLORS = {
  primary:       "#e67e22",
  circulation:   "#fd7e14",
  stationnement: "#1e88e5",
  circulation_stationnement: "#8e24aa",
  autre:         "#9e9e9e",
  ok:            "#55b73e",
};

const TYPE_LABELS = {
  circulation:   "Circulation",
  stationnement: "Stationnement",
  circulation_stationnement: "Circulation + stationnement",
  autre:         "Voirie",
};

const TYPE_ICONS = {
  circulation:   "mdi:traffic-cone",
  stationnement: "mdi:car-off",
  circulation_stationnement: "mdi:sign-caution",
  autre:         "mdi:road-variant",
};

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function titreCase(str) {
  return String(str ?? "").toLowerCase().replace(
    /(^|[\s\-'])([a-zà-ü])/g,
    (_, sep, c) => sep + c.toUpperCase(),
  );
}

function dateFr(iso) {
  if (!iso) return "";
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}

function estRecent(iso, jours) {
  if (!iso) return false;
  const age = Date.now() - new Date(`${iso}T00:00:00`).getTime();
  return age >= 0 && age < jours * 86400000;
}

function fireMoreInfo(el, entityId) {
  if (!entityId) return;
  el.dispatchEvent(new CustomEvent("hass-more-info", {
    detail: { entityId }, bubbles: true, composed: true,
  }));
}

// ════════════════════════════════════════════════════════════════
//  Carte
// ════════════════════════════════════════════════════════════════

class TravauxBesanconCard extends HTMLElement {
  static getConfigElement() {
    return document.createElement("travaux-besancon-card-editor");
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass?.states || {}).find(
      (id) => id.startsWith("sensor.") &&
        hass.states[id]?.attributes?.integration === "travaux_besancon",
    );
    return { mode: "flux", entity: entity || "sensor.travaux_besancon" };
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Définissez « entity » (capteur Travaux Besançon).");
    this._config = {
      mode: "flux",
      max_items: 10,
      group_by: "none",
      show_pdf: true,
      show_quartiers: true,
      jours_nouveau: 3,
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return this._config?.mode === "compact" ? 2 : 4;
  }

  // ------------------------------------------------------------------

  _arretes() {
    const st = this._hass?.states?.[this._config.entity];
    if (!st) return null;
    return {
      etat: st.state,
      arretes: st.attributes?.arretes || [],
      maj: st.last_updated,
    };
  }

  _render() {
    if (!this._config || !this._hass) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });

    const data = this._arretes();
    let corps;
    if (!data) {
      corps = `<div class="tb-vide">
        <ha-icon icon="mdi:alert-circle-outline"></ha-icon>
        <div>Entité introuvable : <code>${esc(this._config.entity)}</code></div>
      </div>`;
    } else if (this._config.mode === "compact") {
      corps = this._renderCompact(data);
    } else {
      corps = this._renderFlux(data);
    }

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <ha-card>${corps}</ha-card>
    `;

    const header = this.shadowRoot.querySelector(".tb-header");
    if (header) {
      header.addEventListener("click", () => fireMoreInfo(this, this._config.entity));
    }
  }

  _renderHeader(data, compact = false) {
    const n = data.arretes.length;
    const titre = this._config.title ||
      (compact ? "Travaux" : "Travaux & arrêtés — Besançon");
    const chipColor = n > 0 ? COLORS.primary : COLORS.ok;
    return `
      <div class="tb-header">
        <ha-icon class="tb-header-ico" icon="mdi:traffic-cone"></ha-icon>
        <div class="tb-header-titre">${esc(titre)}</div>
        <div class="tb-chip" style="background:${chipColor}">${n}</div>
      </div>`;
  }

  _renderRow(a) {
    const cfg   = this._config;
    const type  = a.type || "autre";
    const color = COLORS[type] || COLORS.autre;
    const rues  = (a.rues || []).map(titreCase).join(", ") || esc(a.titre);
    const quartiers = cfg.show_quartiers && (a.quartiers || []).length
      ? ` · ${a.quartiers.map(titreCase).join(", ")}`
      : "";
    const nouveau = estRecent(a.date_publication, cfg.jours_nouveau)
      ? `<span class="tb-nouveau">nouveau</span>` : "";
    const pdf = cfg.show_pdf && a.url_pdf
      ? `<a class="tb-pdf" href="${esc(a.url_pdf)}" target="_blank" rel="noopener"
           title="Ouvrir l'arrêté (PDF)"><ha-icon icon="mdi:file-pdf-box"></ha-icon></a>`
      : "";

    // Résumé extrait du PDF (motif, période réelle du chantier, horaires)
    const res = a.resume || {};
    const morceaux = [];
    if (res.motif) morceaux.push(res.motif.charAt(0).toUpperCase() + res.motif.slice(1));
    if (res.date_debut && res.date_fin) {
      morceaux.push(res.date_debut === res.date_fin
        ? `le ${dateFr(res.date_debut)}`
        : `du ${dateFr(res.date_debut)} au ${dateFr(res.date_fin)}`);
    }
    if (res.horaires?.length) morceaux.push(res.horaires.join(", "));
    const resume = morceaux.length
      ? `<div class="tb-resume">${esc(morceaux.join(" · "))}</div>` : "";

    return `
      <div class="tb-row">
        <div class="tb-badge" style="background:${color}1a;color:${color}">
          <ha-icon icon="${TYPE_ICONS[type]}"></ha-icon>
        </div>
        <div class="tb-corps">
          <div class="tb-rues">${esc(rues)} ${nouveau}</div>
          <div class="tb-meta">
            <span style="color:${color}">${TYPE_LABELS[type]}</span>
            · ${dateFr(a.date_publication)}${esc(quartiers)}
          </div>
          ${resume}
        </div>
        ${pdf}
      </div>`;
  }

  _renderVide() {
    return `<div class="tb-vide">
      <ha-icon icon="mdi:check-circle-outline" style="color:${COLORS.ok}"></ha-icon>
      <div>Aucun arrêté en cours sur vos zones</div>
    </div>`;
  }

  _renderFlux(data) {
    const cfg = this._config;
    const arretes = data.arretes.slice(0, cfg.max_items);

    let liste;
    if (!arretes.length) {
      liste = this._renderVide();
    } else if (cfg.group_by === "rue" || cfg.group_by === "quartier") {
      const cle = cfg.group_by === "rue" ? "rues" : "quartiers";
      const groupes = new Map();
      for (const a of arretes) {
        const noms = (a[cle] || []).length ? a[cle] : ["Autres"];
        for (const nom of noms) {
          if (!groupes.has(nom)) groupes.set(nom, []);
          groupes.get(nom).push(a);
        }
      }
      liste = [...groupes.entries()]
        .sort((x, y) => x[0].localeCompare(y[0], "fr"))
        .map(([nom, items]) => `
          <div class="tb-groupe">${esc(titreCase(nom))}</div>
          ${items.map((a) => this._renderRow(a)).join("")}
        `).join("");
    } else {
      liste = arretes.map((a) => this._renderRow(a)).join("");
    }

    const reste = data.arretes.length - arretes.length;
    const pied = reste > 0
      ? `<div class="tb-pied">+ ${reste} autre${reste > 1 ? "s" : ""} arrêté${reste > 1 ? "s" : ""}</div>`
      : "";

    return `${this._renderHeader(data)}<div class="tb-liste">${liste}</div>${pied}`;
  }

  _renderCompact(data) {
    const derniers = data.arretes.slice(0, 3);
    const lignes = derniers.length
      ? derniers.map((a) => {
          const type  = a.type || "autre";
          const color = COLORS[type] || COLORS.autre;
          const rues  = (a.rues || []).map(titreCase).join(", ") || esc(a.titre);
          return `<div class="tb-mini">
            <span class="tb-mini-dot" style="background:${color}"></span>
            <span class="tb-mini-rue">${esc(rues)}</span>
            <span class="tb-mini-date">${dateFr(a.date_publication)}</span>
          </div>`;
        }).join("")
      : `<div class="tb-mini tb-mini-ok">
           <ha-icon icon="mdi:check-circle-outline"></ha-icon> Rien à signaler
         </div>`;

    return `${this._renderHeader(data, true)}<div class="tb-liste tb-liste-compacte">${lignes}</div>`;
  }

  _styles() {
    return `
      :host { display: block; }
      ha-card { padding: 12px 16px 14px; }

      .tb-header {
        display: flex; align-items: center; gap: 10px;
        cursor: pointer; padding: 4px 0 10px;
      }
      .tb-header-ico { color: ${COLORS.primary}; }
      .tb-header-titre {
        flex: 1; font-size: 16px; font-weight: 600;
        color: var(--primary-text-color);
      }
      .tb-chip {
        min-width: 26px; height: 26px; border-radius: 13px;
        display: flex; align-items: center; justify-content: center;
        color: #fff; font-size: 13px; font-weight: 700; padding: 0 8px;
      }

      .tb-liste { display: flex; flex-direction: column; }
      .tb-row {
        display: flex; align-items: center; gap: 12px;
        padding: 8px 0;
        border-top: 1px solid var(--divider-color, rgba(127,127,127,.2));
      }
      .tb-badge {
        width: 36px; height: 36px; border-radius: 10px; flex-shrink: 0;
        display: flex; align-items: center; justify-content: center;
      }
      .tb-badge ha-icon { --mdc-icon-size: 20px; }
      .tb-corps { flex: 1; min-width: 0; }
      .tb-rues {
        font-size: 14px; font-weight: 500; color: var(--primary-text-color);
        overflow: hidden; text-overflow: ellipsis;
      }
      .tb-meta {
        font-size: 12px; color: var(--secondary-text-color); margin-top: 2px;
      }
      .tb-resume {
        font-size: 12px; color: var(--secondary-text-color); margin-top: 2px;
        font-style: italic; overflow: hidden; text-overflow: ellipsis;
      }
      .tb-nouveau {
        display: inline-block; margin-left: 6px; padding: 1px 7px;
        border-radius: 9px; font-size: 10px; font-weight: 700;
        text-transform: uppercase; letter-spacing: .05em;
        background: ${COLORS.primary}; color: #fff; vertical-align: middle;
      }
      .tb-pdf {
        color: var(--secondary-text-color); flex-shrink: 0;
        transition: color .15s;
      }
      .tb-pdf:hover { color: ${COLORS.circulation}; }

      .tb-groupe {
        font-size: 11px; font-weight: 700; text-transform: uppercase;
        letter-spacing: .06em; color: var(--secondary-text-color);
        padding: 10px 0 2px;
      }
      .tb-pied {
        font-size: 12px; color: var(--secondary-text-color);
        padding-top: 8px; text-align: center;
      }
      .tb-vide {
        display: flex; flex-direction: column; align-items: center; gap: 8px;
        padding: 22px 0 14px; color: var(--secondary-text-color); font-size: 13px;
      }
      .tb-vide ha-icon { --mdc-icon-size: 34px; }
      code { font-size: 12px; }

      .tb-liste-compacte { gap: 4px; }
      .tb-mini {
        display: flex; align-items: center; gap: 8px;
        font-size: 13px; color: var(--primary-text-color);
      }
      .tb-mini-dot {
        width: 8px; height: 8px; border-radius: 4px; flex-shrink: 0;
      }
      .tb-mini-rue { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .tb-mini-date { color: var(--secondary-text-color); font-size: 12px; }
      .tb-mini-ok { color: ${COLORS.ok}; }
      .tb-mini-ok ha-icon { --mdc-icon-size: 18px; }
    `;
  }
}

// ════════════════════════════════════════════════════════════════
//  Éditeur visuel
// ════════════════════════════════════════════════════════════════

class TravauxBesanconCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot) this._render();
  }

  _entites() {
    return Object.keys(this._hass?.states || {}).filter(
      (id) => id.startsWith("sensor.") &&
        this._hass.states[id]?.attributes?.integration === "travaux_besancon",
    );
  }

  _render() {
    if (!this._config) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });

    const cfg = this._config;
    const entites = this._entites();
    const optEntites = (entites.length ? entites : [cfg.entity || ""])
      .map((id) => `<option value="${esc(id)}" ${id === cfg.entity ? "selected" : ""}>${esc(id)}</option>`)
      .join("");

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <div class="tb-editor">
        <div class="tb-field">
          <label>Entité</label>
          <select id="entity">${optEntites}</select>
        </div>
        <div class="tb-field">
          <label>Mode</label>
          <select id="mode">
            <option value="flux" ${cfg.mode !== "compact" ? "selected" : ""}>Flux (liste détaillée)</option>
            <option value="compact" ${cfg.mode === "compact" ? "selected" : ""}>Compact</option>
          </select>
        </div>
        <div class="tb-field">
          <label>Titre <span class="tb-opt">(optionnel)</span></label>
          <input type="text" id="title" value="${esc(cfg.title || "")}" placeholder="Travaux &amp; arrêtés — Besançon">
        </div>
        <div class="tb-field">
          <label>Regrouper par</label>
          <select id="group_by">
            <option value="none" ${!cfg.group_by || cfg.group_by === "none" ? "selected" : ""}>—</option>
            <option value="rue" ${cfg.group_by === "rue" ? "selected" : ""}>Rue</option>
            <option value="quartier" ${cfg.group_by === "quartier" ? "selected" : ""}>Quartier</option>
          </select>
        </div>
        <div class="tb-field">
          <label>Nombre maximum d'arrêtés affichés</label>
          <input type="number" id="max_items" min="1" max="50" value="${cfg.max_items ?? 10}">
        </div>
        <div class="tb-toggles">
          <label class="tb-toggle"><input type="checkbox" id="show_pdf" ${cfg.show_pdf !== false ? "checked" : ""}> Lien vers le PDF de l'arrêté</label>
          <label class="tb-toggle"><input type="checkbox" id="show_quartiers" ${cfg.show_quartiers !== false ? "checked" : ""}> Afficher les quartiers</label>
        </div>
        <div class="tb-section">Aperçu YAML</div>
        <pre id="yaml-preview">${esc(this._yaml())}</pre>
      </div>
    `;

    for (const id of ["entity", "mode", "title", "group_by", "max_items", "show_pdf", "show_quartiers"]) {
      const el = this.shadowRoot.getElementById(id);
      el.addEventListener("change", () => this._majConfig());
      if (el.type === "text" || el.type === "number") {
        el.addEventListener("input", () => this._majConfig());
      }
    }
  }

  _majConfig() {
    const get = (id) => this.shadowRoot.getElementById(id);
    const cfg = {
      type: "custom:travaux-besancon-card",
      entity: get("entity").value,
      mode: get("mode").value,
    };
    if (get("title").value) cfg.title = get("title").value;
    if (get("group_by").value !== "none") cfg.group_by = get("group_by").value;
    const max = parseInt(get("max_items").value, 10);
    if (!Number.isNaN(max) && max !== 10) cfg.max_items = max;
    if (!get("show_pdf").checked) cfg.show_pdf = false;
    if (!get("show_quartiers").checked) cfg.show_quartiers = false;

    this._config = cfg;
    const pre = this.shadowRoot.getElementById("yaml-preview");
    if (pre) pre.textContent = this._yaml();
    this.dispatchEvent(new CustomEvent("config-changed", {
      detail: { config: cfg }, bubbles: true, composed: true,
    }));
  }

  _yaml() {
    const cfg = this._config;
    const lines = [
      "type: custom:travaux-besancon-card",
      `entity: ${cfg.entity || "sensor.travaux_besancon"}`,
      `mode: ${cfg.mode || "flux"}`,
    ];
    if (cfg.title) lines.push(`title: ${cfg.title}`);
    if (cfg.group_by && cfg.group_by !== "none") lines.push(`group_by: ${cfg.group_by}`);
    if (cfg.max_items !== undefined && cfg.max_items !== 10) lines.push(`max_items: ${cfg.max_items}`);
    if (cfg.show_pdf === false) lines.push("show_pdf: false");
    if (cfg.show_quartiers === false) lines.push("show_quartiers: false");
    return lines.join("\n");
  }

  _styles() {
    return `
      :host { display: block; }
      .tb-editor {
        padding: 16px 0;
        font-family: var(--paper-font-body1_-_font-family, sans-serif);
        font-size: 14px; color: var(--primary-text-color);
      }
      .tb-field { margin-bottom: 14px; }
      label {
        display: block; font-size: 12px; font-weight: 500;
        color: var(--secondary-text-color); margin-bottom: 5px;
        text-transform: uppercase; letter-spacing: .04em;
      }
      .tb-opt { text-transform: none; font-weight: 400; }
      select, input[type="text"], input[type="number"] {
        width: 100%; box-sizing: border-box; padding: 8px 10px;
        border-radius: 6px;
        border: 1px solid var(--divider-color, rgba(255,255,255,.2));
        background: var(--secondary-background-color, #2c2c2e);
        color: var(--primary-text-color, #e5e5ea);
        font-size: 14px; outline: none; transition: border-color .15s;
      }
      select:focus, input:focus { border-color: ${COLORS.primary}; }
      input[type="number"] { width: 70px; }
      .tb-toggles { display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px; }
      .tb-toggle {
        display: flex; align-items: center; gap: 8px; cursor: pointer;
        font-size: 13px; text-transform: none; letter-spacing: 0;
        color: var(--primary-text-color); font-weight: 400;
      }
      .tb-toggle input { width: auto; cursor: pointer; }
      .tb-section {
        font-size: 11px; font-weight: 600; color: var(--disabled-text-color);
        text-transform: uppercase; letter-spacing: .06em;
        border-top: 1px solid var(--divider-color, rgba(255,255,255,.1));
        padding-top: 14px; margin: 18px 0 10px;
      }
      pre {
        font-family: var(--code-font-family, monospace); font-size: 11px;
        color: var(--secondary-text-color); line-height: 1.8;
        background: var(--secondary-background-color, rgba(255,255,255,.05));
        padding: 10px 12px; border-radius: 8px; overflow-x: auto; margin: 0; white-space: pre;
      }
    `;
  }
}

// ════════════════════════════════════════════════════════════════
//  Enregistrement
// ════════════════════════════════════════════════════════════════

customElements.define("travaux-besancon-card",        TravauxBesanconCard);
customElements.define("travaux-besancon-card-editor", TravauxBesanconCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type:        "travaux-besancon-card",
  name:        "Travaux Besançon",
  description: "Arrêtés temporaires de circulation et de stationnement sur vos rues et quartiers de Besançon",
  preview:     false,
});

console.info(
  `%c TRAVAUX BESANÇON CARD %c v${TB_VERSION} `,
  `background:${COLORS.primary};color:#fff;font-weight:700;border-radius:4px 0 0 4px`,
  `background:#333;color:#fff;font-weight:400;border-radius:0 4px 4px 0`,
);
