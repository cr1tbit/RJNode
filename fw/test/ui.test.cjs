const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

test('relay controls and Wi-Fi setup, status, failure and recovery', async () => {
  const html = fs.readFileSync(path.join(__dirname, '../src/index.html'), 'utf8');
  const elements = {};
  for (const [, id] of html.matchAll(/id="([^"]+)"/g)) {
    elements[id] = {
      textContent: '', value: '', disabled: false, hidden: false, handlers: {},
      setAttribute(name, value) { this[name] = value; },
      removeAttribute(name) { delete this[name]; },
      addEventListener(event, handler) { this.handlers[event] = handler; }
    };
  }
  let wifi = { enabled: false, configured: false, state: 'disabled', ssid: '', ip: '',
    via_wifi: false, rssi_dbm: null, channel: null, disconnects: 0,
    last_disconnect_reason: 0, error: '', connected_s: 0 };
  const relays = [false, false];
  const intervals = [];
  const sent = [];
  let offline = false;
  vm.runInNewContext(html.split('<script>')[1].split('</script>')[0], {
    document: { getElementById: id => elements[id] },
    AbortSignal, performance,
    setInterval(callback) { intervals.push(callback); },
    async fetch(url, options) {
      if (offline) throw new Error('Network unavailable');
      if (options.method === 'POST') {
        assert.equal(options.headers['X-RJNode-Control'], '1');
        if (url === '/api/wifi') {
          const config = JSON.parse(options.body);
          sent.push(config);
          wifi = config.forget ? { ...wifi, enabled: false, configured: false, state: 'disabled',
            ssid: '', ip: '', rssi_dbm: null, channel: null, connected_s: 0, via_wifi: false } :
            { ...wifi, enabled: true, configured: true, state: 'connecting', ssid: config.ssid };
          return { ok: true, json: async () => ({ accepted: true }) };
        }
        relays[Number(url.slice(-1)) - 1] = options.body === '1';
      }
      return { ok: true, json: async () => url === '/api/wifi' ? { ...wifi } : { relays: [...relays] } };
    }
  });
  const settle = () => new Promise(resolve => setImmediate(resolve));
  const poll = async () => {
    await Promise.all(intervals.map(callback => callback()));
    await settle();
  };
  await settle();
  assert.equal(elements['wifi-state'].textContent, 'Disabled');
  assert.equal(elements.forget.disabled, true);
  assert.equal(elements.state1.textContent, 'OFF');

  await elements.relay1.handlers.click();
  await elements.relay2.handlers.click();
  assert.deepEqual(relays, [true, true]);
  await elements.relay1.handlers.click();
  assert.deepEqual(relays, [false, true]);

  elements.ssid.value = 'Test network';
  elements.password.value = 'test-only-password';
  elements['wifi-form'].handlers.submit({ preventDefault() {} });
  await settle();
  assert.deepEqual(sent[0], { ssid: 'Test network', password: 'test-only-password' });
  assert.equal(elements.password.value, '');
  await poll();
  assert.equal(elements['wifi-state'].textContent, 'Connecting…');
  assert.equal(elements.forget.disabled, false);

  wifi = { ...wifi, state: 'connected', ip: '192.168.88.123', rssi_dbm: -65,
    channel: 6, connected_s: 20, via_wifi: true };
  await poll();
  assert.equal(elements['wifi-signal'].textContent, '-65 dBm / 6');
  assert.equal(elements['wifi-address'].href, 'http://192.168.88.123/');
  assert.equal(elements['wifi-path'].textContent, 'Wi-Fi');
  assert.equal(elements['wifi-duration'].textContent, '20 s');

  offline = true;
  await poll();
  assert.equal(elements['wifi-signal'].textContent, 'Unknown');
  assert.equal(elements['wifi-failures'].textContent, '1');
  assert.equal(elements.relay1.disabled, true);
  assert.equal(elements.forget.disabled, true);
  offline = false;
  await poll();
  assert.equal(elements['wifi-signal'].textContent, '-65 dBm / 6');
  assert.equal(elements.relay1.disabled, false);

  elements.forget.handlers.click();
  await settle();
  await poll();
  assert.deepEqual(sent.at(-1), { forget: true });
  assert.equal(elements['wifi-state'].textContent, 'Disabled');
  assert.equal(elements['wifi-address'].hidden, true);
  assert.equal(elements['wifi-address'].href, undefined);
  assert.equal(elements.ssid.value, '');
  assert.equal(elements.forget.disabled, true);
});
