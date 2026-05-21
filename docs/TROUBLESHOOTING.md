# Troubleshooting

These are the real issues encountered while building this, with fixes.

### "No Lymow device targeted. Pick the mower in the Targets section."
The target is wrong. `start_zones` needs a **device** target. Most commonly you
put an entity ID (`lawn_mower.lymow1`) where a device ID belongs.
**Fix:** use the 32-character hex device ID — see step 2 in the README.

### "extra keys not allowed @ data['entity_id']"
This build of the integration does **not** accept `entity_id` as a target at
all — only `device_id`.
**Fix:** use `device_id: <hex>`.

### "Template rendered invalid entity IDs: ['ed2c…']"
You have the correct hex string but it's on a `entity_id:` line. HA is trying
to validate the hex as an entity ID.
**Fix:** change that line's key from `entity_id:` to `device_id:`.

### The script doesn't appear / "unknown action"
If `configuration.yaml` has `script: !include scripts.yaml`, then
`scripts.yaml` must contain the script IDs at the **top level** with no
`script:` wrapper. A doubled `script:` key makes HA load zero scripts.
**Fix:** remove the top-level `script:` line, then *Developer Tools → YAML →
Reload Scripts* (no reboot needed).

### A card button shows "unavailable"
The script it points to doesn't exist yet (not created, or failed to load).
Reload scripts and confirm `script.lymow_queue_mow` etc. appear in
*Developer Tools → States*.

### Helper entity ID doesn't match
The entity ID is fixed at creation from the name and does **not** follow a
later rename. You need exactly `input_select.lymow_zone` and
`input_text.lymow_queue`. Check/fix via the helper's settings (gear) dialog.

### "Unknown zone: 'X'. Known zones: …"
The name isn't in the mower's current zone catalog, or the catalog hasn't
loaded yet. It refreshes at startup and on the Waiting→Mowing transition.
**Fix:** start any mow once from the Lymow app, then retry. Confirm spelling
against the per-zone sensors (use the bare name, not the "Zone " prefix).

### I tapped MOW but nothing happened
`start_zones` is **fire-and-forget** — a successful call means "sent," not
"accepted." The firmware silently ignores commands invalid for its current
state (already mowing, or in an error).
**Fix:** watch the work-status sensor; if it doesn't flip to *Mowing*, resolve
the mower's state first (dock/clear error) and resend.
