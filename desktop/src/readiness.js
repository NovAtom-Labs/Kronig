"use strict";

const MAX_READINESS_BYTES = 16 * 1024;

function readinessError(message) {
  return new Error(`Invalid backend readiness record: ${message}`);
}

function parseReadinessLine(line) {
  if (typeof line !== "string") throw readinessError("output must be text");
  if (Buffer.byteLength(line, "utf8") > MAX_READINESS_BYTES) {
    throw readinessError("record exceeds the 16 KiB size limit");
  }

  let value;
  try {
    value = JSON.parse(line);
  } catch {
    throw readinessError("record is not JSON");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw readinessError("record must be an object");
  }
  if (value.protocol !== 1) throw readinessError("unsupported protocol");
  if (!Number.isSafeInteger(value.pid) || value.pid <= 0) {
    throw readinessError("PID must be a positive integer");
  }
  if (value.owner_monitor_pid !== undefined && (
    !Number.isSafeInteger(value.owner_monitor_pid) || value.owner_monitor_pid <= 0
    || value.owner_monitor_pid === value.pid
  )) throw readinessError("owner monitor PID must identify a separate process");
  if (
    typeof value.runtime_fingerprint !== "string" ||
    !/^[a-zA-Z0-9._-]{6,128}$/.test(value.runtime_fingerprint)
  ) {
    throw readinessError("runtime fingerprint is missing or malformed");
  }

  let parsedUrl;
  try {
    parsedUrl = new URL(value.url);
  } catch {
    throw readinessError("URL is malformed");
  }
  if (
    parsedUrl.protocol !== "http:" ||
    parsedUrl.hostname !== "127.0.0.1" ||
    !parsedUrl.port ||
    parsedUrl.pathname !== "/" ||
    parsedUrl.username ||
    parsedUrl.password ||
    parsedUrl.search ||
    parsedUrl.hash
  ) {
    throw readinessError("URL must be an unadorned IPv4 loopback origin");
  }
  const port = Number(parsedUrl.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw readinessError("URL port is invalid");
  }

  return Object.freeze({
    protocol: 1,
    url: parsedUrl.origin,
    pid: value.pid,
    runtime_fingerprint: value.runtime_fingerprint,
    ...(value.owner_monitor_pid === undefined ? {} : {owner_monitor_pid: value.owner_monitor_pid}),
  });
}

module.exports = {MAX_READINESS_BYTES, parseReadinessLine};
