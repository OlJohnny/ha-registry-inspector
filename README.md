# Registry Inspector

A Home Assistant sidebar panel that shows active devices and entities alongside the
deleted records Home Assistant remembers. Select saved deleted records to make Home
Assistant forget their old names, icons, areas and other settings before pairing a
previously used device again.

Active entries are read-only. Disabled or unavailable entities are still active
registry entries, not candidates for deletion.

## Compatibility

Version 0.2 targets **Home Assistant Core 2026.11.3**. Forgetting is enabled on the
2026.11 stable series only, with the expected entity and device registry schemas.
Other versions can inspect records if their serialization is compatible, but writes
are disabled. This integration uses internal registry interfaces; each new HA minor
release needs a compatibility review before enabling writes.

Python backend, plain JavaScript panel, no frontend dependencies or build step.
No separate server, credentials, Docker app or YAML configuration.

## Install

### HACS custom repository

1. In HACS, open the three-dot menu and **Custom repositories**.
2. Add `https://github.com/OlJohnny/ha-registry-inspector`, category **Integration**.
3. Download Registry Inspector and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and select
   **Registry Inspector**.
5. Open **Registry Inspector** in the sidebar as an administrator.

### Manual installation

Copy `custom_components/registry_inspector` into your Home Assistant configuration's
`custom_components` directory, then follow steps 3–5 above. You can do this using
Samba or a file editor app without typing source code into the VM console.

## Use

1. Search the replacement device's **physical IEEE address** or unique ID. An entity
   ID that you renamed can contain the address of a different device.
2. Review the **Saved deleted** entries. Use **View** to see the exact saved record.
3. Select individual deleted records, or use a device group's checkbox to select
   its deleted records. Active records remain read-only.
4. Choose **Forget selected**. A backup is written first and offered for download.
   Pair the device again when ready.

More entries appear automatically as you scroll. Selections persist across filters
and loading more entries, with no fixed count limit. **Refresh** clears them.
Every selected record is checked again immediately before mutation.
If any selected record has changed or become active again, the entire operation is
rejected. No active registry entry is ever removed.
Forgetting is also rejected during Home Assistant startup, shutdown or integration unload.

Entities are grouped with their devices using stored links when available. For
deleted entities, the panel also uses unambiguous complete hardware-address matches
within an integration. Records without a known device can share a hardware-address
group; ambiguous or unidentified records appear under Other entities. Grouping never
changes a saved record or the exact identities submitted for deletion. A group
checkbox selects its filtered deleted records, including any not yet loaded on screen.
Area names show an entry's explicitly saved area, not an inferred device area.

## What forgetting changes

- **Deleted entity records:** removes the selected entries from `deleted_entities`.
- **Deleted device records:** removes the selected entries from `deleted_devices`,
  through the registry's indexed container so its lookup indexes stay consistent.
- Home Assistant schedules persistence through its normal registry storage mechanism,
  usually within ten seconds while running. A normal shutdown flushes pending writes.

It does not modify active entities/devices, Zigbee2MQTT, MQTT retained messages,
Recorder history or statistics. Other integrations may still supply the same names
or settings when a device returns. Forgetting registry records cannot recover history
that Recorder has already purged.

## Backups and recovery

Backups live under `.storage/registry_inspector_backups/` in your Home Assistant
configuration directory. Each JSON file contains the selected records plus full
entity and device registry snapshots in Core's storage format. They contain device
identifiers and configuration metadata; treat them as configuration backups.
Backups are not automatically deleted.

The panel can download the backup from the most recent operation in the current
session. Older backups remain available through your configuration files.

Take a normal Home Assistant backup before using a new custom integration. The
panel does not provide automatic restore. To recover, restore your normal backup,
or, with Home Assistant Core **stopped**, extract `registries.entity` and
`registries.device` from the JSON into `.storage/core.entity_registry` and
`.storage/core.device_registry` respectively, then start Core. Restoring these full
snapshots also rolls back registry changes made after the backup. Do not replace
Core's registry files while Home Assistant is running.

## Development

On Linux with Python 3.14.2 or newer:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-test.txt
python -m playwright install --with-deps chromium
pytest
ruff check .
ruff format --check .
```

The tests exercise actual Home Assistant registry classes and the browser panel with
a simulated authenticated connection. They do not connect to or modify a live HA
server. GitHub Actions runs the same checks. No telemetry or external API calls are
made by the integration.
