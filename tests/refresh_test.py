import json, datetime as dt, asyncio, time
from playwright.async_api import async_playwright
calls = {"dispatch": 0, "runs": 0}
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': __import__('os').environ['CHROME']} if __import__('os').environ.get('CHROME') else {}))
        pg = await b.new_page(viewport={"width": 400, "height": 900})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        state = {"blob": "old.enc.json"}
        async def route(r):
            u = r.request.url
            if 'raw.githubusercontent' in u: return await r.fulfill(path='old.enc.json', content_type='application/json')
            if 'api.github.com' in u:
                assert r.request.headers.get('authorization') == 'Bearer tok123'
                if '/dispatches' in u:
                    calls["dispatch"] += 1; return await r.fulfill(status=204, body='')
                if '/runs' in u:
                    calls["runs"] += 1
                    st = "completed" if calls["runs"] >= 2 else "in_progress"
                    if st == "completed": state["blob"] = "new.enc.json"
                    created = dt.datetime.now(dt.timezone.utc).isoformat()
                    return await r.fulfill(json={"workflow_runs": [{"created_at": created, "status": st, "conclusion": "success" if st=="completed" else None}]})
                if '/contents/' in u: return await r.fulfill(path=state["blob"], content_type='application/json')
            if 'intervals.icu' in u: return await r.fulfill(json=[])
            if 'fonts' in u: return await r.abort()
            return await r.continue_()
        await pg.route("**/*", route)
        await pg.goto((__import__('pathlib').Path(__file__).resolve().parent.parent / 'index.html').as_uri())
        await pg.evaluate("localStorage.setItem('iv_athlete_id','i1');localStorage.setItem('iv_api_key','k');localStorage.setItem('garmin_pass','correct horse battery')")
        await pg.reload(); await pg.wait_for_timeout(2500)
        before = await pg.evaluate("state.garmin.generated")
        await pg.click('.m-head .m-icon >> nth=0'); await pg.wait_for_timeout(500)
        print('setup shown without token:', await pg.locator('#gh-token').count())
        await pg.fill('#gh-token', 'tok123'); await pg.click('.g-setup button')
        await pg.click('.m-head .m-icon >> nth=0'); await pg.wait_for_timeout(3000)
        print('during:', await pg.locator('#g-refresh-msg').inner_text())
        
        await pg.wait_for_timeout(16000)
        after = await pg.evaluate("state.garmin.generated")
        print('dispatch calls', calls, 'data changed:', before != after, )
        print('errors:', errs)
        await b.close()
asyncio.run(main())
