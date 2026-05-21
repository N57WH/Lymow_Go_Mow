# Usage

## The everyday flow

1. **Pick a zone** from the *Lymow zone* dropdown.
2. Tap **ADD** — the zone is appended to the queue (visible in the *Queue* field).
3. Repeat for each zone, in the order you want them mowed.
4. Tap **MOW** — the mower drives the queue in order, and the queue clears.
5. **CLEAR** empties the queue without mowing.

Example:

| Step | Action | Queue becomes |
|------|--------|---------------|
| 1 | pick `East`, ADD | `East` |
| 2 | pick `North`, ADD | `East, North` |
| 3 | pick `Driveway`, ADD | `East, North, Driveway` |
| 4 | MOW | *(mows East → North → Driveway, then clears)* |

You can add the same zone twice to mow it twice, and you can hand-edit the
queue text directly if you prefer typing.

## Running it from elsewhere

The **MOW** button just calls `script.lymow_queue_mow`, so you can trigger the
same behaviour from an automation, a voice assistant, or another script. To mow
a fixed set of zones directly (bypassing the queue), call the underlying action:

```yaml
action: lymow_mqtt.start_zones
target:
  device_id: <YOUR_MOWER_DEVICE_ID>
data:
  zones:
    - East
    - North
```

Zone names are matched case-insensitively, and 8-character hashIds work too.
