#!/usr/bin/env python3
"""
lymow_raw_tap.py — dump the truly raw Lymow One MQTT stream.

Connects to the same AWS IoT MQTT-over-WSS channel the official app and the
HA integration use, subscribes to /pboutput and /notify-app (the topics the
integration's MqttClient subscribes to), and prints EVERY field of EVERY
message as it arrives.

This is a standalone reconstruction of the integration's data path. It reuses
the integration's own modules (auth, sigv4, mqtt envelope + protobuf), so it
decodes messages identically to Home Assistant.

USAGE
-----
1. Put this file *next to* the integration package, i.e. in a folder that
   contains the `lymow_mqtt/` directory (the contents of
   custom_components/lymow_mqtt/). Easiest: copy the integration folder out:

       cp -r /path/to/custom_components/lymow_mqtt ./lymow_mqtt
       # then drop this script alongside it

2. Install deps into the same Python you'll run this with:

       pip install paho-mqtt aiohttp pycognito protobuf

3. Run:

       # native email/password login:
       python lymow_raw_tap.py --region us-east-2 --email you@example.com --password 'pw'

       # already have a Cognito refresh token? skip creds:
       python lymow_raw_tap.py --region us-east-2 --refresh-token 'ey...'

   It lists your mowers, you pick one, and the raw firehose starts.

NOTES
-----
* This OPENS ITS OWN connection. AWS IoT allows multiple concurrent clients,
  so it does NOT kick your HA integration offline — both can listen at once.
* Output is read-only: this script never publishes a command. It taps
  /pboutput (the mower's state broadcasts) and /notify-app. To ALSO see the
  commands the app/HA send (/pbinput), add that topic to the subscribe list
  in lymow_mqtt/mqtt.py:_on_connect — by default it's publish-only there.
* `--raw-hex` adds the raw protobuf bytes (hex) under each message, so you can
  diff against the schema or feed bytes to the wire-walker.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
from datetime import datetime

import aiohttp

# The integration package must be importable as `lymow_mqtt`.
try:
    from lymow_mqtt.auth import CognitoAuth
    from lymow_mqtt.const import API_ENDPOINTS, REGIONS, RTSP_PATH, RTSP_PORT
    from lymow_mqtt.mqtt import MqttClient
    from lymow_mqtt import protocol
    from lymow_mqtt.rest import LymowREST
except ImportError as e:
    sys.exit(
        f"Could not import the integration package: {e}\n"
        "Make sure a `lymow_mqtt/` folder (the integration's contents) sits "
        "next to this script, and that paho-mqtt/aiohttp/pycognito/protobuf "
        "are installed in this Python."
    )


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def dump_pboutput(raw_envelope: bytes, show_hex: bool) -> None:
    """Decode a /pboutput payload and print every populated field."""
    try:
        msg = protocol.decode_pboutput_envelope(raw_envelope)
    except Exception as exc:  # noqa: BLE001
        print(f"[{ts()}] /pboutput  DECODE FAILED: {exc}")
        if show_hex:
            print("    raw:", raw_envelope[:200])
        return

    present = protocol.populated_fields(msg)
    print(f"[{ts()}] /pboutput  fields={present}")
    # The protobuf library's text_format gives a complete, every-field dump.
    from google.protobuf import text_format

    text = text_format.MessageToString(msg, as_utf8=True)
    for line in text.splitlines():
        print("    " + line)

    if show_hex:
        # Recover the raw protobuf bytes (strip JSON envelope if present).
        stripped = raw_envelope.lstrip()
        raw_pb = (
            protocol.unwrap_envelope(raw_envelope)
            if stripped.startswith(b"{")
            else raw_envelope
        )
        print("    [raw protobuf hex]")
        print("    " + raw_pb.hex())
    print()


def dump_notify(payload: dict) -> None:
    print(f"[{ts()}] /notify-app  {json.dumps(payload)}")


async def main() -> None:
    ap = argparse.ArgumentParser(description="Raw Lymow One MQTT tap")
    ap.add_argument("--region", required=True, choices=sorted(REGIONS),
                    help="Your account's AWS region (one of the 4 Lymow regions)")
    ap.add_argument("--email")
    ap.add_argument("--password")
    ap.add_argument("--refresh-token", help="Skip login; use an existing Cognito refresh token")
    ap.add_argument("--thing-name", help="Skip the picker; tap this thingName directly")
    ap.add_argument("--raw-hex", action="store_true", help="Also print raw protobuf bytes")
    args = ap.parse_args()

    async with aiohttp.ClientSession() as session:
        auth = CognitoAuth(args.region, session)

        # --- authenticate ---
        if args.refresh_token:
            auth.refresh_token = args.refresh_token
            await auth.refresh_tokens()
        elif args.email and args.password:
            await auth.login_srp(args.email, args.password)
        else:
            sys.exit("Provide either --refresh-token, or --email and --password.")

        await auth.get_aws_credentials()
        print(f"[{ts()}] authenticated; AWS creds acquired")

        # --- pick a mower ---
        thing_name = args.thing_name
        if not thing_name:
            rest = LymowREST(args.region, auth, session)
            devices = await rest.get_device_list()
            if not devices:
                sys.exit("No mowers bound to this account.")
            print("\nMowers on this account:")
            for i, d in enumerate(devices):
                tn = d.get("deviceThingName") or d.get("thingName") or d.get("sn") or "?"
                nm = d.get("deviceName") or d.get("nickname") or ""
                print(f"  [{i}] {tn}   {nm}")
            idx = 0 if len(devices) == 1 else int(input("\nPick #: "))
            d = devices[idx]
            thing_name = d.get("deviceThingName") or d.get("thingName") or d.get("sn")

        host = API_ENDPOINTS[args.region]["iotDomain"]
        print(f"[{ts()}] tapping thing={thing_name} via {host}\n")

        # --- connect + stream ---
        loop = asyncio.get_running_loop()
        stop = loop.create_future()

        client = MqttClient(
            thing_name=thing_name,
            host=host,
            region=args.region,
            auth=auth,
            on_pboutput=lambda raw: dump_pboutput(raw, args.raw_hex),
            on_notify_app=dump_notify,
        )
        await client.connect()
        print(f"[{ts()}] connected + subscribed. Listening for raw messages "
              f"(Ctrl-C to stop)...\n")

        def _sig(*_):
            if not stop.done():
                stop.set_result(None)

        for s in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(s, _sig)
            except NotImplementedError:
                pass  # Windows

        await stop
        await client.disconnect()
        print(f"\n[{ts()}] disconnected.")


if __name__ == "__main__":
    asyncio.run(main())
