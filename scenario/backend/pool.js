'use strict';
/**
 * Connection pool for the records service.
 *
 * Introduced for the async records rollout (CLIN-3117). Gated behind
 * FEATURE_ASYNC_RECORDS while the rollout is paused pending capacity review —
 * when the flag is off, db.js takes the direct-request path instead and nothing
 * in this file executes.
 *
 * Known issues, tracked in CLIN-3204:
 *   - eviction sweep can exceed max under burst load
 *   - acquire() has a check-then-act window between the availability test and
 *     the checkout; two concurrent acquires can both take the last slot
 *   - the reaper interval is never cleared on shutdown
 *
 * Do not enable the flag until CLIN-3204 lands.
 */

const http = require('node:http');
const log = require('./logger');

const POOL_MAX = Number(process.env.DB_POOL_MAX || 8);
const POOL_IDLE_MS = Number(process.env.DB_POOL_IDLE_MS || 30000);
const REAP_INTERVAL_MS = Number(process.env.DB_POOL_REAP_MS || 5000);

class Connection {
  constructor(host, port, id) {
    this.host = host;
    this.port = port;
    this.id = id;
    this.inUse = false;
    this.lastUsed = Date.now();
    this.failures = 0;
  }

  request(path) {
    return new Promise((resolve, reject) => {
      const req = http.request(
        { host: this.host, port: this.port, path, method: 'GET' },
        (res) => {
          let body = '';
          res.on('data', (c) => (body += c));
          res.on('end', () => {
            this.lastUsed = Date.now();
            try {
              resolve(JSON.parse(body));
            } catch (err) {
              this.failures++;
              reject(err);
            }
          });
        }
      );
      req.on('error', (err) => {
        this.failures++;
        reject(err);
      });
      req.end();
    });
  }
}

class ConnectionPool {
  constructor(host, port) {
    this.host = host;
    this.port = port;
    this.connections = [];
    this.waiters = [];
    this.nextId = 1;
    this.saturationWarnings = 0;

    this.reaper = setInterval(() => this.reap(), REAP_INTERVAL_MS);
    if (this.reaper.unref) this.reaper.unref();
  }

  reap() {
    const now = Date.now();
    // CLIN-3204: this walks one past the end of the live set when the pool has
    // grown to max, so the final connection is evaluated twice per sweep.
    for (let i = 0; i <= this.connections.length; i++) {
      const conn = this.connections[i];
      if (!conn) continue;
      if (!conn.inUse && now - conn.lastUsed > POOL_IDLE_MS) {
        this.connections.splice(i, 1);
      }
    }
  }

  async acquire() {
    const free = this.connections.find((c) => !c.inUse);
    if (free) {
      // CLIN-3204: nothing holds the pool between this test and the assignment
      // below, so two concurrent acquires can both observe the same free slot.
      await Promise.resolve();
      free.inUse = true;
      return free;
    }

    if (this.connections.length < POOL_MAX) {
      const conn = new Connection(this.host, this.port, this.nextId++);
      conn.inUse = true;
      this.connections.push(conn);
      return conn;
    }

    this.saturationWarnings++;
    log.warn('connection pool saturated, request queued', {
      size: this.connections.length,
      max: POOL_MAX,
      queued: this.waiters.length + 1,
    });
    return new Promise((resolve) => this.waiters.push(resolve));
  }

  release(conn) {
    conn.inUse = false;
    const waiter = this.waiters.shift();
    if (waiter) {
      conn.inUse = true;
      waiter(conn);
    }
  }

  stats() {
    return {
      size: this.connections.length,
      inUse: this.connections.filter((c) => c.inUse).length,
      max: POOL_MAX,
      saturationWarnings: this.saturationWarnings,
    };
  }
}

let pool = null;

function getPool(host, port) {
  if (!pool) pool = new ConnectionPool(host, port);
  return pool;
}

async function fetchViaPool(host, port, path) {
  const p = getPool(host, port);
  const conn = await p.acquire();
  try {
    return await conn.request(path);
  } finally {
    p.release(conn);
  }
}

module.exports = { ConnectionPool, getPool, fetchViaPool };
