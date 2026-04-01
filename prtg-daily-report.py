#!/usr/bin/env python3
import os
import requests
from collections import Counter
from datetime import datetime

PRTG_URL = os.environ["PRTG_URL"].rstrip("/")
PRTG_USER = os.environ["PRTG_USER"]
PRTG_PASSHASH = os.environ["PRTG_PASSHASH"]

# Optional: set PRTG_VERIFY_TLS=false if self-signed cert
VERIFY_TLS = os.environ.get("PRTG_VERIFY_TLS", "true").lower() == "true"


def api_table(content, columns, extra=None, count=5000):
    params = {
        "content": content,
        "output": "json",
        "columns": ",".join(columns),
        "count": count,
        "username": PRTG_USER,
        "passhash": PRTG_PASSHASH,
    }
    if extra:
        params.update(extra)
    r = requests.get(f"{PRTG_URL}/api/table.json", params=params, verify=VERIFY_TLS, timeout=30)
    r.raise_for_status()
    return r.json()


def parse_num(s):
    if s is None:
        return None
    txt = str(s).replace(",", "").strip()
    num = ""
    for ch in txt:
        if ch.isdigit() or ch in ".-":
            num += ch
        elif num:
            break
    try:
        return float(num) if num else None
    except Exception:
        return None


def top_by_keyword(sensors, keywords, n=5, reverse=True):
    rows = []
    for s in sensors:
        name = f"{s.get('device','')} / {s.get('sensor','')}".lower()
        if any(k in name for k in keywords):
            v = parse_num(s.get("lastvalue_raw") or s.get("lastvalue"))
            if v is not None:
                rows.append((v, s))
    rows.sort(key=lambda x: x[0], reverse=reverse)
    return rows[:n]


def format_bandwidth_from_bps(bps):
    """
    PRTG Traffic sensor lastvalue_raw is typically in bit/s.
    Return both Kbit/s and Mbit/s for readability.
    """
    kbit = bps / 1000.0
    mbit = bps / 1_000_000.0
    return kbit, mbit


def top_disk_by_used(sensors, n=5):
    """
    SNMP Disk Free sensors report FREE percent.
    For ranking and recommendations, convert to USED percent = 100 - free.
    """
    rows = []
    for s in sensors:
        name = f"{s.get('device','')} / {s.get('sensor','')}".lower()
        if "disk" in name or "inode" in name:
            free_pct = parse_num(s.get("lastvalue_raw") or s.get("lastvalue"))
            if free_pct is not None:
                used_pct = 100.0 - free_pct
                rows.append((used_pct, free_pct, s))
    rows.sort(key=lambda x: x[0], reverse=True)
    return rows[:n]


def sensor_status_summary(sensors):
    c = Counter()
    down_or_unusual = []
    for s in sensors:
        st = (s.get("status") or "").strip()
        c[st] += 1
        if st.lower() in ("down", "unusual", "warning"):
            down_or_unusual.append(s)
    return c, down_or_unusual


def recommendations(top_cpu, top_ram, top_disk_used, issues):
    recs = []
    if top_cpu and top_cpu[0][0] >= 80:
        recs.append("High CPU detected (>=80%). Check workload spikes and process-level usage.")
    if top_ram and top_ram[0][0] >= 85:
        recs.append("High RAM usage detected (>=85%). Consider memory tuning or restart planning.")
    # top_disk_used tuple: (used_pct, free_pct, sensor)
    if top_disk_used and top_disk_used[0][0] >= 85:
        recs.append("Disk usage high (>=85% used). Clean logs/temp files or extend storage.")
    if len(issues) > 0:
        recs.append("There are Down/Warning/Unusual sensors today. Review unstable sensors and alert thresholds.")
    if not recs:
        recs.append("No critical anomalies detected today. Keep current thresholds and monitor trends.")
    return recs


def main():
    devices_data = api_table(
        "devices",
        ["objid", "group", "device", "host", "status"],
    )
    sensors_data = api_table(
        "sensors",
        [
            "objid",
            "group",
            "device",
            "sensor",
            "status",
            "message",
            "lastvalue",
            "lastvalue_raw",
            "lastup",
            "lastdown",
        ],
    )

    devices = devices_data.get("devices", [])
    sensors = sensors_data.get("sensors", [])

    total_devices = len(devices)
    total_sensors = len(sensors)

    by_group = Counter((d.get("group") or "Unknown") for d in devices)

    top_cpu = top_by_keyword(sensors, ["cpu"], n=5, reverse=True)
    top_ram = top_by_keyword(sensors, ["memory", "ram"], n=5, reverse=True)
    top_disk_used = top_disk_by_used(sensors, n=5)
    top_bw = top_by_keyword(sensors, ["traffic", "bandwidth", "bit/s", "bps"], n=5, reverse=True)

    status_counter, issues = sensor_status_summary(sensors)
    recs = recommendations(top_cpu, top_ram, top_disk_used, issues)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append(f"PRTG Daily Report ({now})")
    lines.append("")
    lines.append(f"- Total devices: {total_devices}")
    lines.append(f"- Total sensors: {total_sensors}")
    lines.append("")
    lines.append("Total devices by group:")
    for g, cnt in by_group.most_common():
        lines.append(f"  - {g}: {cnt}")
    lines.append("")
    lines.append("Top CPU sensors:")
    for v, s in top_cpu:
        lines.append(f"  - {s.get('device')} / {s.get('sensor')}: {v}")
    if not top_cpu:
        lines.append("  - (no CPU sensors found)")
    lines.append("")
    lines.append("Top RAM sensors:")
    for v, s in top_ram:
        lines.append(f"  - {s.get('device')} / {s.get('sensor')}: {v}")
    if not top_ram:
        lines.append("  - (no RAM sensors found)")
    lines.append("")
    lines.append("Top Disk sensors (by used %):")
    for used_pct, free_pct, s in top_disk_used:
        lines.append(f"  - {s.get('device')} / {s.get('sensor')}: used {used_pct:.2f}% (free {free_pct:.2f}%)")
    if not top_disk_used:
        lines.append("  - (no Disk sensors found)")
    lines.append("")
    lines.append("Top Bandwidth sensors (Kbit/s and Mbit/s):")
    for bps, s in top_bw:
        kbit, mbit = format_bandwidth_from_bps(bps)
        lines.append(
            f"  - {s.get('device')} / {s.get('sensor')}: {kbit:.2f} Kbit/s ({mbit:.3f} Mbit/s)"
        )
    if not top_bw:
        lines.append("  - (no Bandwidth sensors found yet)")
    lines.append("")
    lines.append("Sensors in Down/Unusual/Warning states:")
    lines.append(f"  - Down: {status_counter.get('Down', 0)}")
    lines.append(f"  - Unusual: {status_counter.get('Unusual', 0)}")
    lines.append(f"  - Warning: {status_counter.get('Warning', 0)}")
    if issues:
        for s in issues[:15]:
            lines.append(f"  - {s.get('device')} / {s.get('sensor')} [{s.get('status')}] - {s.get('message','')}")
    else:
        lines.append("  - No unusual sensors today")
    lines.append("")
    lines.append("Recommendations:")
    for r in recs:
        lines.append(f"  - {r}")

    print("\n".join(lines))


if __name__ == "__main__":
    main()