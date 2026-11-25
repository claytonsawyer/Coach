#!/usr/bin/env python3
"""Pull Clayton's Garmin data with the official Garmin Connect Personal API,
summarise it, and write an ENCRYPTED file the dashboard can read.

Runs in GitHub Actions. Needs two secrets as environment variables:
  GARMIN_PERSONAL_API_KEY  - the Personal API key from Garmin Connect
  DASH_PASSPHRASE          - the passphrase the dashboard asks for

Output: garmin.enc.json  (AES-256-GCM, key from PBKDF2-SHA256)

The Actions log for a public repo is public, so this script NEVER prints
the key, the token, or any health/activity values - only counts, dates of
coverage and HTTP status codes. Set DEBUG_SHAPE=1 to print the *names* of
fields each endpoint returns (no values), for fixing field mappings.
"""
import base64
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import hashlib

BASE = "https://personal.connectapi.garmin.com"
TOKEN_URL = BASE + "/personalapitoken-service/personal-api/personal-api-key/token"
DAYS_BACK = int(os.environ.get("DAYS_BACK", "365"))
DEBUG_SHAPE = os.environ.get("DEBUG_SHAPE") == "1"
PBKDF2_ITER = 310_000
OUT = os.environ.get("OUT_FILE", "garmin.enc.json")


def log(msg):
    print(msg, flush=True)


# ── HTTP ─────────────────────────────────────────────────────────────
class ApiError(Exception):
    def __init__(self, status, path):
        super().__init__(f"HTTP {status} on {path}")
        self.status = status


def request(method, url, headers, retries=4):
    path = url.replace(BASE, "").split("?")[0]
    for attempt in range(retries):
        req = urllib.request.Request(url, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504) and attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            raise ApiError(e.code, path) from None
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            raise ApiError("network", path) from None


def get_token(api_key):
    body = request("POST", TOKEN_URL, {"Authorization": f"ApiKey {api_key}",
                                       "Accept": "*/*"})
    body = body.strip()
    if body.startswith("{"):  # tolerate a JSON wrapper if Garmin adds one
        j = json.loads(body)
        body = j.get("access_token") or j.get("accessToken") or j.get("token") or ""
    return body.strip().strip('"')


class Garmin:
    def __init__(self, token):
        self.h = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self.calls = 0

    def get(self, path):
        time.sleep(0.4)
        self.calls += 1
        txt = request("GET", BASE + path, self.h)
        return json.loads(txt) if txt.strip() else None


# ── helpers ──────────────────────────────────────────────────────────
def dig(obj, path, default=None):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def first(obj, *paths):
    for p in paths:
        v = dig(obj, p)
        if v is not None and v != "":
            return v
    return None


def as_list(resp, *keys):
    if resp is None:
        return []
    if isinstance(resp, list):
        return resp
    for k in keys:
        if isinstance(resp.get(k), list):
            return resp[k]
    for v in resp.values():
        if isinstance(v, list):
            return v
    return []


def item_date(item):
    d = first(item, "calendarDate", "summaryDate", "date", "dailySleepDTO.calendarDate")
    return str(d)[:10] if d else None


def shape(name, items):
    if DEBUG_SHAPE and items:
        it = items[0]
        keys = sorted(it.keys()) if isinstance(it, dict) else type(it).__name__
        log(f"  [shape] {name}: {keys}")
        for k, v in (it.items() if isinstance(it, dict) else []):
            if isinstance(v, dict):
                log(f"  [shape] {name}.{k}: {sorted(v.keys())}")


def ranges(start, end, days):
    cur = start
    while cur <= end:
        stop = min(cur + dt.timedelta(days=days - 1), end)
        yield cur, stop
        cur = stop + dt.timedelta(days=1)


