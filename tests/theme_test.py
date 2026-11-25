import asyncio, json, datetime as dt
from playwright.async_api import async_playwright
exec(open(__import__('pathlib').Path(__file__).with_name('runmech_test.py')).read().split('calls=[0]')[0].split('from playwright.async_api import async_playwright')[1])
well = [{"id": str(today - dt.timedelta(days=i)), "comments": (f"Back: pain {[1,2,2,1,4,5][i%6]}/10 · reach thigh · sit-to-stand ok · routine done")} for i in range(1,20)]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': __import__('os').environ['CHROME']} if __import__('os').environ.get('CHROME') else {}))
        errs=[]
        for name, vp, view in [('phone', {"width":390,"height":844}, 'phone'), ('desk', {"width":1500,"height":1000}, 'desktop')]:
            pg = await b.new_page(viewport=vp, device_scale_factor=2 if view=='phone' else 1)
            pg.on("pageerror", lambda e: errs.append(str(e)))
            async def route(r):
                u=r.request.url
                if 'raw.githubusercontent' in u: return await r.fulfill(path='garmin.enc.json', content_type='application/json')
                if 'intervals.icu' in u:
                    if '/streams' in u: k=int(u.split('/activity/i')[1].split('/')[0]); return await r.fulfill(json=streams(k))
                    if '/activities' in u: return await r.fulfill(json=acts)
                    if '/wellness' in u: return await r.fulfill(json=well)
                    return await r.fulfill(json=[])
                if 'fonts.g' in u: return await r.abort()
                return await r.continue_()
            await pg.route("**/*", route)
            await pg.goto((__import__('pathlib').Path(__file__).resolve().parent.parent / 'index.html').as_uri())
            await pg.evaluate(f"localStorage.clear();localStorage.setItem('iv_athlete_id','i1');localStorage.setItem('iv_api_key','k');localStorage.setItem('garmin_pass','correct horse battery');localStorage.setItem('tab','train');localStorage.setItem('dashboard_view','{view}');localStorage.setItem('view','{view}')")
            await pg.reload(); await pg.wait_for_timeout(5000)
            if view=='desktop':
                if not await pg.locator('.d-wrap').count():
                    await pg.evaluate("setView('desktop')"); await pg.wait_for_timeout(1500)
            await pg.screenshot(path=f'theme_{name}.png', full_page=True)
            await pg.close()
        print('errors', errs)
        await b.close()
asyncio.run(main())
