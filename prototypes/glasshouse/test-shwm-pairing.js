/* Minimal Node-only tests for proposed Glasshouse TV-code pairing. */
'use strict';
var assert = require('assert');
var crypto = require('crypto');
var protocol = require('./shwm-pairing');

var raw = new Buffer(51);
raw.writeUInt32BE(11, 0);
raw.write('ssh-ed25519', 4, 'ascii');
raw.writeUInt32BE(32, 15);
for (var i = 19; i < 51; i++) raw[i] = 123;
var key = 'ssh-ed25519 ' + raw.toString('base64') + ' shwm-magic-remote-assist';
var keyData = protocol.validateKey(key);
assert.ok(keyData);
assert.ok(/^SHA256:/.test(keyData.fingerprint));
assert.strictEqual(protocol.validateKey(key + '\ncommand'), null);
assert.strictEqual(protocol.validateKey(key.replace('shwm-magic-remote-assist', 'bad-label')), null);
assert.strictEqual(protocol.validateKey('ssh-rsa abc shwm-magic-remote-assist'), null);
assert.strictEqual(protocol.privateIpv4('192.168.1.101'), true);
assert.strictEqual(protocol.privateIpv4('::ffff:10.1.2.3'), true);
assert.strictEqual(protocol.privateIpv4('8.8.8.8'), false);
assert.strictEqual(protocol.privateIpv4('127.0.0.1'), false);

var now = 1000000;
var messages = [];
var keys = [];
var addons = 0;
var fakeSsh = {
  status: function (cb) { cb({ ok: true, keys: keys }); },
  add: function (line, cb) {
    addons++;
    assert.strictEqual(line, key);
    keys.push({ fingerprint: keyData.fingerprint });
    cb({ ok: true, keys: keys });
  }
};
function make() {
  return protocol.make({
    now: function () { return now; },
    notify: function (msg, cb) { messages.push(msg); cb({ok: true}); },
    sshKeys: fakeSsh
  });
}
var bridge = make();
var ticket;
bridge.start({public_key: key}, '192.168.1.101', function (r) {
  assert.strictEqual(r.ok, true);
  assert.strictEqual(typeof r.ticket, 'string');
  assert.strictEqual(r.code, undefined);
  ticket = r.ticket;
});
var receivedCode = /code: (\d{8})/.exec(messages[0])[1];
bridge.start({public_key: key}, '192.168.1.102', function (r) {assert.strictEqual(r.error, 'BUSY');});
bridge.finish({ticket: ticket, code: receivedCode}, '192.168.1.102', function (r) {assert.strictEqual(r.error, 'INVALID_SESSION');});
bridge.finish({ticket: ticket, code: '0000000x'}, '192.168.1.101', function (r) {assert.strictEqual(r.error, 'CODE_INVALID');});
bridge.finish({ticket: ticket, code: receivedCode}, '192.168.1.101', function (r) {
  assert.strictEqual(r.status, 'PAIRED');
  assert.strictEqual(r.fingerprint, keyData.fingerprint);
});
assert.strictEqual(addons, 1);
bridge.finish({ticket: ticket, code: receivedCode}, '192.168.1.101', function (r) {assert.strictEqual(r.error, 'INVALID_SESSION');});

now += 16000;
bridge.start({public_key: key}, '192.168.1.101', function (r) {ticket = r.ticket;});
var secondCode = /code: (\d{8})/.exec(messages[1])[1];
bridge.finish({ticket: ticket, code: secondCode}, '192.168.1.101', function (r) {assert.strictEqual(r.status, 'ALREADY_PAIRED');});
assert.strictEqual(addons, 1);

now += 16000;
bridge.start({public_key: key}, '192.168.1.101', function (r) {ticket = r.ticket;});
var attempts = 0;
for (var n = 0; n < 5; n++) {
  bridge.finish({ticket:ticket, code:'invalid'}, '192.168.1.101', function(r) {
    assert.strictEqual(r.error,'CODE_INVALID');
    attempts++;
  });
}
assert.strictEqual(attempts, 5);
bridge.finish({ticket: ticket, code: /code: (\d{8})/.exec(messages[2])[1]}, '192.168.1.101', function(r){assert.strictEqual(r.error,'INVALID_SESSION');});

now += 16000;
bridge.start({public_key: key}, '192.168.1.101', function (r) {ticket = r.ticket;});
now += 121000;
bridge.finish({ticket:ticket,code:/code: (\d{8})/.exec(messages[3])[1]}, '192.168.1.101', function(r){assert.strictEqual(r.error,'INVALID_SESSION');});
var failedToast = protocol.make({
  now: function(){return now;},
  notify: function(msg,cb){cb({ok:false});},
  sshKeys: fakeSsh
});
failedToast.start({public_key:key}, '192.168.1.101', function(r){assert.strictEqual(r.error,'TV_NOTIFICATION_UNAVAILABLE');});
assert.strictEqual(addons,1);
console.log('Glasshouse SHWM pairing proof tests: OK');
