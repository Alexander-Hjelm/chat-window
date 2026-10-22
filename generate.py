#!/usr/bin/env python3
"""Generate a static WhatsApp-style chat page from input.txt.

Usage: python generate.py [input.txt] [-o output.html] [--seed N]
Asset paths in the input are resolved relative to the input file and the
output HTML (keep the output next to the input, or the assets will not load).
"""
import argparse
import json
import random
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

PERSON_RE = re.compile(r"^\[person\s+([\w\-]+)\]$", re.I)
ATTACH_RE = re.compile(r"^<(image|video|audio):([^>]+)>\s*(.*)$", re.I | re.S)
MSG_RE = re.compile(r"^(?:\[([^\]]+)\]\s*)?([\w\-]+):\s?(.*)$")
FULL_FMT = "%Y-%m-%d %H:%M"


def parse_ts(text, prev):
    text = text.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", FULL_FMT):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(text, fmt).time()
        except ValueError:
            continue
        dt = datetime.combine(prev.date(), t)
        return dt + timedelta(days=1) if dt < prev else dt
    raise ValueError(f"bad timestamp: {text!r}")


def parse(path, rng):
    people, chats = {}, []
    cur, section = None, None
    for n, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = PERSON_RE.match(line)
        if m:
            cur = {"id": m.group(1)}
            people[cur["id"]] = cur
            section = "person"
            continue
        if line.lower() == "[chat]":
            cur = {"members": [], "title": "", "messages": [], "_start": None,
                   "last_seen": ""}
            chats.append(cur)
            section = "chat_header"
            continue
        if section == "person":
            k, _, v = line.partition("=")
            k, v = k.strip().lower(), v.strip()
            cur[k] = v.lower() in ("true", "yes", "1") if k == "me" else v
            continue
        if section == "chat_header" and re.match(r"^(members|title|start|last_seen)\s*=", line):
            k, _, v = line.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k == "members":
                cur["members"] = [x.strip() for x in v.split(",") if x.strip()]
            elif k == "start":
                cur["_start"] = parse_ts(v, datetime.now())
            else:
                cur[k] = v
            continue
        if section in ("chat_header", "chat"):
            section = "chat"
            m = MSG_RE.match(line)
            msgs = cur["messages"]
            if m and m.group(2) in people:
                ts_text, sender, body = m.groups()
            elif msgs:
                ts_text, sender, body = None, msgs[-1]["from"], line
            else:
                sys.exit(f"{path.name}:{n}: cannot parse line: {raw}")
            if msgs:
                prev = msgs[-1]["_dt"]
            else:
                prev = cur["_start"] or datetime.now().replace(second=0, microsecond=0)
            try:
                if ts_text:
                    dt = parse_ts(ts_text, prev)
                elif msgs:
                    dt = prev + timedelta(seconds=rng.randint(30, 300))
                else:
                    dt = prev
            except ValueError as e:
                sys.exit(f"{path.name}:{n}: {e}")
            msg = {"from": sender, "_dt": dt, "text": body}
            a = ATTACH_RE.match(body)
            if a:
                msg["attach"] = {"type": a.group(1).lower(), "src": a.group(2).strip()}
                msg["text"] = a.group(3).strip()
            msgs.append(msg)
            continue
        sys.exit(f"{path.name}:{n}: unexpected line: {raw}")

    me = [p for p in people.values() if p.get("me")]
    if len(me) != 1:
        sys.exit("Exactly one [person ...] must have 'me = true'.")
    for c in chats:
        for pid in c["members"] + [m["from"] for m in c["messages"]]:
            if pid not in people:
                sys.exit(f"Unknown person id: {pid}")
        for m in c["messages"]:
            dt = m.pop("_dt")
            m["ts"] = dt.strftime("%Y-%m-%dT%H:%M:%S")
        c.pop("_start")
        c["group"] = len(c["members"]) > 1
        if not c["title"]:
            c["title"] = people[c["members"][0]].get("name", c["members"][0]) if c["members"] else "Chat"
    return me[0]["id"], people, chats


TEMPLATE = Path(__file__).with_name("template.html")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", default="input.txt")
    ap.add_argument("-o", "--output", default="chat.html")
    ap.add_argument("--seed", type=int, default=None, help="seed for random timestamp offsets")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    me, people, chats = parse(Path(args.input), rng)
    data = {"me": me, "people": people, "chats": chats}
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out = TEMPLATE.read_text(encoding="utf-8").replace("/*DATA*/null", payload)
    Path(args.output).write_text(out, encoding="utf-8")
    print(f"Wrote {args.output} ({len(chats)} chats, {len(people)} people)")


if __name__ == "__main__":
    main()


