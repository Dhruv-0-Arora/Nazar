'use strict';
/**
 * Records-database client.
 *
 * The connection is opened PER REQUEST and never at boot. That is the whole
 * point of the scenario: with a bad DB_HOST the process still starts cleanly,
 * still binds its port, and still reports `active (running)` to systemd — while
 * every actual patient lookup fails. A boot-time connection check would crash
 * the service and make the bug trivially visible, which is exactly the subtlety
 * we are trying to preserve.
 */

const http = require('node:http');
const pool = require('./pool');

const DB_HOST = process.env.DB_HOST;
const DB_PORT = Number(process.env.DB_PORT || 5432);
const DB_TIMEOUT_MS = Number(process.env.DB_TIMEOUT_MS || 3000);

// CLIN-3117 rollout, paused pending CLIN-3204. Off in every site config.
const FEATURE_ASYNC_RECORDS = process.env.FEATURE_ASYNC_RECORDS === 'true';

class UpstreamError extends Error {
  constructor(message, { code, host, port, correlationId }) {
    super(message);
    this.name = 'UpstreamError';
    this.code = code || 'EUPSTREAM';
    this.host = host;
    this.port = port;
    this.correlationId = correlationId;
  }
}

function target() {
  return { host: DB_HOST, port: DB_PORT };
}

function fetchPatients(query, correlationId) {
  return new Promise((resolve, reject) => {
    if (!DB_HOST) {
      // The empty-env-var bug variant.
      return reject(
        new UpstreamError('DB_HOST is not set', {
          code: 'ECONFIG',
          host: '(unset)',
          port: DB_PORT,
          correlationId,
        })
      );
    }

    const path = query ? `/patients?q=${encodeURIComponent(query)}` : '/patients';

    if (FEATURE_ASYNC_RECORDS) {
      return pool
        .fetchViaPool(DB_HOST, DB_PORT, path)
        .then(resolve)
        .catch((err) =>
          reject(
            new UpstreamError(err.message, {
              code: err.code,
              host: DB_HOST,
              port: DB_PORT,
              correlationId,
            })
          )
        );
    }

    const req = http.request(
      { host: DB_HOST, port: DB_PORT, path, method: 'GET', timeout: DB_TIMEOUT_MS },
      (res) => {
        let body = '';
        res.on('data', (c) => (body += c));
        res.on('end', () => {
          if (res.statusCode !== 200) {
            return reject(
              new UpstreamError(`records database returned HTTP ${res.statusCode}`, {
                code: `EHTTP${res.statusCode}`,
                host: DB_HOST,
                port: DB_PORT,
                correlationId,
              })
            );
          }
          try {
            resolve(JSON.parse(body));
          } catch (err) {
            reject(
              new UpstreamError(`malformed response from records database: ${err.message}`, {
                code: 'EPARSE',
                host: DB_HOST,
                port: DB_PORT,
                correlationId,
              })
            );
          }
        });
      }
    );

    req.on('timeout', () => {
      req.destroy(
        new UpstreamError(`connection to records database timed out after ${DB_TIMEOUT_MS}ms`, {
          code: 'ETIMEDOUT',
          host: DB_HOST,
          port: DB_PORT,
          correlationId,
        })
      );
    });

    req.on('error', (err) => {
      if (err instanceof UpstreamError) return reject(err);
      // ENOTFOUND (stale hostname) / ECONNREFUSED (wrong port, service down)
      reject(
        new UpstreamError(err.message, {
          code: err.code,
          host: DB_HOST,
          port: DB_PORT,
          correlationId,
        })
      );
    });

    req.end();
  });
}

module.exports = { fetchPatients, target, UpstreamError };
