/* No dependencies or build step. Home Assistant supplies the authenticated hass object. */
class RegistryInspectorPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.rows = [];
    this.selected = new Set();
    this.page = 0;
    this.busy = false;
    this.loaded = false;
    this.loadSequence = 0;
  }

  set hass(value) {
    this._hass = value;
    if (this.isConnected && !this.loaded) this.refresh();
  }

  connectedCallback() {
    if (!this.shadowRoot.childElementCount) this.mount();
    if (this._hass && !this.loaded) this.refresh();
  }

  mount() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; height:100%; overflow:auto; color:var(--primary-text-color,#222);
          background:var(--primary-background-color,#fafafa); font:14px/1.5 system-ui,sans-serif; }
        * { box-sizing:border-box; } button,input,select { font:inherit; }
        button { cursor:pointer; border:1px solid var(--divider-color,#ccc); border-radius:6px;
          padding:8px 12px; color:inherit; background:var(--card-background-color,white); }
        button:disabled { cursor:default; opacity:.5; }
        button.primary { background:var(--primary-color,#0277bd); color:white; border-color:transparent; }
        button.danger { background:var(--error-color,#b3261e); color:white; border-color:transparent; }
        button:focus-visible,input:focus-visible,select:focus-visible { outline:2px solid
          var(--primary-color,#0277bd); outline-offset:2px; }
        header { display:flex; align-items:center; gap:14px; padding:12px 20px; border-bottom:1px solid
          var(--divider-color,#ddd); background:var(--card-background-color,white); }
        header h1 { font-size:20px; margin:0; flex:1; font-weight:600; }
        main { max-width:1400px; margin:auto; padding:24px; }
        p { margin:0 0 16px; } .muted { color:var(--secondary-text-color,#666); }
        #summary { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:20px; }
        .chip { border:1px solid var(--divider-color,#ddd); border-radius:20px; padding:5px 12px; }
        .filters { display:flex; gap:12px; flex-wrap:wrap; align-items:end; margin-bottom:16px; }
        label { display:flex; flex-direction:column; gap:4px; }
        label.search { flex:1; min-width:200px; }
        input[type=search],select { padding:9px; border:1px solid var(--divider-color,#aaa);
          border-radius:6px; background:var(--card-background-color,white); color:inherit; }
        input[type=checkbox] { width:18px; height:18px; accent-color:var(--primary-color,#0277bd); }
        .actions,.pager { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin:14px 0; }
        .actions span,.pager span { flex:1; }
        .table-wrap { overflow-x:auto; background:var(--card-background-color,white);
          border:1px solid var(--divider-color,#ddd); border-radius:8px; }
        table { border-collapse:collapse; width:100%; text-align:left; }
        th,td { padding:10px 12px; border-bottom:1px solid var(--divider-color,#ddd); }
        th { white-space:nowrap; color:var(--secondary-text-color,#666); font-size:12px; }
        tbody tr:last-child td { border-bottom:0; } .identity { max-width:420px; }
        .identity small { display:block; overflow-wrap:anywhere; }
        .badge { display:inline-block; border-radius:4px; padding:2px 6px;
          background:var(--secondary-background-color,#eee); white-space:nowrap; }
        .notice { padding:12px 16px; margin-bottom:16px; border:1px solid var(--divider-color,#ddd);
          border-radius:6px; overflow-wrap:anywhere; }
        .error { border-color:var(--error-color,#b3261e); color:var(--error-color,#b3261e); }
        [hidden] { display:none !important; }
        dialog { max-width:800px; width:calc(100% - 32px); max-height:85vh; overflow:auto;
          border:1px solid var(--divider-color,#aaa); border-radius:10px; padding:24px;
          color:inherit; background:var(--card-background-color,white); }
        dialog::backdrop { background:#0008; } dialog h2 { margin:0 0 12px; font-size:20px; }
        pre { white-space:pre-wrap; overflow-wrap:anywhere; padding:12px; border-radius:6px;
          background:var(--secondary-background-color,#eee); font-size:12px; }
        .ack { display:flex; flex-direction:row; align-items:start; margin:16px 0; }
        .ack input { flex-shrink:0; } #backup-path { display:block; overflow-wrap:anywhere; }
        @media(max-width:600px) { main { padding:16px; } header { padding:10px 16px; }
          th,td { padding:8px; } header h1 { font-size:18px; } }
      </style>
      <header>
        <button id="menu" aria-label="Toggle sidebar">☰</button>
        <h1>Registry Inspector</h1><button id="refresh">Refresh</button>
      </header>
      <main>
        <p class="muted">Inspect registered devices and entities, including saved deleted records.
          Active entries are read-only. Disabled and unavailable entries are still registered.</p>
        <div id="error" class="notice error" role="alert" hidden></div>
        <div id="compatibility" class="notice" hidden></div>
        <div id="success" class="notice" role="status" hidden>
          <span id="success-text"></span><code id="backup-path"></code>
          <button id="download">Download backup</button>
        </div>
        <div id="summary" aria-live="polite"></div>
        <div class="filters">
          <label class="search">Search<input id="search" type="search"
            placeholder="Name, entity ID, IEEE address, integration, or saved setting"></label>
          <label>Type<select id="kind"><option value="all">Devices and entities</option>
            <option value="entity">Entities</option><option value="device">Devices</option></select></label>
          <label>Registry status<select id="status"><option value="all">All entries</option>
            <option value="deleted">Saved deleted</option><option value="active">Active</option></select></label>
        </div>
        <div class="actions">
          <button id="select-page">Select deleted on this page</button>
          <button id="clear">Clear selection</button><span id="selection-count"></span>
          <button id="preview" class="primary">Preview forgetting</button>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>Select</th><th>Name / ID</th><th>Type</th><th>Registry</th>
            <th>Live status</th><th>Integration</th><th>Area</th><th>Details</th></tr></thead>
          <tbody id="rows"></tbody>
        </table></div>
        <p id="empty" class="muted" hidden>No matching entries.</p>
        <div class="pager"><button id="previous">Previous</button><span id="page"></span>
          <button id="next">Next</button></div>
        <p class="muted">Select entity and device records separately. Deleted entities may no longer
          contain a device link; search the physical IEEE address in their unique IDs.
          This panel does not delete MQTT messages, history, or statistics.</p>
      </main>
      <dialog id="details"><h2>Saved registry record</h2><pre id="record"></pre>
        <button id="close-details">Close</button></dialog>
      <dialog id="confirmation"><h2>Forget selected saved settings?</h2>
        <p>Only the records below will be forgotten. Home Assistant will no longer restore their
          saved settings when the same identity is registered again. A backup is written first.</p>
        <p class="muted">Any device record or entity record not selected remains unchanged.
          History and statistics remain unchanged.</p>
        <div id="preview-records"></div>
        <label class="ack"><input id="acknowledge" type="checkbox">
          I have checked these records and want to forget their saved settings.</label>
        <div class="actions"><button id="cancel">Cancel</button>
          <span></span><button id="forget" class="danger" disabled>Forget saved settings</button></div>
      </dialog>`;
    this.$("menu").onclick = () => this.dispatchEvent(new Event("hass-toggle-menu", {
      bubbles: true, composed: true,
    }));
    this.$("refresh").onclick = () => this.refresh();
    for (const id of ["search", "kind", "status"]) {
      this.$(id).addEventListener(id === "search" ? "input" : "change", () => {
        this.page = 0;
        this.render();
      });
    }
    this.$("previous").onclick = () => { this.page--; this.render(); };
    this.$("next").onclick = () => { this.page++; this.render(); };
    this.$("clear").onclick = () => { this.selected.clear(); this.render(); };
    this.$("select-page").onclick = () => {
      for (const row of this.visibleRows()) {
        if (row.deleted && this.selected.size < 100) this.selected.add(this.key(row));
      }
      this.render();
    };
    this.$("preview").onclick = () => this.previewSelection();
    this.$("close-details").onclick = () => this.$("details").close();
    this.$("cancel").onclick = () => this.$("confirmation").close();
    this.$("acknowledge").onchange = () => {
      this.$("forget").disabled = this.busy || !this.$("acknowledge").checked;
    };
    this.$("forget").onclick = () => this.forget();
    this.$("confirmation").addEventListener("cancel", (event) => {
      if (this.busy) event.preventDefault();
    });
    this.$("download").onclick = () => {
      const url = URL.createObjectURL(new Blob([this.lastBackup.backup_content], {
        type: "application/json",
      }));
      const link = document.createElement("a");
      link.href = url;
      link.download = this.lastBackup.backup_filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    };
    this.render();
  }

  $(id) { return this.shadowRoot.getElementById(id); }
  key(row) { return `${row.kind}:${row.id}`; }
  async call(type, data = {}) {
    return this._hass.callWS({ type: `registry_inspector/${type}`, ...data });
  }
  error(message) {
    this.$("error").textContent = message;
    this.$("error").hidden = !message;
  }
  filteredRows() {
    const search = this.$("search").value.trim().toLowerCase();
    const kind = this.$("kind").value;
    const status = this.$("status").value;
    return this.rows.filter((row) => (kind === "all" || row.kind === kind)
      && (status === "all" || row.deleted === (status === "deleted"))
      && (!search || JSON.stringify(row).toLowerCase().includes(search)));
  }
  visibleRows() { return this.filteredRows().slice(this.page * 50, (this.page + 1) * 50); }

  async refresh() {
    const sequence = ++this.loadSequence;
    this.loaded = true;
    this.busy = true;
    this.error("");
    this.render();
    try {
      const result = await this.call("list");
      if (sequence !== this.loadSequence) return;
      this.rows = result.rows;
      this.rows.sort((a, b) => a.name.localeCompare(b.name) || this.key(a).localeCompare(this.key(b)));
      this.writeDisabledReason = result.write_disabled_reason;
      // A refresh requires an explicit new selection rather than silently updating it.
      this.selected.clear();
    } catch (error) {
      if (sequence === this.loadSequence) {
        this.rows = [];
        this.selected.clear();
        this.error(error.message || String(error));
      }
    } finally {
      if (sequence === this.loadSequence) { this.busy = false; this.render(); }
    }
  }

  render() {
    if (!this.$("rows")) return;
    const deletedCount = this.rows.filter((row) => row.deleted).length;
    this.$("summary").replaceChildren(...[
      `${this.rows.length} total`, `${this.rows.length - deletedCount} active`,
      `${deletedCount} saved deleted`,
    ].map((text) => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = text;
      return chip;
    }));
    const filtered = this.filteredRows();
    const pages = Math.max(1, Math.ceil(filtered.length / 50));
    this.page = Math.max(0, Math.min(this.page, pages - 1));
    const visible = this.visibleRows();
    this.$("rows").replaceChildren(...visible.map((row) => {
      const tr = document.createElement("tr");
      const cell = (value, className) => {
        const td = document.createElement("td");
        if (value instanceof Node) td.append(value);
        else td.textContent = value || "—";
        if (className) td.className = className;
        tr.append(td);
        return td;
      };
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.setAttribute("aria-label", `Select ${row.name}`);
      checkbox.checked = this.selected.has(this.key(row));
      checkbox.disabled = !row.deleted || this.busy || !!this.writeDisabledReason
        || (!checkbox.checked && this.selected.size >= 100);
      checkbox.onchange = () => {
        if (checkbox.checked) this.selected.add(this.key(row));
        else this.selected.delete(this.key(row));
        this.render();
      };
      cell(checkbox);
      const name = document.createElement("div");
      name.textContent = row.name;
      const id = document.createElement("small");
      id.className = "muted";
      id.textContent = row.entity_id || row.id;
      name.append(id);
      cell(name, "identity");
      cell(row.kind === "entity" ? "Entity" : "Device");
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = row.deleted ? "Saved deleted" : "Active";
      cell(badge);
      cell(row.deleted ? "Not registered" : row.disabled ? "Disabled"
        : row.state || (row.kind === "device" ? "See entities" : "No current state"));
      cell(row.integration);
      cell(row.area);
      const details = document.createElement("button");
      details.textContent = "View";
      details.setAttribute("aria-label", `View ${row.name}`);
      details.onclick = () => {
        this.$("record").textContent = JSON.stringify({ section: row.section, ...row.record }, null, 2);
        this.$("details").showModal();
      };
      cell(details);
      return tr;
    }));
    this.$("empty").hidden = !!filtered.length || this.busy;
    this.$("page").textContent = this.busy ? "Loading…"
      : `${filtered.length} matches · Page ${this.page + 1} of ${pages}`;
    this.$("previous").disabled = this.busy || this.page === 0;
    this.$("next").disabled = this.busy || this.page >= pages - 1;
    this.$("refresh").disabled = this.busy;
    this.$("clear").disabled = this.busy || !this.selected.size;
    this.$("select-page").disabled = this.busy || !!this.writeDisabledReason
      || !visible.some((row) => row.deleted) || this.selected.size >= 100;
    this.$("preview").disabled = this.busy || !!this.writeDisabledReason || !this.selected.size;
    this.$("selection-count").textContent = `${this.selected.size} selected across all filters (max 100)`;
    this.$("compatibility").hidden = !this.writeDisabledReason;
    this.$("compatibility").textContent = this.writeDisabledReason || "";
  }

  async previewSelection() {
    this.busy = true;
    this.error("");
    this.render();
    try {
      const selections = this.rows.filter((row) => this.selected.has(this.key(row)))
        .map(({ kind, id, fingerprint }) => ({ kind, id, fingerprint }));
      this.preview = await this.call("preview", { selections });
      this.$("preview-records").replaceChildren(...this.preview.records.map((item) => {
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        const record = item.record;
        summary.textContent = `${item.section}: ${record.entity_id || record.name_by_user || record.id}`;
        const pre = document.createElement("pre");
        pre.textContent = JSON.stringify(record, null, 2);
        details.append(summary, pre);
        return details;
      }));
      this.$("acknowledge").checked = false;
      this.$("forget").disabled = true;
      this.$("confirmation").showModal();
    } catch (error) { this.error(error.message || String(error)); }
    finally { this.busy = false; this.render(); }
  }

  async forget() {
    if (this.busy || !this.preview || !this.$("acknowledge").checked) return;
    this.busy = true;
    this.$("forget").disabled = true;
    this.$("cancel").disabled = true;
    this.error("");
    this.render();
    try {
      const result = await this.call("forget", { token: this.preview.token });
      this.lastBackup = result;
      this.$("success-text").textContent = `Forgot ${result.forgotten} saved deleted records.
        Home Assistant has scheduled its registry save. Backup: `;
      this.$("backup-path").textContent = result.backup_path;
      this.$("success").hidden = false;
      this.$("confirmation").close();
      await this.refresh();
    } catch (error) {
      this.$("confirmation").close();
      this.error(error.message || String(error));
    } finally {
      this.preview = null;
      this.busy = false;
      this.$("cancel").disabled = false;
      this.render();
    }
  }
}

if (!customElements.get("registry-inspector-panel")) {
  customElements.define("registry-inspector-panel", RegistryInspectorPanel);
}
