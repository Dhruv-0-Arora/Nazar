#!/usr/bin/env node
// Scenario frontend ("the symptom"): serves index.html and proxies /api/*
// to the backend so the browser never has to deal with CORS.
// Node core modules only: http, fs, path. Zero npm dependencies.
//
// Config comes from an env file (KEY=VALUE lines), path given by the
// ENV_FILE environment variable, default ./frontend.env next to this script.
// Real environment variables override file values; file values override defaults.
//
// Keys: PORT (default 8080), BACKEND_URL (default http://127.0.0.1:3001),
//       LOG_FILE (default ./frontend.log next to this script).

'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');

function parseEnvFile(filePath) {
  const out = {};
  let text;
  try {
    text = fs.readFileSync(filePath, 'utf8');
  } catch (err) {
    return out;
  }
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim();
    if (line === '' || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq <= 0) continue;
    out[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
  }
  return out;
}

const envFilePath = path.resolve(
  __dirname,
  process.env.ENV_FILE || path.join(__dirname, 'frontend.env')
);
const fileConfig = parseEnvFile(envFilePath);

function cfg(key, fallback) {
  if (process.env[key] !== undefined && process.env[key] !== '') return process.env[key];
  if (fileConfig[key] !== undefined && fileConfig[key] !== '') return fileConfig[key];
  return fallback;
}

const PORT = parseInt(cfg('PORT', '8080'), 10);
const BACKEND_URL = new URL(cfg('BACKEND_URL', 'http://127.0.0.1:3001'));
const LOG_FILE = path.resolve(__dirname, cfg('LOG_FILE', path.join(__dirname, 'frontend.log')));
const INDEX_HTML = path.join(__dirname, 'index.html');

function log(level, message) {
  const line = `${new Date().toISOString()} ${level} ${message}\n`;
  try {
    fs.appendFileSync(LOG_FILE, line);
  } catch (err) {
    process.stderr.write(`cannot write log file ${LOG_FILE}: ${err.message}\n`);
  }
  process.stdout.write(line);
}

function sendJson(res, status, body) {
  const payload = JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(payload)
  });
  res.end(payload);
}

function proxy(req, res) {
  const options = {
    hostname: BACKEND_URL.hostname,
    port: BACKEND_URL.port || 80,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: BACKEND_URL.host },
    timeout: 5000
  };
  const upstream = http.request(options, (upstreamRes) => {
    res.writeHead(upstreamRes.statusCode, upstreamRes.headers);
    upstreamRes.pipe(res);
  });
  upstream.on('timeout', () => {
    upstream.destroy(new Error('proxy timeout'));
  });
  upstream.on('error', (err) => {
    log('ERROR', `proxy ${req.method} ${req.url} -> ${BACKEND_URL.origin} failed: ${err.message}`);
    if (!res.headersSent) {
      sendJson(res, 502, { error: 'backend unreachable', detail: err.message });
    } else {
      res.destroy();
    }
  });
  req.pipe(upstream);
}

const server = http.createServer((req, res) => {
  const url = req.url.split('?')[0];

  if (url.startsWith('/api/')) {
    proxy(req, res);
    return;
  }

  if (req.method === 'GET' && (url === '/' || url === '/index.html')) {
    fs.readFile(INDEX_HTML, (err, data) => {
      if (err) {
        log('ERROR', `cannot read index.html: ${err.message}`);
        sendJson(res, 500, { error: 'index.html missing' });
        return;
      }
      res.writeHead(200, {
        'Content-Type': 'text/html; charset=utf-8',
        'Content-Length': data.length
      });
      res.end(data);
    });
    return;
  }

  sendJson(res, 404, { error: 'not found' });
});

server.listen(PORT, () => {
  log(
    'INFO',
    `frontend started on port ${PORT} (env_file=${envFilePath} backend=${BACKEND_URL.origin} log=${LOG_FILE})`
  );
});
