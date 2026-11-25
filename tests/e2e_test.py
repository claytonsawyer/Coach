import asyncio, json, datetime as dt
from playwright.async_api import async_playwright
exec(open(__import__('pathlib').Path(__file__).with_name('runmech_test.py')).read().split('calls=[0]')[0].split('from playwright.async_api import async_playwright')[1])
DB = {str(today - dt.timedelta(days=i)): {"id": str(today - dt.timedelta(days=i)), "comments": f"Back: pain {[2,1,2,3,2,1,4][i%7]}/10 · reach thigh · sit-to-stand ok · routine done"} for i in range(1, 15)}
DB[str(today-dt.timedelta(days=3))]["comments"] += "\nDone: lower\nLifts: Rear-Foot Elevated Split Squat 40x8/40x8/40x8; Barbell or DB Hip Thrust 185x10/185x10/185x10"
DB[str(today-dt.timedelta(days=2))]["comments"] += "\nDone: upper\nLifts: Incline Barbell Press 135x8/135x8/135x7; Weighted Pull-Ups 25x6/25x6/25x5"
puts = []; DOWN = [False]
async def route(r):
    u = r.request.url
    if 'raw.githubusercontent' in u: return await r.fulfill(path='garmin.enc.json', content_type='application/json')
    if 'intervals.icu' in u:
        if DOWN[0]: return await r.fulfill(status=503, body='down')
        if r.request.method == 'PUT':
            body = json.loads(r.request.post_data); puts.append(body); DB[body['id']] = {**DB.get(body['id'], {}), **body}; return await r.fulfill(json=body)
        if '/streams' in u: k = int(u.split('/activity/i')[1].split('/')[0]); return await r.fulfill(json=streams(k))
        if '/activities' in u: return await r.fulfill(json=acts)
        if '/wellness' in u: return await r.fulfill(json=list(DB.values()))
        return await r.fulfill(json=[])
    if 'fonts.g' in u: return await r.abort()
    return await r.continue_()
async def page(b, tab='today', clear=True):
    ctx = await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    pg = await ctx.new_page(); pg.errs = []
    pg.on("pageerror", lambda e: pg.errs.append(str(e)))
    await pg.route("**/*", route)
    await pg.goto((__import__('pathlib').Path(__file__).resolve().parent.parent / 'index.html').as_uri())
    await pg.evaluate(f"localStorage.clear();localStorage.setItem('iv_athlete_id','i1');localStorage.setItem('iv_api_key','k');localStorage.setItem('garmin_pass','correct horse battery');localStorage.setItem('tab','{tab}')")
    await pg.reload(); await pg.wait_for_timeout(3500)
    return pg
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(**({'executable_path': __import__('os').environ['CHROME']} if __import__('os').environ.get('CHROME') else {}))
        # device A: back check-in, then lower session with lifts
        A = await page(b, 'back')
        await A.click('.b-pain button:nth-child(3)'); await A.click('.b-save >> nth=0'); await A.wait_for_timeout(600)
        print('back PUT:', [x['comments'].split('\n')[-1] for x in puts][-1])
        await A.screenshot(path='e2e_back.png', full_page=True)
        await A.click(".m-tabs button:has-text('Today')"); await A.wait_for_timeout(300)
        print('call:', await A.locator('.m-call-h').inner_text(), '|', (await A.locator('.m-why').inner_text()).replace('\n',' / '))
        await A.click(".m-seg button:has-text('60')"); await A.evaluate("setPick('lower')"); await A.wait_for_timeout(300)
        print('title:', await A.locator('.m-sess-title').inner_text())
        print('sug:', await A.locator('.lift-sug').first.inner_text())
        print('hinge row:', await A.locator('.exercise.hinge .exercise-name').count())
        inp = A.locator('.lift-log').nth(1).locator('input')
        await inp.nth(0).fill('45'); await inp.nth(0).dispatch_event('change')
        for k in range(1, await inp.count()): await inp.nth(k).fill('8'); await inp.nth(k).dispatch_event('change')
        await A.screenshot(path='e2e_today.png', full_page=True)
        await A.click('.m-sess .b-save'); await A.wait_for_timeout(800)
        print('today comments ->', DB[str(today)]['comments'].replace('\n',' || '))
        print('A errors', A.errs)
        # device B: fresh storage, sees same data via Intervals
        B = await page(b, 'today')
        print('B done banner:', await B.locator('.m-done').inner_text())
        await B.click(".m-tabs button:has-text('Train')"); await B.wait_for_timeout(2500)
        await B.screenshot(path='e2e_train.png', full_page=True)
        print('B strength rows:', await B.locator('.str-row').count())
        await B.click(".m-tabs button:has-text('Recover')"); await B.wait_for_timeout(300)
        await B.screenshot(path='e2e_recover.png', full_page=True)
        await B.click(".m-tabs button:has-text('Back')"); await B.wait_for_timeout(300)
        for q,v in [('sts','2'),('bridgeL','20'),('bridgeR','30'),('heel','ok'),('toe','ok'),('slr','60°+')]:
            await B.evaluate(f"setCheck('{q}','{v}')")
        await B.click("button:has-text('Save check')"); await B.wait_for_timeout(600)
        print('check saved ->', [l for l in DB[str(today)]['comments'].split('\n') if l.startswith('Check')])
        print('ladder:', await B.locator('.ladder .now').inner_text())
        print('B errors', B.errs)
        # Intervals down
        DOWN[0] = True
        C = await page(b, 'today')
        print('down warn:', (await C.locator('.m-warn').inner_text())[:60], '| call:', await C.locator('.m-call-h').inner_text())
        await C.click(".m-tabs button:has-text('Back')"); await C.click('.b-pain button:nth-child(2)'); await C.click('.b-save >> nth=0'); await C.wait_for_timeout(500)
        print('pending stored:', await C.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('pend_'))"))
        DOWN[0] = False
        await C.reload(); await C.wait_for_timeout(3500)
        print('after recovery pending:', await C.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('pend_'))"), '| DB back:', [l for l in DB[str(today)]['comments'].split('\n') if l.startswith('Back')])
        # AI prompt
        pr = await C.evaluate("buildClaudePrompt()")
        print('prompt has:', all(k in pr for k in ['HRV','Back last 14 days','Hinge ladder','Lifts (last 3 weeks)',"Dashboard's pick",'Run mechanics']))
        print('C errors', C.errs)
        await b.close()
asyncio.run(main())
