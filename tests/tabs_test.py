import asyncio, datetime as dt
from playwright.async_api import async_playwright
today = dt.date.today()
well = [{"id": str(today - dt.timedelta(days=i)), "ctl": 9, "atl": 10, "hrv": 92, "restingHR": 48, "sleepSecs": 25000,
         "comments": (f"Back: pain {[4,5,3,6,4,3,5,2,3][i%9]}/10 · reach thigh · sit-to-stand hurt · routine done" if i%3 else None)} for i in range(1,40)]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': __import__('os').environ['CHROME']} if __import__('os').environ.get('CHROME') else {}))
        pg = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type=="error" and errs.append(m.text))
        async def route(r):
            u = r.request.url
            if 'raw.githubusercontent' in u: return await r.fulfill(path='garmin.enc.json', content_type='application/json')
            if 'intervals.icu' in u:
                if '/wellness' in u and r.request.method=='GET': return await r.fulfill(json=well)
                return await r.fulfill(json=[] if r.request.method=='GET' else {})
            if 'fonts' in u: return await r.abort()
            return await r.continue_()
        await pg.route("**/*", route)
        await pg.goto((__import__('pathlib').Path(__file__).resolve().parent.parent / 'index.html').as_uri())
        await pg.evaluate("localStorage.clear();localStorage.setItem('iv_athlete_id','i1');localStorage.setItem('iv_api_key','k');localStorage.setItem('garmin_pass','correct horse battery')")
        await pg.reload(); await pg.wait_for_timeout(2500)
        for t in ['today','train','recover','back']:
            await pg.click(f".m-tabs button:has-text('{t.capitalize()}')"); await pg.wait_for_timeout(400)
            await pg.screenshot(path=f'tab_{t}.png', full_page=True)
        # interactions
        await pg.click(".m-tabs button:has-text('Today')")
        await pg.click(".m-seg button:has-text('20')"); await pg.wait_for_timeout(200)
        print('20min:', await pg.locator('.m-sess-title').inner_text())
        await pg.click(".b-save"); await pg.wait_for_timeout(200)
        print('after done:', await pg.locator('.m-sess-title').inner_text(), '|', await pg.locator('.m-done').inner_text())
        await pg.click(".m-seg button:has-text('90+')"); print('90:', await pg.locator('.m-sess-title').inner_text())
        await pg.click(".m-tabs button:has-text('Train')"); await pg.locator('.ch-hit').nth(3).click(); print('tip:', await pg.locator('.ch-read').first.inner_text())
        print('errors:', errs)
        await b.close()
asyncio.run(main())
