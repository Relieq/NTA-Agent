/*
 * Frida hook to recover the Cocos Creator XXTEA decryption key for NTA.
 *
 * The engine calls jsb_set_xxtea_key(const std::string&) once at boot, and
 * xxtea_decrypt(...) for every encrypted .jsc it loads. We hook both: the
 * former gives the key directly, the latter is a backstop that also reveals
 * the key argument on each decrypt call.
 *
 * Run (spawns the game so we catch the boot-time call):
 *   frida -U -f twgame.global.acers -l hook_xxtea.js
 */
'use strict';

// Read a libc++ (__ndk1) std::string from a pointer.
function readStdString(ptr_) {
  const p = ptr(ptr_);
  const first = p.readU8();
  if ((first & 1) === 0) {
    // short string: size = first>>1, data starts at p+1
    const len = first >> 1;
    return p.add(1).readUtf8String(len);
  }
  // long string: [cap][size][data*]
  const size = p.add(Process.pointerSize).readU64();
  const dataPtr = p.add(Process.pointerSize * 2).readPointer();
  return dataPtr.readUtf8String(size.toNumber());
}

function hexPreview(ptr_, n) {
  try { return hexdump(ptr(ptr_), { length: n, ansi: false }); }
  catch (e) { return '<unreadable>'; }
}


function waitForModule(name, cb) {
  var existing = Process.findModuleByName(name);
  if (existing) { cb(existing); return; }
  var done = false;
  var dlopen;
  try { dlopen = Module.getGlobalExportByName('android_dlopen_ext'); }
  catch (e) { dlopen = Module.getGlobalExportByName('dlopen'); }
  console.log('[*] waiting for ' + name + ' via ' + dlopen);
  Interceptor.attach(dlopen, {
    onLeave: function () {
      if (done) return;
      var m = Process.findModuleByName(name);
      if (m) { done = true; console.log('[*] ' + name + ' loaded'); cb(m); }
    }
  });
}

function main() {
  waitForModule('libcocos2djs.so', installHooks);
}

function installHooks(mod) {
  console.log('[*] libcocos2djs.so @ ' + mod.base + ' size=' + mod.size);

  const exps = mod.enumerateExports();
  const xxteaExps = exps.filter(function (e) {
    return e.name.toLowerCase().indexOf('xxtea') >= 0;
  });
  console.log('[*] xxtea exports: ' + JSON.stringify(xxteaExps.map(function (e) { return e.name; })));

  // 1) jsb_set_xxtea_key(const std::string&)
  const setKey = xxteaExps.find(function (e) { return e.name.indexOf('jsb_set_xxtea_key') >= 0; });
  if (setKey) {
    Interceptor.attach(setKey.address, {
      onEnter: function (args) {
        try {
          const key = readStdString(args[0]);
          console.log('\n========================================');
          console.log('[XXTEA KEY] "' + key + '"  (len=' + key.length + ')');
          console.log('========================================\n');
        } catch (e) {
          console.log('[!] set_key read failed: ' + e + '\n' + hexPreview(args[0], 32));
        }
      }
    });
    console.log('[+] hooked jsb_set_xxtea_key @ ' + setKey.address);
  } else {
    console.log('[!] jsb_set_xxtea_key export not found');
  }

  // 2) xxtea_decrypt(unsigned char* data, xxtea_long len, unsigned char* key, xxtea_long keylen, xxtea_long* out)
  const dec = xxteaExps.find(function (e) { return e.name.indexOf('xxtea_decrypt') >= 0; });
  if (dec) {
    let shown = 0;
    Interceptor.attach(dec.address, {
      onEnter: function (args) {
        if (shown++ > 3) return;
        try {
          const keylen = args[3].toInt32();
          const key = args[2].readUtf8String(keylen);
          console.log('[xxtea_decrypt] datalen=' + args[1].toInt32() +
                      ' keylen=' + keylen + ' key="' + key + '"');
        } catch (e) {
          console.log('[xxtea_decrypt] key(hex):\n' + hexPreview(args[2], 24));
        }
      }
    });
    console.log('[+] hooked xxtea_decrypt @ ' + dec.address);
  }
}

setImmediate(main);
