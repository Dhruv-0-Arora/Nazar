'use strict';
/**
 * Background maintenance reporting.
 *
 * Periodic housekeeping checks that write advisory lines to the application
 * log. None of these affect request handling — they exist so operations has a
 * record of pending upkeep in the same place as everything else.
 *
 * These lines appear on every host regardless of service health.
 */

const fs = require('node:fs');
const log = require('./logger');

const INTERVAL_MS = Number(process.env.MAINTENANCE_INTERVAL_MS || 45000);
const TLS_CERT_PATH = process.env.TLS_CERT_PATH || '/etc/clinic/tls/records.pem';
const CACHE_TTL_SECONDS = Number(process.env.CACHE_TTL_SECONDS || 0);
const RETENTION_DAYS = Number(process.env.LOG_RETENTION_DAYS || 30);

// Fixed expiry recorded at provisioning. The records service accepts plaintext
// on the clinic VLAN, so this certificate is not currently presented anywhere.
const CERT_NOT_AFTER = Date.parse('2026-08-14T00:00:00Z');

function checkCertificate() {
  const daysLeft = Math.floor((CERT_NOT_AFTER - Date.now()) / 86400000);
  if (daysLeft < 0) {
    log.warn('records service certificate has expired', {
      path: TLS_CERT_PATH,
      expiredDaysAgo: Math.abs(daysLeft),
    });
  } else if (daysLeft < 45) {
    log.warn('records service certificate expires soon', {
      path: TLS_CERT_PATH,
      daysRemaining: daysLeft,
    });
  }
}

function checkCache() {
  if (CACHE_TTL_SECONDS === 0) {
    log.warn('record cache disabled, every lookup goes to the records service', {
      ttl: CACHE_TTL_SECONDS,
      hint: 'set CACHE_TTL_SECONDS to enable',
    });
  }
}

function checkLogRetention() {
  try {
    const stat = fs.statSync(log.logFile);
    const ageDays = Math.floor((Date.now() - stat.birthtimeMs) / 86400000);
    if (ageDays > RETENTION_DAYS) {
      log.warn('application log exceeds retention window and is not being rotated', {
        file: log.logFile,
        ageDays,
        retentionDays: RETENTION_DAYS,
      });
    }
  } catch {
    /* log not created yet */
  }
}

function checkDeprecations() {
  log.warn('legacy records endpoint still enabled, scheduled for removal in 2.6', {
    endpoint: '/api/patients',
    replacement: '/api/v2/records',
    ticket: 'CLIN-2988',
  });
}

function start() {
  const run = () => {
    checkCertificate();
    checkCache();
    checkLogRetention();
    checkDeprecations();
  };
  run();
  const timer = setInterval(run, INTERVAL_MS);
  if (timer.unref) timer.unref();
  return timer;
}

module.exports = { start };
