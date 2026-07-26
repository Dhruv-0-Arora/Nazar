#!/usr/bin/env node
'use strict';
/**
 * clinic-portal — serves the patient records portal.
 *
 * Static file server plus a generated /config.json, so the browser learns the
 * backend URL from the environment instead of it being baked into the bundle.
 * BACKEND_URL is the frontend-side bug surface: point it at a host that moved
 * and the portal fails while the backend is perfectly healthy.
 *
 * Node stdlib only.
 */

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const PORT = Number(process.env.PORT || 3000);
const BIND = process.env.BIND || '0.0.0.0';
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8080';
const SERVICE = process.env.SERVICE_NAME || 'clinic-portal';
const VERSION = process.env.SERVICE_VERSION || '1.8.0';
const PUBLIC_DIR = path.join(__dirname, 'public');

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json',
};

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);

  if (url.pathname === '/healthz') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify({ status: 'ok', service: SERVICE, version: VERSION }));
  }

  if (url.pathname === '/config.json') {
    res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    return res.end(JSON.stringify({ backendUrl: BACKEND_URL, service: SERVICE, version: VERSION }));
  }

  const rel = url.pathname === '/' ? 'index.html' : url.pathname.replace(/^\/+/, '');
  const file = path.join(PUBLIC_DIR, rel);

  // Keep traversal out of a service we are about to hand to strangers on a demo box.
  if (!file.startsWith(PUBLIC_DIR + path.sep)) {
    res.writeHead(403, { 'Content-Type': 'text/plain' });
    return res.end('forbidden');
  }

  fs.readFile(file, (err, buf) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      return res.end('not found');
    }
    res.writeHead(200, {
      'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream',
      'Cache-Control': 'no-store',
    });
    res.end(buf);
  });
});

server.listen(PORT, BIND, () => {
  process.stdout.write(
    `${new Date().toISOString()} INFO  [${SERVICE}] listening bind=${BIND}:${PORT} backend=${BACKEND_URL} version=${VERSION}\n`
  );
});

process.on('SIGTERM', () => server.close(() => process.exit(0)));
