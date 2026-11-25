import asyncio, json, math, datetime as dt
from playwright.async_api import async_playwright
today = dt.date.today()
def streams(seed):
    t=list(range(0,3600)); dist=[]; alt=[]; cad=[]; hr=[]; d=0
    for i in t:
        climbing = (i//300)%3==1           # every 3rd 5-min block is a 8% climb
        sp = 2.4 if climbing else 3.2
        d += sp; dist.append(d)
        alt.append((alt[-1] if alt else 100) + (sp*0.08 if climbing else (-sp*0.04 if (i//300)%3==2 else 0)))
        cad.append(77+seed if climbing else 86)
        hr.append(138 + i/3600*14 + (8 if climbing else 0))
    return [{"type":"time","data":t},{"type":"distance","data":dist},{"type":"altitude","data":alt},{"type":"cadence","data":cad},{"type":"heartrate","data":hr}]
acts=[{"id":f"i{k}","type":"TrailRun" if k%2 else "Run","name":f"Morning Run {k}","moving_time":3600,"start_date_local":f"{today-dt.timedelta(days=3*k)}T06:00:00"} for k in range(6)]
calls=[0]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': __import__('os').environ['CHROME']} if __import__('os').environ.get('CHROME') else {}))
        pg = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
        async def route(r):
            u=r.request.url
            if 'raw.githubusercontent' in u: return await r.fulfill(path='garmin.enc.json', content_type='application/json')
            if 'intervals.icu' in u:
                if '/streams' in u: calls[0]+=1; k=int(u.split('/activity/i')[1].split('/')[0]); return await r.fulfill(json=streams(k))
                if '/activities' in u: return await r.fulfill(json=acts)
                return await r.fulfill(json=[])
            if 'fonts' in u: return await r.abort()
            return await r.continue_()
        await pg.route("**/*", route)
        await pg.goto((__import__('pathlib').Path(__file__).resolve().parent.parent / 'index.html').as_uri())
        await pg.evaluate("localStorage.clear();localStorage.setItem('iv_athlete_id','i1');localStorage.setItem('iv_api_key','k');localStorage.setItem('garmin_pass','correct horse battery');localStorage.setItem('tab','train')")
        await pg.reload(); await pg.wait_for_timeout(6000)
        print('stream calls', calls[0])
        print(json.dumps(await pg.evaluate("state.runMech"))[:400])
        card = pg.locator('.card:has-text("Run mechanics")'); await card.screenshot(path='runmech.png')
        await pg.click(".m-tabs button:has-text('Back')"); await pg.wait_for_timeout(300)
        print('checkpoint:', await pg.locator('.m-check').inner_text())
        await pg.reload(); await pg.wait_for_timeout(3000); print('stream calls after reload (cached):', calls[0])
        print('errors', errs)
        await b.close()
asyncio.run(main())