def fetch_ranged(g, name, template, start, end, chunk, list_keys):
    """Fetch a date-ranged endpoint in chunks; halve the chunk on HTTP 500
    (Garmin fails responses over ~256 KB with a bare 500)."""
    out = []
    pending = list(ranges(start, end, chunk))
    while pending:
        a, b = pending.pop(0)
        try:
            resp = g.get(template.format(a=a.isoformat(), b=b.isoformat()))
            out.extend(as_list(resp, *list_keys))
        except ApiError as e:
            span = (b - a).days + 1
            if e.status == 500 and span > 1:
                half = a + dt.timedelta(days=span // 2 - 1)
                pending[0:0] = [(a, half), (half + dt.timedelta(days=1), b)]
                continue
            if e.status in (400, 404, 500):  # gap / unsupported: skip this range
                log(f"  {name}: skipped {a}..{b} ({e})")
                continue
            raise
    shape(name, out)
    return out


# ── pulls ────────────────────────────────────────────────────────────
def pull_activities(g, since):
    acts, start = [], 0
    while True:
        page = as_list(g.get(f"/activitylist-service/activities/search/activities?start={start}&limit=20"))
        if start == 0:
            shape("activities", page)
        if not page:
            break
        for a in page:
            d = str(a.get("startTimeLocal") or "")[:10]
            if d and d < since.isoformat():
                return acts
            acts.append(a)
        if len(page) < 20:
            break
        start += 20
    return acts


def num(v, nd=1):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def build(g):
    today = dt.date.today()
    since = today - dt.timedelta(days=DAYS_BACK)

    log("Activities...")
    raw_acts = pull_activities(g, since)
    acts = []
    for a in raw_acts:
        acts.append({
            "id": a.get("activityId"),
            "t": a.get("startTimeLocal"),
            "type": dig(a, "activityType.typeKey"),
            "name": a.get("activityName"),
            "dist": num(a.get("distance"), 0),
            "dur": num(a.get("duration"), 0),
            "elev": num(a.get("elevationGain"), 0),
            "hr": num(a.get("averageHR"), 0),
            "maxHr": num(a.get("maxHR"), 0),
            "load": num(a.get("activityTrainingLoad"), 1),
            "te": num(a.get("aerobicTrainingEffect"), 1),
            "cad": num(first(a, "averageRunningCadenceInStepsPerMinute", "averageBikingCadenceInRevPerMinute"), 0),
            "z": [num(a.get(f"hrTimeInZone_{i}"), 0) or 0 for i in range(1, 6)],
        })

    days = {}

    def day(d):
        return days.setdefault(d, {"d": d})

    log("Daily summaries...")
    for it in fetch_ranged(g, "daily", "/usersummary-service/v2/dailysummaries?startDate={a}&endDate={b}",
                           since, today, 60, ["data"]):
        d = item_date(it)
        if not d:
            continue
        r = day(d)
        r["rhr"] = num(first(it, "heartRate.restingValue", "restingHeartRate"), 0)
        r["stress"] = num(first(it, "stress.avgLevel", "averageStressLevel"), 0)
        r["bbMax"] = num(first(it, "bodyBattery.maxValue", "bodyBatteryHighestValue"), 0)
        r["bbMin"] = num(first(it, "bodyBattery.minValue", "bodyBatteryLowestValue"), 0)
        r["steps"] = num(first(it, "movement.steps.value", "totalSteps"), 0)
        r["imMod"] = num(first(it, "intensityMinutes.moderate"), 0)
        r["imVig"] = num(first(it, "intensityMinutes.vigorous"), 0)
        r["resp"] = num(first(it, "respiration.avgValue"), 1)

    log("Sleep...")
    for it in fetch_ranged(g, "sleep", "/sleep-service/sleep/dailySleepSummariesByDate?startDate={a}&endDate={b}",
                           since, today, 31, ["data", "sleepSummaries"]):
        src = it.get("dailySleepDTO", it) if isinstance(it, dict) else {}
        d = item_date(it) or item_date(src)
        if not d or not first(src, "sleepTimeSeconds"):
            continue
        r = day(d)
        r["sleepS"] = num(src.get("sleepTimeSeconds"), 0)
        r["deepS"] = num(src.get("deepSleepSeconds"), 0)
        r["remS"] = num(src.get("remSleepSeconds"), 0)
        r["awakeS"] = num(src.get("awakeSleepSeconds"), 0)
        r["sleepScore"] = num(first(src, "sleepScores.overall.value", "sleepScore"), 0)

    log("HRV...")
    for it in fetch_ranged(g, "hrv", "/hrv-service/hrv/daily/{a}/{b}",
                           since, today, 366, ["hrvSummaries"]):
        d = item_date(it)
        if not d:
            continue
        r = day(d)
        r["hrv"] = num(it.get("lastNightAvg"), 0)
        r["hrvWeek"] = num(it.get("weeklyAvg"), 0)
        r["hrvStatus"] = it.get("status")
        r["hrvLow"] = num(first(it, "baseline.balancedLow"), 0)
        r["hrvHigh"] = num(first(it, "baseline.balancedUpper"), 0)

    log("Weight...")
    for it in fetch_ranged(g, "weight", "/weight-service/weight/range/{a}/{b}",
                           since, today, 90, ["dailyWeightSummaries"]):
        d = first(it, "summaryDate", "calendarDate", "date")
        grams = first(it, "latestWeight.weight", "weight")
        if not d or not grams:
            continue
        day(str(d)[:10])["wt"] = round(float(grams) / 1000, 2)   # kg

    zones = None
    try:
        zones = g.get("/biometric-service/heartRateZones/v2")
        shape("zones", as_list(zones) or ([zones] if isinstance(zones, dict) else []))
    except (ApiError, ValueError) as e:
        log(f"  zones: skipped ({type(e).__name__})")

    # keep only days that carry at least one value
    day_rows = sorted((r for r in days.values() if len(r) > 1), key=lambda r: r["d"])
    payload = {
        "v": 1,
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "range": [since.isoformat(), today.isoformat()],
        "days": day_rows,
        "acts": acts,
        "zones": zones,
    }
    log(f"Got {len(acts)} activities, {len(day_rows)} days "
        f"({sum(1 for r in day_rows if 'sleepS' in r)} nights of sleep, "
        f"{sum(1 for r in day_rows if r.get('hrv'))} nights of HRV, "
        f"{sum(1 for r in day_rows if r.get('wt'))} weigh-ins) "
        f"covering {since}..{today} in {g.calls} calls.")
    return payload


# ── encryption (matches WebCrypto PBKDF2 + AES-GCM in index.html) ───
def encrypt(payload, passphrase):
    salt, iv = os.urandom(16), os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, PBKDF2_ITER, 32)
    ct = AESGCM(key).encrypt(iv, json.dumps(payload, separators=(",", ":")).encode("utf-8"), None)
    b64 = lambda b: base64.b64encode(b).decode("ascii")
    return {"v": 1, "alg": "PBKDF2-SHA256/AES-256-GCM", "iter": PBKDF2_ITER,
            "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}


def main():
    api_key = os.environ.get("GARMIN_PERSONAL_API_KEY", "").strip()
    passphrase = os.environ.get("DASH_PASSPHRASE", "")
    log(f"GARMIN_PERSONAL_API_KEY is {'set' if api_key else 'NOT set'}; "
        f"DASH_PASSPHRASE is {'set' if passphrase else 'NOT set'}.")
    if not api_key or not passphrase:
        sys.exit("Missing secret(s). Add them under the repo's Settings -> Secrets and variables -> Actions.")
    if len(passphrase) < 12:
        sys.exit("DASH_PASSPHRASE is too short - use at least 12 characters (a few random words works well).")

    try:
        token = get_token(api_key)
    except ApiError as e:
        sys.exit(f"Token request failed ({e}). The key is missing, mistyped or expired - "
                 "make a new one in Garmin Connect and update the GitHub secret.")
    if not token:
        sys.exit("Token request returned an empty token.")

    payload = build(Garmin(token))
    with open(OUT, "w") as f:
        json.dump(encrypt(payload, passphrase), f)
    log(f"Wrote encrypted {OUT} ({os.path.getsize(OUT) // 1024} KB).")


if __name__ == "__main__":
    main()
