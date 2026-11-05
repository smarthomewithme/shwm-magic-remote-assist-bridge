/* SHWM Magic Remote: proof-of-concept TV-code SSH pairing for Glasshouse.
 * Self-contained ES5 module for Glasshouse's old Node/webOS compatibility.
 * Do NOT expose the one-time TV code through any remote HTTP API.
 * Root SSH access is granted only after the physical TV shows a code which
 * the owner types into Home Assistant. This module does not touch mic or MQTT.
 *
 * Review by the Glasshouse maintainers is required before upstream deployment.
 */
'use strict';
var crypto = require('crypto');

var DEFAULT_TTL_MS = 120000;
var START_COOLDOWN_MS = 15000;
var MAX_ATTEMPTS = 5;

function reject(error) { return { ok: false, error: error }; }

function privateIpv4(address) {
  var ip = String(address || '').replace(/^::ffff:/i, '');
  var parts = ip.split('.');
  if (parts.length !== 4) return false;
  for (var i = 0; i < 4; i++) {
    if (!/^(0|[1-9][0-9]{0,2})$/.test(parts[i]) || +parts[i] > 255) return false;
  }
  var a = +parts[0], b = +parts[1];
  return a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
}

function validateKey(text) {
  if (typeof text !== 'string' || text.length < 70 || text.length > 240 ||
      /[\r\n]/.test(text)) return null;
  var fields = text.trim().split(/\s+/);
  if (fields.length !== 3 || fields[0] !== 'ssh-ed25519' ||
      fields[2] !== 'shwm-magic-remote-assist') return null;
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(fields[1])) return null;
  var blob = new Buffer(fields[1], 'base64'); // webOS old Node compatible
  if (blob.length !== 51 || blob.readUInt32BE(0) !== 11 ||
      blob.toString('ascii', 4, 15) !== 'ssh-ed25519' ||
      blob.readUInt32BE(15) !== 32) return null;
  if (blob.toString('base64') !== fields[1]) return null;
  return {
    line: fields.join(' '),
    fingerprint: 'SHA256:' + crypto.createHash('sha256').update(blob).digest('base64').replace(/=+$/, '')
  };
}

function make(options) {
  options = options || {};
  var clock = options.now || Date.now;
  var random = options.randomBytes || crypto.randomBytes;
  var notify = options.notify;  // fn(message, cb({ok: boolean}))
  var sshKeys = options.sshKeys;
  var canPair = options.canPair || function () { return true; };
  var state = null;
  var lastStart = 0;

  function expired() {
    if (state && clock() >= state.expires) state = null;
  }

  function start(body, peer, cb) {
    expired();
    if (!canPair()) return cb(reject('DISABLED'));
    if (!privateIpv4(peer)) return cb(reject('PRIVATE_IPV4_ONLY'));
    var valid = validateKey(body && body.public_key);
    if (!valid) return cb(reject('INVALID_PUBLIC_KEY'));
    if (!notify || !sshKeys) return cb(reject('NOT_CONFIGURED'));
    if (state) return cb(reject('BUSY'));
    if (lastStart && clock() - lastStart < START_COOLDOWN_MS) return cb(reject('COOLDOWN'));

    var ticket = random(24).toString('hex');
    var codeNumber = random(4).readUInt32BE(0) % 100000000;
    var code = ('00000000' + String(codeNumber)).slice(-8);
    lastStart = clock();
    state = {
      ticket: ticket, code: code, key: valid.line, fingerprint: valid.fingerprint,
      peer: String(peer).replace(/^::ffff:/i, ''), expires: clock() + DEFAULT_TTL_MS,
      attempts: 0, submitting: false
    };

    var message = 'SHWM/HA pairing code: ' + code + ' (2 min). Use on your Home Assistant only.';
    try {
      notify(message, function (result) {
        if (!result || !result.ok) {
          if (state && state.ticket === ticket) state = null;
          return cb(reject('TV_NOTIFICATION_UNAVAILABLE'));
        }
        // The code is *only* in the TV notification; never return it over HTTP.
        cb({ ok: true, ticket: ticket, expires_in: Math.floor(DEFAULT_TTL_MS / 1000) });
      });
    } catch (_e) {
      state = null;
      cb(reject('TV_NOTIFICATION_UNAVAILABLE'));
    }
  }

  function finish(body, peer, cb) {
    expired();
    if (!canPair()) return cb(reject('DISABLED'));
    if (!privateIpv4(peer)) return cb(reject('PRIVATE_IPV4_ONLY'));
    if (!state || !body || typeof body.ticket !== 'string' ||
        body.ticket !== state.ticket ||
        state.peer !== String(peer).replace(/^::ffff:/i, '')) {
      return cb(reject('INVALID_SESSION'));
    }
    if (state.submitting) return cb(reject('IN_PROGRESS'));
    var input = String(body.code || '');
    if (!/^\d{8}$/.test(input) || input !== state.code) {
      state.attempts++;
      if (state.attempts >= MAX_ATTEMPTS) state = null;
      return cb(reject('CODE_INVALID'));
    }

    var active = state;
    active.submitting = true;
    // A successful one-time challenge is consumed BEFORE root key operations.
    state = null;
    try {
      sshKeys.status(function (old) {
        if (!old || old.ok !== true || !Array.isArray(old.keys)) {
          return cb(reject('SSH_STATUS_FAILED'));
        }
        if (old.keys.some(function (k) { return k.fingerprint === active.fingerprint; })) {
          return cb({ ok: true, status: 'ALREADY_PAIRED', fingerprint: active.fingerprint });
        }
        sshKeys.add(active.key, function (r) {
          if (!r || r.ok !== true || !Array.isArray(r.keys) ||
              !r.keys.some(function (k) { return k.fingerprint === active.fingerprint; })) {
            return cb(reject('SSH_ADD_UNVERIFIED'));
          }
          cb({ ok: true, status: 'PAIRED', fingerprint: active.fingerprint });
        });
      });
    } catch (_e) {
      cb(reject('SSH_ADD_UNVERIFIED'));
    }
  }

  function cancel() { state = null; }

  return { start: start, finish: finish, cancel: cancel };
}

module.exports = {
  make: make,
  validateKey: validateKey,
  privateIpv4: privateIpv4,
  DEFAULT_TTL_MS: DEFAULT_TTL_MS
};
