# Dashboard tests

Headless-browser checks for `index.html` using fake data — no real Garmin or Intervals.icu calls.

```bash
pip install playwright cryptography && playwright install chromium
cd tests
python mock_pull.py      # builds garmin.enc.json from fake Garmin data (passphrase: "correct horse battery")
python e2e_test.py       # back check-in, lift log, cross-device sync, Intervals outage, AI prompt
python theme_test.py     # phone + desktop screenshots (theme_phone.png, theme_desk.png)
python refresh_test.py   # Refresh button → GitHub Action → reload
python runmech_test.py   # climb cadence / HR drift from synthetic run streams
```

Every script prints `errors []` when the page threw no JavaScript errors. Set `CHROME=/path/to/chrome` to use a specific browser.
