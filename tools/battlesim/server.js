"use strict";
// Long-lived battle-forecast sidecar. Reads newline-delimited JSON-RPC requests
// on stdin, writes one JSON response line per request on stdout. ALL diagnostics
// go to stderr — stdout carries only protocol frames.
//
// Request:  {"id":<n>,"method":"ping"|"forecast","params":<obj>}
// Response: {"id":<n>,"result":<obj>}  or  {"id":<n>,"error":{"message":<str>}}

const readline = require("readline");
const { forecast } = require("./forecast");

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

function handle(msg) {
  const { id, method, params } = msg;
  if (method === "ping") return { id, result: "pong" };
  if (method === "forecast") return { id, result: forecast(params || {}) };
  return { id, error: { message: "unknown method: " + method } };
}

const rl = readline.createInterface({ input: process.stdin, terminal: false });
rl.on("line", (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  let msg;
  try {
    msg = JSON.parse(trimmed);
  } catch (e) {
    send({ id: null, error: { message: "bad JSON: " + e.message } });
    return;
  }
  try {
    send(handle(msg));
  } catch (e) {
    send({ id: msg && msg.id != null ? msg.id : null, error: { message: String(e && e.message || e) } });
  }
});
rl.on("close", () => process.exit(0));

process.stderr.write("[battlesim] sidecar ready\n");
