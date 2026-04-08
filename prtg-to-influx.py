#!/usr/bin/env python3
import os
import time
import requests
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point, WritePrecision

PRTG_URL = os.environ["PRTG_URL"].rstrip("/")
PRTG_USER = os.environ["PRTG_USER"]
PRTG_PASSHASH = os.environ["PRTG_PASSHASH"]
PRTG_VERIFY_TLS = os.environ.get("PRTG_VERIFY_TLS", "true").lower() == "true"

INFLUX_URL = os.environ["INFLUX_URL"]
INFLUX_TOKEN = os.environ["INFLUX_TOKEN"]
INFLUX_ORG = os.environ["INFLUX_ORG"]
INFLUX_BUCKET = os.environ["INFLUX_BUCKET"]

INTERVAL_SECONDS = 60

def fetch_sensors():
    params = {
        "content": "sensors",
        "output": "json",
        "columns": "objid,group,device,sensor,status,lastvalue,lastvalue_raw",
        "count": "5000",
        "username": PRTG_USER,
        "passhash": PRTG_PASSHASH,
    }
    r = requests.get(f"{PRTG_URL}/api/table.json", params=params, verify=PRTG_VERIFY_TLS, timeout=30)
    r.raise_for_status()
    return r.json().get("sensors", [])

def parse_float(v):
    try:
        return float(v)
    except Exception:
        return None

def main():
    client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = client.write_api()

    while True:
        try:
            sensors = fetch_sensors()
            now = datetime.now(timezone.utc)

            points = []
            for s in sensors:
                sensor_id = str(s.get("objid", ""))
                group = str(s.get("group", "Unknown"))
                device = str(s.get("device", "Unknown"))
                sensor = str(s.get("sensor", "Unknown"))
                status = str(s.get("status", "Unknown"))
                raw = parse_float(s.get("lastvalue_raw"))
                text_val = str(s.get("lastvalue", ""))

                p = (
                    Point("prtg_sensor")
                    .tag("sensor_id", sensor_id)
                    .tag("group", group)
                    .tag("device", device)
                    .tag("sensor", sensor)
                    .tag("status", status)
                    .field("value_raw", raw if raw is not None else 0.0)
                    .field("value_text", text_val)
                    .time(now, WritePrecision.S)
                )
                points.append(p)

            if points:
                write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=points)

            print(f"[{now.isoformat()}] wrote {len(points)} sensor points")
        except Exception as e:
            print(f"collector error: {e}")

        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    main()