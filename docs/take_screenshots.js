/**
 * Takes screenshots of the PO Extractor Streamlit app using headless Chrome + CDP.
 * Usage: node take_screenshots.js
 */
const { execSync, spawn } = require('child_process');
const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
// Use Node.js v21+ built-in WebSocket global

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const DEBUG_PORT = 9223;
const USER_DATA_DIR = 'C:\\Temp\\chrome-ss-profile';
const STREAMLIT_URL = 'http://localhost:8501';
const OUT_DIR = path.join(__dirname, 'screenshots');

if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

function httpGet(url) {
  return new Promise((resolve, reject) => {
    http.get(url, res => {
      let data = '';
      res.on('data', d => data += d);
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

async function waitForPort(port, maxWait = 10000) {
  const start = Date.now();
  while (Date.now() - start < maxWait) {
    try {
      await httpGet(`http://localhost:${port}/json`);
      return true;
    } catch {
      await delay(300);
    }
  }
  return false;
}

async function main() {
  // Clean old profile
  try { execSync(`rmdir /S /Q "${USER_DATA_DIR}"`, { stdio: 'ignore' }); } catch {}

  console.log('Launching headless Chrome...');
  const chrome = spawn(CHROME_PATH, [
    `--remote-debugging-port=${DEBUG_PORT}`,
    `--user-data-dir=${USER_DATA_DIR}`,
    '--headless=new',
    '--no-sandbox',
    '--disable-gpu',
    '--window-size=1440,900',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    'about:blank'
  ], { detached: true, stdio: 'ignore' });

  console.log('Waiting for Chrome debug port...');
  const ready = await waitForPort(DEBUG_PORT);
  if (!ready) { console.error('Chrome did not start in time'); process.exit(1); }
  console.log('Chrome ready!');

  // Get WebSocket URL
  const jsonData = await httpGet(`http://localhost:${DEBUG_PORT}/json`);
  const pages = JSON.parse(jsonData);
  const wsUrl = pages[0].webSocketDebuggerUrl;

  const ws = new WebSocket(wsUrl);
  let cmdId = 1;
  const pending = new Map();

  ws.addEventListener('open', async () => {
    function send(method, params = {}) {
      const id = cmdId++;
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        ws.send(JSON.stringify({ id, method, params }));
      });
    }

    async function screenshot(filename) {
      await delay(2000); // Wait for Streamlit to render
      const result = await send('Page.captureScreenshot', { format: 'jpeg', quality: 92 });
      const imgData = Buffer.from(result.data, 'base64');
      const fp = path.join(OUT_DIR, filename);
      fs.writeFileSync(fp, imgData);
      console.log(`Saved: ${filename} (${imgData.length} bytes)`);
    }

    async function navigate(url) {
      await send('Page.navigate', { url });
      await delay(4000); // wait for Streamlit to fully render
    }

    async function click(selector) {
      const { result } = await send('Runtime.evaluate', {
        expression: `
          (function() {
            const el = document.querySelector('${selector}');
            if (!el) return 'not found';
            el.click();
            return 'clicked';
          })()
        `
      });
      await delay(1000);
      return result.value;
    }

    async function scrollToTop() {
      await send('Runtime.evaluate', {
        expression: `document.querySelector('[data-testid="stMain"]')?.scrollTop = 0`
      });
      await delay(300);
    }

    try {
      // 1. Login page
      await navigate(STREAMLIT_URL);
      await screenshot('sc_01_login.jpg');
      console.log('Login page captured');

      // 2. Log in — use CDP Input.insertText to trigger React properly
      async function typeInto(placeholderOrType, text) {
        // Get element center coords
        const { result } = await send('Runtime.evaluate', {
          expression: `
            (function() {
              const inputs = document.querySelectorAll('input');
              const el = ${placeholderOrType === 'password'
                ? `Array.from(inputs).find(i => i.type === 'password')`
                : `Array.from(inputs).find(i => i.getAttribute('placeholder') === '${placeholderOrType}')`
              };
              if (!el) return null;
              const r = el.getBoundingClientRect();
              return { x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2) };
            })()
          `,
          returnByValue: true
        });
        if (!result.value) { console.error('Input not found:', placeholderOrType); return; }
        const { x, y } = result.value;
        // Triple-click to select all existing text, then insert
        await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 3 });
        await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 3 });
        await delay(200);
        await send('Input.insertText', { text });
        await delay(200);
      }

      await typeInto('your username', 'skyeast_demo');
      await typeInto('password', 'demo1234');
      await delay(300);

      // Click Sign In button via coords
      const { result: btnCoords } = await send('Runtime.evaluate', {
        expression: `
          (function() {
            const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Sign In'));
            if (!btn) return null;
            const r = btn.getBoundingClientRect();
            return { x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2) };
          })()
        `,
        returnByValue: true
      });
      if (btnCoords.value) {
        const { x, y } = btnCoords.value;
        await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
        await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
      }
      await delay(5000);
      await scrollToTop();
      await screenshot('sc_02_main_dashboard.jpg');
      console.log('Dashboard captured');

      // 3. Click Sky East tab
      await send('Runtime.evaluate', { expression: `
        Array.from(document.querySelectorAll('[data-baseweb="tab"]')).find(t => t.textContent.includes('Sky East'))?.click()
      `});
      await delay(2000);
      await scrollToTop();
      await screenshot('sc_03_skyeast_new_contracts.jpg');

      // 4. Expand reference files
      await send('Runtime.evaluate', { expression: `
        Array.from(document.querySelectorAll('div')).find(d => d.textContent.trim().startsWith('Reference files'))?.click()
      `});
      await delay(1500);
      await scrollToTop();
      await screenshot('sc_04_skyeast_ref_files.jpg');

      // 5. Contract History
      await send('Runtime.evaluate', { expression: `
        Array.from(document.querySelectorAll('[data-baseweb="tab"]')).find(t => t.textContent.includes('Contract History'))?.click()
      `});
      await delay(2000);
      await scrollToTop();
      await screenshot('sc_06_contract_history.jpg');

      // 6. Missing Fields — filter to only visible tabs (offsetParent != null) to skip hidden GIII sub-tabs
      const { result: missingTabCoords } = await send('Runtime.evaluate', {
        expression: `
          (function() {
            const tab = Array.from(document.querySelectorAll('[data-baseweb="tab"]'))
              .filter(t => t.offsetParent !== null && t.textContent.includes('Missing'))
              .find(t => true);
            if (!tab) return null;
            const r = tab.getBoundingClientRect();
            return { x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2) };
          })()
        `,
        returnByValue: true
      });
      if (missingTabCoords.value) {
        const { x, y } = missingTabCoords.value;
        await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
        await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
      }
      await delay(2000);
      await scrollToTop();
      await screenshot('sc_07_missing_fields.jpg');

      // 7. Colors tab
      await send('Runtime.evaluate', { expression: `
        Array.from(document.querySelectorAll('[data-baseweb="tab"]')).find(t => t.textContent.includes('Colors'))?.click()
      `});
      await delay(3000);
      await scrollToTop();
      await screenshot('sc_08_colors.jpg');

      // 8. Summary tab
      await send('Runtime.evaluate', { expression: `
        Array.from(document.querySelectorAll('[data-baseweb="tab"]')).find(t => t.textContent.includes('Summary'))?.click()
      `});
      await delay(2000);
      await scrollToTop();
      await screenshot('sc_09_summary.jpg');

      console.log('All screenshots done!');
    } catch (err) {
      console.error('Error:', err);
    }

    ws.close();
    chrome.kill();
    process.exit(0);
  });

  ws.addEventListener('message', (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message));
      else resolve(msg.result);
    }
  });

  ws.addEventListener('error', e => { console.error('WS error:', e.message); process.exit(1); });
}

main().catch(e => { console.error(e); process.exit(1); });
