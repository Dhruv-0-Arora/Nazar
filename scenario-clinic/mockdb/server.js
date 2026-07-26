#!/usr/bin/env node
'use strict';
/**
 * clinic-mockdb — stands in for the records database.
 *
 * Deliberately dumb: reads a JSON file, serves it over HTTP. It exists so the
 * backend has a real network dependency to lose. Node stdlib only — the demo
 * premise is a dead network, so nothing here may require `npm install`.
 */

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const PORT = Number(process.env.MOCKDB_PORT || 5432);
const HOST = process.env.MOCKDB_BIND || '0.0.0.0';
const DATA_FILE = process.env.MOCKDB_DATA || path.join(__dirname, 'patients.json');

function loadPatients() {
  const raw = fs.readFileSync(DATA_FILE, 'utf8');
  return JSON.parse(raw).patients;
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  res.setHeader('Content-Type', 'application/json');

  if (url.pathname === '/healthz') {
    res.writeHead(200);
    return res.end(JSON.stringify({ status: 'ok', service: 'clinic-mockdb' }));
  }

  if (url.pathname === '/patients') {
    let patients;
    try {
      patients = loadPatients();
    } catch (err) {
      // Surfaces the malformed-JSON bug variant if inject.sh corrupts the data file.
      process.stderr.write(`[mockdb] failed to read ${DATA_FILE}: ${err.message}\n`);
      res.writeHead(500);
      return res.end(JSON.stringify({ error: 'datafile_unreadable', detail: err.message }));
    }
    const q = (url.searchParams.get('q') || '').trim().toLowerCase();
    const filtered = q
      ? patients.filter((p) => p.name.toLowerCase().includes(q) || p.mrn.toLowerCase().includes(q))
      : patients;
    res.writeHead(200);
    return res.end(JSON.stringify({ count: filtered.length, patients: filtered }));
  }

  res.writeHead(404);
  res.end(JSON.stringify({ error: 'not_found' }));
});

server.listen(PORT, HOST, () => {
  process.stdout.write(`[mockdb] listening on ${HOST}:${PORT}, data=${DATA_FILE}\n`);
});
