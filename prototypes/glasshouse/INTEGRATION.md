# Glasshouse SSH pairing via TV code — contribution proposal

**Status: Prototype only. Not merged into Glasshouse and NOT installed on LG.**

The standard Glasshouse endpoint POST /api/ssh deliberately requires an administrator
token and never discloses it over HTTP. This proposal avoids accessing that token.

## API (new optional routes)

1. SHWM HA app POST /api/shwm-pair/request with JSON public_key (canonical
   ed25519, shwm-magic-remote-assist marker). Glasshouse validates and generates
   24 random bytes for a one-time ticket and an 8-digit PIN. It sends the PIN
   ONLY to the LG screen using its webOS notification service, not to the API
   response. The response returns ticket and 120 second expiry.
2. Owner reads the 8 digits from the LG screen and enters the PIN in the HA app.
3. HA app POST /api/shwm-pair/complete with ticket and code from the same
   private-LAN IP. Glasshouse validates the single-use challenge (5 tries
   maximum, 2 minute TTL) before adding only the approved public key.
4. Glasshouse calls its existing sshKeys.add and verifies the SHA256 fingerprint.
   The existing /api/ssh token protection stays in place.

This is opt-in via explicit user interaction in HA and physical LG presence.
It uses no SSH root password, copied private key, telnet or Glasshouse token.
The module does not alter MQTT, the remote buttons or the audio pipeline.

## Upstream integration touchpoints

The ES5 module in shwm-pairing.js is designed for Glasshouse old-Node support.
Copy it to the official Glasshouse server/lib/shwm-pairing.js after maintainer
review. In server/lib/routes.js, require the module alongside sshkeys.js,
initialize it inside init() AFTER config/controls/sshKeys have been set:

    var pairFactory = require('./shwm-pairing');
    var shwmPairingInstance = pairFactory.make({
      sshKeys: sshKeysModule,
      canPair: function () { return !!config.allowControl; },
      notify: function (message, cb) {
        controlsModule.doControl('toast', message, cb);
      }
    });

Inside handleRequest, immediately before the global /api/ token guard, route
ONLY two new pre-auth POST paths. Use the EXISTING readJsonBody size-limited
parser, reject non-JSON content types and all non-POST methods:

    if (pathname === '/api/shwm-pair/request' ||
        pathname === '/api/shwm-pair/complete') {
      if (req.method !== 'POST')
        return send(res,405,JSON.stringify({ok:false,error:'METHOD_NOT_ALLOWED'}));
      if (!shwmPairingInstance)
        return send(res,503,JSON.stringify({ok:false,error:'UNAVAILABLE'}));
      if (!/^application\/json(?:;|$)/i.test(req.headers['content-type'] || ''))
        return send(res,415,JSON.stringify({ok:false,error:'JSON_REQUIRED'}));
      return readJsonBody(req,res,function(body) {
        var reply=function(result) {
          send(res,result.ok?200:400,JSON.stringify(result));
        };
        var peer=req.socket.remoteAddress;
        if (pathname === '/api/shwm-pair/request')
          return shwmPairingInstance.start(body,peer,reply);
        return shwmPairingInstance.finish(body,peer,reply);
      });
    }

Do not weaken Glasshouse global API auth nor expose the TV PIN in remote
responses or logs. Existing /api/ssh remains protected. Do not use fromTV(req)
alone as proof of physical ownership: Glasshouse explicitly warns that pages
and apps on the television can also originate from loopback. The owner must
read a code shown physically on the TV.

## Security and UX checks before release

- Obtain upstream maintainer security review and approval before patching Glasshouse.
- Confirm notification display on the specific LG webOS versions. A short toast
  may disappear too quickly; use a dedicated on-TV prompt if needed.
- Verify old Node support (including webOS 4), Homebrew SSH and permissions.
- Add tests upstream: PIN expiry, 5 wrong attempts, rate limiting, IP binding,
  no duplicate key, no loss of old keys, locked API, restart/cancel semantics.
- Consider a dedicated temporary pairing enable switch in Glasshouse.
- Confirm no root operation occurs on request; only after code verification.
- Keep production Glasshouse and HA addon unchanged during proposal review.

The SHWM addon on main remains 0.1.5; it does not support this protocol yet.
