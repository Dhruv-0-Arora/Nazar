#!/usr/bin/env node
// Mock database ("the database" that lives on the backend host).
// A trivial TCP server: accepts a connection, writes a short banner, closes.
// Node core modules only. Port: MOCK_DB_PORT env var, default 5432.

'use strict';

const net = require('net');

const PORT = parseInt(process.env.MOCK_DB_PORT || '5432', 10);

const server = net.createServer((socket) => {
  socket.on('error', () => {}); // client may hang up first; not our problem
  socket.end('MOCKDB/1.0 ready\n');
});

server.listen(PORT, () => {
  process.stdout.write(`${new Date().toISOString()} INFO mock-db listening on port ${PORT}\n`);
});
