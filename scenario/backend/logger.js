'use strict';
/**
 * Append-only file logger.
 *
 * The bundle collector tails LOG_FILE, so this format is load-bearing: the
 * chunker splits log chunks on the timestamp/severity line, and the graph
 * builder regexes error classes and hostnames out of the message body. Keep
 * error class and upstream host as literal tokens on the same line.
 */

const fs = require('node:fs');
const path = require('node:path');

const LOG_FILE = process.env.LOG_FILE || '/var/log/clinic/backend.log';
const SERVICE = process.env.SERVICE_NAME || 'clinic-backend';

let stream = null;

function open() {
  if (stream) return stream;
  try {
    fs.mkdirSync(path.dirname(LOG_FILE), { recursive: true });
    stream = fs.createWriteStream(LOG_FILE, { flags: 'a' });
  } catch (err) {
    process.stderr.write(`[logger] cannot open ${LOG_FILE}: ${err.message}\n`);
  }
  return stream;
}

function write(level, msg, fields = {}) {
  const parts = Object.entries(fields)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${k}=${v}`)
    .join(' ');
  const line = `${new Date().toISOString()} ${level.padEnd(5)} [${SERVICE}] ${msg}${parts ? ' ' + parts : ''}\n`;

  const s = open();
  if (s) s.write(line);
  // journald picks this up too, so `journalctl -u clinic-backend` and the app
  // log tell the same story from two sources — which is what lets the agent
  // cross-reference them.
  process.stdout.write(line);
}

module.exports = {
  logFile: LOG_FILE,
  info: (msg, f) => write('INFO', msg, f),
  warn: (msg, f) => write('WARN', msg, f),
  error: (msg, f) => write('ERROR', msg, f),
};
