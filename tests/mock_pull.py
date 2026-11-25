import sys, json, random, datetime as dt, re
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent.parent / 'scripts'))
import garmin_pull as gp
random.seed(1)
today = dt.date.today()
class Fake:
    calls = 0
    def get(self, path):
        self.calls += 1
        if path.startswith('/activitylist'):
            start = int(re.search(r'start=(\d+)', path).group(1))
            acts = []
            for i in range(start, start+20):
                d = today - dt.timedelta(days=int(i*1.6))
                if i > 200: break
                acts.append({"activityId": i, "startTimeLocal": f"{d} 07:00:00", "activityType": {"typeKey": random.choice(["trail_running","mountain_biking","strength_training","strength_training","stand_up_paddleboarding","surfing","motorcycling"])},
                  "activityName": "x", "distance": 8000, "duration": random.randint(1800, 7200), "elevationGain": 200, "averageHR": 145, "maxHR": 170,
                  "activityTrainingLoad": random.uniform(20, 120), "aerobicTrainingEffect": 2.8,
                  **{f"hrTimeInZone_{z}": random.uniform(0, 1200) for z in range(1,6)}})
            return acts
        if "heartRateZones" in path: return [{"sport": "DEFAULT", "zoneLowBoundaries": [100,142,160,169,187]}]
        m = re.search(r'(\d{4}-\d\d-\d\d)\D+(\d{4}-\d\d-\d\d)', path)
        a, b = dt.date.fromisoformat(m.group(1)), dt.date.fromisoformat(m.group(2))
        ds = [a + dt.timedelta(days=i) for i in range((b-a).days+1)]
        if 'dailysummaries' in path:
            if (b-a).days > 40: raise gp.ApiError(500, 'daily')   # exercise halving
            return {"data": [{"calendarDate": str(d), "heartRate": {"restingValue": 48}, "stress": {"avgLevel": 30}, "bodyBattery": {"maxValue": 80, "minValue": 20}, "movement": {"steps": {"value": 9000}}} for d in ds]}
        if 'sleep' in path:
            return [{"calendarDate": str(d), "sleepTimeSeconds": random.randint(18000, 27000), "deepSleepSeconds": 3600, "remSleepSeconds": 5400, "sleepScores": {"overall": {"value": 70}}} for d in ds]
        if 'weight-service' in path:
            return {"dailyWeightSummaries": [{"summaryDate": str(d), "latestWeight": {"weight": 83000 + (d - today).days * -12 + random.randint(-400,400)}} for d in ds if d.toordinal()%2==0]}
        if 'hrv' in path:
            return {"hrvSummaries": [{"calendarDate": str(d), "lastNightAvg": random.randint(70, 105), "weeklyAvg": 90, "status": "BALANCED", "baseline": {"balancedLow": 88, "balancedUpper": 108}} for d in ds]}
g = Fake()
payload = gp.build(g)
json.dump(gp.encrypt(payload, "correct horse battery"), open('garmin.enc.json','w'))
print('ok', len(json.dumps(payload))//1024, 'KB plaintext')
