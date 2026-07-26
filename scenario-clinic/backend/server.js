#!/usr/bin/env node
'use strict';
/**
 * clinic-backend — patient records API for the portal.
 *
 * Reads config from the environment (systemd EnvironmentFile=/etc/clinic/backend.env).
 * Node stdlib only.
 *
 * SYMPTOM CHAIN THIS SERVICE IS BUILT TO PRODUCE:
 *   1. `systemctl status clinic-backend` -> active (running)
 *   2. `curl /healthz`                   -> 200 ok
 *   3. `curl /api/patients`              -> 502, and an ERROR line in the app log
 * Health is intentionally shallow. Anything that probes the DB from /healthz
 * would give the bug away for free.
 */

const http = require('node:http');
const crypto = require('node:crypto');
const log = require('./logger');
const db = require('./db');
const maintenance = require('./maintenance');

const PORT = Number(process.env.PORT || 8080);
const BIND = process.env.BIND || '0.0.0.0';
const SERVICE = process.env.SERVICE_NAME || 'clinic-backend';
const VERSION = process.env.SERVICE_VERSION || '2.4.1';

let lastUpstreamSuccess = null;

function send(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': Buffer.byteLength(body),
    // The portal is served from another host, so the browser preflights.
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
  });
  res.end(body);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const correlationId = crypto.randomBytes(4).toString('hex');

  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'GET,OPTIONS',
    });
    return res.end();
  }

  // Shallow by design — see the header comment.
  if (url.pathname === '/healthz') {
    return send(res, 200, { status: 'ok', service: SERVICE, version: VERSION });
  }

  // Lets the portal's status bar name the upstream it depends on without
  // guessing. Also the first thing an FDE hits when triaging by hand.
  if (url.pathname === '/api/meta') {
    const t = db.target();
    return send(res, 200, {
      service: SERVICE,
      version: VERSION,
      pid: process.pid,
      uptimeSeconds: Math.round(process.uptime()),
      upstream: { host: t.host || '(unset)', port: t.port },
      lastUpstreamSuccess,
      logFile: log.logFile,
    });
  }

  if (url.pathname === '/api/patients') {
    const q = url.searchParams.get('q') || '';
    const started = Date.now();
    try {
      const data = await db.fetchPatients(q, correlationId);
      lastUpstreamSuccess = new Date().toISOString();
      log.info('patient query served', {
        cid: correlationId,
        results: data.count,
        ms: Date.now() - started,
      });
      return send(res, 200, data);
    } catch (err) {
      // One line, all the identifiers: error class, upstream host:port, cid.
      // The portal renders these verbatim and the collector ships this file, so
      // the string on the FDE's screen is the string in the bundle.
      log.error('records database unreachable', {
        cid: correlationId,
        err: err.code,
        upstream: `${err.host}:${err.port}`,
        detail: JSON.stringify(err.message),
        ms: Date.now() - started,
      });
      return send(res, 502, {
        error: 'records_database_unreachable',
        code: err.code,
        upstream: { host: err.host, port: err.port },
        correlationId,
        detail: err.message,
      });
    }
  }

  send(res, 404, { error: 'not_found' });
});

server.listen(PORT, BIND, () => {
  const t = db.target();
  log.info('service started', {
    version: VERSION,
    bind: `${BIND}:${PORT}`,
    upstream: `${t.host || '(unset)'}:${t.port}`,
    pid: process.pid,
  });
  // Note what is NOT here: no upstream reachability check at boot.
  maintenance.start();
});

process.on('SIGTERM', () => {
  log.info('received SIGTERM, shutting down');
  server.close(() => process.exit(0));
});
