#!/usr/bin/env node
// Scenario backend ("the patient").
// Node core modules only: http, net, fs, path. Zero npm dependencies.
//
// Config comes from an env file (KEY=VALUE lines), path given by the
// ENV_FILE environment variable, default ./backend.env next to this script.
// Real environment variables override file values; file values override defaults.
//
// Keys: PORT (default 3001), DB_HOST, DB_PORT (default 5432),
//       LOG_FILE (default ./backend.log next to this script).

'use strict';

const http = require('http');
const net = require('net');
const fs = require('fs');
const path = require('path');

function parseEnvFile(filePath) {
  const out = {};
  let text;
  try {
    text = fs.readFileSync(filePath, 'utf8');
  } catch (err) {
    return out; // missing env file -> defaults only
  }
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim();
    if (line === '' || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim();
    out[key] = value;
  }
  return out;
}

const envFilePath = path.resolve(
  __dirname,
  process.env.ENV_FILE || path.join(__dirname, 'backend.env')
);
const fileConfig = parseEnvFile(envFilePath);

function cfg(key, fallback) {
  if (process.env[key] !== undefined && process.env[key] !== '') return process.env[key];
  if (fileConfig[key] !== undefined && fileConfig[key] !== '') return fileConfig[key];
  return fallback;
}

const PORT = parseInt(cfg('PORT', '3001'), 10);
const DB_HOST = cfg('DB_HOST', '127.0.0.1');
const DB_PORT = parseInt(cfg('DB_PORT', '5432'), 10);
const LOG_FILE = path.resolve(__dirname, cfg('LOG_FILE', path.join(__dirname, 'backend.log')));

function log(level, message) {
  const line = `${new Date().toISOString()} ${level} ${message}\n`;
  try {
    fs.appendFileSync(LOG_FILE, line);
  } catch (err) {
    process.stderr.write(`cannot write log file ${LOG_FILE}: ${err.message}\n`);
  }
  process.stdout.write(line);
}

// Fake rows returned when the database connection succeeds.
const FAKE_ROWS = [
  { id: 1, sku: 'WDG-001', name: 'widget', qty: 42 },
  { id: 2, sku: 'SPK-007', name: 'sprocket', qty: 7 },
  { id: 3, sku: 'GRM-113', name: 'grommet', qty: 113 }
];

// Attempt a raw TCP connection to the database with a 2 s timeout.
function checkDb(callback) {
  const socket = net.connect({ host: DB_HOST, port: DB_PORT });
  let settled = false;
  const settle = (err) => {
    if (settled) return;
    settled = true;
    socket.destroy();
    callback(err);
  };
  socket.setTimeout(2000);
  socket.on('connect', () => settle(null));
  socket.on('timeout', () => {
    const err = new Error(`connect ETIMEDOUT ${DB_HOST}:${DB_PORT}`);
    err.code = 'ETIMEDOUT';
    settle(err);
  });
  socket.on('error', (err) => settle(err));
}

function sendJson(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(payload)
  });
  res.end(payload);
}

const server = http.createServer((req, res) => {
  const url = req.url.split('?')[0];

  if (req.method === 'GET' && url === '/api/health') {
    sendJson(res, 200, { status: 'ok' });
    return;
  }

  if (req.method === 'GET' && url === '/api/items') {
    checkDb((err) => {
      if (err) {
        const code = err.code || 'ECONNFAILED';
        log('ERROR', `db connect failed: connect ${code} ${DB_HOST}:${DB_PORT}`);
        sendJson(res, 500, { error: 'database unavailable' });
      } else {
        log('INFO', `GET /api/items 200 (${FAKE_ROWS.length} rows, db ${DB_HOST}:${DB_PORT})`);
        sendJson(res, 200, { rows: FAKE_ROWS });
      }
    });
    return;
  }

  sendJson(res, 404, { error: 'not found' });
});

server.listen(PORT, () => {
  log(
    'INFO',
    `backend started on port ${PORT} (env_file=${envFilePath} DB_HOST=${DB_HOST} DB_PORT=${DB_PORT} log=${LOG_FILE})`
  );
});
