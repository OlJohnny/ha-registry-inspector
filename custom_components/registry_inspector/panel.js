/* No dependencies or build step. Home Assistant supplies the authenticated hass object. */
class RegistryInspectorPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.rows = [];
    this.selected = new Set();
    this.visibleLimit = 50;
    this.collapsedGroups = new Set();
    this.busy = false;
    this.loaded = false;
    this.loadSequence = 0;
    this.addEventListener("scroll", () => this.scheduleLoad(), { passive: true });
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
        .actions { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin:14px 0;
          position:sticky; top:0; z-index:1; padding:10px 0;
          background:var(--primary-background-color,#fafafa); }
        .actions span { flex:1; }
        .group,.single-records { margin-bottom:14px; border:1px solid var(--divider-color,#ddd);
          border-radius:8px; background:var(--card-background-color,white); overflow:hidden; }
        .single-records > .table-wrap { border-top:0; }
        .group > summary { display:flex; gap:12px; align-items:center; padding:12px;
          cursor:pointer; list-style:none; }
        .group > summary::before { content:"▸"; width:12px; }
        .group[open] > summary::before { content:"▾"; }
        .group-title { flex:1; min-width:0; overflow-wrap:anywhere; font-weight:600; }
        .group-count { color:var(--secondary-text-color,#666); font-size:12px; }
        #load-status { padding:12px 0; text-align:center; }
        .table-wrap { overflow-x:auto; background:var(--card-background-color,white);
          border-top:1px solid var(--divider-color,#ddd); }
        table { border-collapse:collapse; width:100%; text-align:left; }
        th,td { padding:10px 12px; border-bottom:1px solid var(--divider-color,#ddd); }
        th { white-space:nowrap; color:var(--secondary-text-color,#666); font-size:12px; }
        tbody:last-child tr:last-child td { border-bottom:0; } .identity { max-width:420px; }
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
        @media(max-width:600px) { main { padding:16px; } header { padding:10px 16px; }
          th,td { padding:8px; } header h1 { font-size:18px; } }
      </style>
      <header>
        <button id="menu" aria-label="Toggle sidebar">☰</button>
        <h1>Registry Inspector</h1><button id="refresh">Refresh</button>
      </header>
      <main>
        <div id="error" class="notice error" role="alert" hidden></div>
        <div id="compatibility" class="notice" hidden></div>
        <div id="success" class="notice" role="status" hidden>
          <span id="success-text"></span>
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
          <button id="select-loaded">Select loaded deleted records</button>
          <button id="clear">Clear selection</button><span id="selection-count"></span>
          <button id="forget" class="danger">Forget selected</button>
        </div>
        <div id="groups"></div>
        <p id="empty" class="muted" hidden>No matching entries.</p>
        <div id="load-status" class="muted" role="status"></div>
      </main>
      <dialog id="details"><h2>Saved registry record</h2><pre id="record"></pre>
        <button id="close-details">Close</button></dialog>`;
    this.$("menu").onclick = () => this.dispatchEvent(new Event("hass-toggle-menu", {
      bubbles: true, composed: true,
    }));
    this.$("refresh").onclick = () => this.refresh();
    for (const id of ["search", "kind", "status"]) {
      this.$(id).addEventListener(id === "search" ? "input" : "change", () => {
        this.visibleLimit = 50;
        this.scrollTop = 0;
        this.render();
      });
    }
    this.$("clear").onclick = () => { this.selected.clear(); this.updateSelection(); };
    this.$("select-loaded").onclick = () => {
      for (const row of this.visibleRows()) {
        if (row.deleted) this.selected.add(this.key(row));
      }
      this.updateSelection();
    };
    this.$("close-details").onclick = () => this.$("details").close();
    this.$("forget").onclick = () => this.forget();
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
  filteredGroups() {
    if (this.groupCache) return this.groupCache;
    const groups = new Map();
    for (const row of this.filteredRows()) {
      const id = row.group_id || (row.kind === "device" ? this.key(row) : "other");
      if (!groups.has(id)) groups.set(id, {
        id, name: row.group_name || (row.kind === "device" ? row.name : "Other entities"), rows: [],
      });
      groups.get(id).rows.push(row);
    }
    this.groupCache = [...groups.values()].sort((a, b) => (a.id === "other") - (b.id === "other")
      || a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
    return this.groupCache;
  }

  visibleRows() {
    return this.filteredGroups().flatMap((group) => group.rows).slice(0, this.visibleLimit);
  }

  scheduleLoad() {
    if (this.loadScheduled) return;
    this.loadScheduled = requestAnimationFrame(() => {
      this.loadScheduled = null;
      if (!this.isConnected || this.busy || !this.clientHeight) return;
      const total = this.filteredGroups().reduce((count, group) => count + group.rows.length, 0);
      if (this.visibleLimit >= total) return;
      if (this.scrollTop + this.clientHeight < this.scrollHeight - 160) return;
      this.visibleLimit += 50;
      this.renderGroups(true);
    });
  }

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
      this.visibleLimit = 50;
      this.scrollTop = 0;
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
    if (!this.$("groups")) return;
    this.groupCache = null;
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
    this.renderGroups();
    this.$("compatibility").hidden = !this.writeDisabledReason;
    this.$("compatibility").textContent = this.writeDisabledReason || "";
  }

  renderGroups(append = false) {
    if (!append) this.$("groups").replaceChildren();
    const existing = new Map([...this.$("groups").querySelectorAll("tbody[data-group]")]
      .map((body) => [body.dataset.group, body]));
    const groups = this.filteredGroups();
    let remaining = this.visibleLimit;
    for (const group of groups) {
      if (remaining <= 0) break;
      const records = group.rows.slice(0, remaining);
      remaining -= records.length;
      let body = existing.get(group.id);
      if (!body && group.rows.length === 1) {
        let block = this.$("groups").lastElementChild;
        if (!block?.classList.contains("single-records")) {
          block = document.createElement("div");
          block.className = "single-records";
          block.append(this.createTable());
          this.$("groups").append(block);
        }
        const table = block.querySelector("table");
        body = table.lastElementChild;
        if (body.dataset.group) {
          body = document.createElement("tbody");
          table.append(body);
        }
        body.dataset.group = group.id;
      } else if (!body) {
        const node = document.createElement("details");
        node.className = "group";
        node.dataset.group = group.id;
        node.open = !this.collapsedGroups.has(group.id);
        const summary = document.createElement("summary");
        const select = document.createElement("input");
        select.type = "checkbox";
        select.className = "group-select";
        select.members = group.rows.filter((row) => row.deleted).map((row) => this.key(row));
        select.setAttribute("aria-label", `Select deleted in ${group.name}`);
        select.onclick = (event) => event.stopPropagation();
        select.onchange = () => {
          for (const key of select.members) {
            if (select.checked) this.selected.add(key);
            else this.selected.delete(key);
          }
          this.updateSelection();
        };
        const name = document.createElement("span");
        name.className = "group-title";
        name.textContent = group.name;
        const count = document.createElement("span");
        count.className = "group-count";
        count.textContent = `${group.rows.length} records · ${select.members.length} deleted`;
        summary.append(select, name, count);
        const table = this.createTable();
        body = table.querySelector("tbody");
        body.dataset.group = group.id;
        node.append(summary, table);
        node.addEventListener("toggle", () => {
          if (node.open) this.collapsedGroups.delete(group.id);
          else this.collapsedGroups.add(group.id);
          this.scheduleLoad();
        });
        this.$("groups").append(node);
      }
      body.append(...records.slice(body.children.length).map((row) => this.renderRow(row)));
    }
    const total = groups.reduce((count, group) => count + group.rows.length, 0);
    this.$("empty").hidden = !!total || this.busy;
    this.$("load-status").textContent = this.busy ? "Loading…"
      : `${Math.min(this.visibleLimit, total)} of ${total} records`;
    this.updateSelection();
    this.scheduleLoad();
  }

  createTable() {
    const table = document.createElement("div");
    table.className = "table-wrap";
    table.innerHTML = `<table><thead><tr><th>Select</th><th>Name / ID</th><th>Type</th>
      <th>Registry</th><th>Live status</th><th>Integration</th><th>Area</th><th>Details</th>
      </tr></thead><tbody></tbody></table>`;
    return table;
  }

  renderRow(row) {
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
    checkbox.className = "record-select";
    checkbox.dataset.key = this.key(row);
    checkbox.setAttribute("aria-label", `Select ${row.name}`);
    checkbox.checked = this.selected.has(this.key(row));
    checkbox.disabled = !row.deleted || this.busy || !!this.writeDisabledReason;
    checkbox.deleted = row.deleted;
    checkbox.onchange = () => {
      if (checkbox.checked) this.selected.add(this.key(row));
      else this.selected.delete(this.key(row));
      this.updateSelection();
    };
    cell(checkbox);
    const name = document.createElement("div");
    name.textContent = row.name;
    const subtitle = row.entity_id || row.id;
    if (subtitle !== row.name) {
      const id = document.createElement("small");
      id.className = "muted";
      id.textContent = subtitle;
      name.append(id);
    }
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
  }

  updateSelection() {
    for (const input of this.shadowRoot.querySelectorAll(".record-select")) {
      input.checked = this.selected.has(input.dataset.key);
      input.disabled = !input.deleted || this.busy || !!this.writeDisabledReason;
    }
    for (const input of this.shadowRoot.querySelectorAll(".group-select")) {
      const selected = input.members.filter((key) => this.selected.has(key)).length;
      input.checked = input.members.length > 0 && selected === input.members.length;
      input.indeterminate = selected > 0 && selected < input.members.length;
      input.disabled = this.busy || !!this.writeDisabledReason || !input.members.length;
    }
    this.$("refresh").disabled = this.busy;
    this.$("clear").disabled = this.busy || !this.selected.size;
    this.$("select-loaded").disabled = this.busy || !!this.writeDisabledReason
      || !this.visibleRows().some((row) => row.deleted);
    this.$("forget").disabled = this.busy || !!this.writeDisabledReason || !this.selected.size;
    this.$("forget").textContent = this.busy ? "Working…" : "Forget selected";
    this.$("selection-count").textContent = `${this.selected.size} selected`;
  }

  async forget() {
    if (this.busy || this.writeDisabledReason || !this.selected.size) return;
    this.busy = true;
    this.$("forget").disabled = true;
    this.$("success").hidden = true;
    this.error("");
    this.render();
    try {
      const selections = this.rows.filter((row) => this.selected.has(this.key(row)))
        .map(({ kind, id, fingerprint }) => ({ kind, id, fingerprint }));
      const result = await this.call("forget", { selections });
      this.lastBackup = result;
      this.$("success-text").textContent = `Forgot ${result.forgotten} records. `;
      this.$("download").title = result.backup_path;
      this.$("success").hidden = false;
      await this.refresh();
    } catch (error) {
      this.error(error.message || String(error));
    } finally {
      this.busy = false;
      this.render();
    }
  }
}

if (!customElements.get("registry-inspector-panel")) {
  customElements.define("registry-inspector-panel", RegistryInspectorPanel);
}
