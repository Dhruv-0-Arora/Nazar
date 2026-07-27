"""Evidence-layer graph construction (SPEC section 6.3).

Input is the chunk store, never raw bundles. Nodes record their birth chunks
at extraction time; chunk.mentions gets the reverse link the same instant
(ADR-0004). Deterministic: structural tier + regex extraction + cross-ref.
"""

import re

from ..ingest.bundle import Manifest
from ..ingest.chunker import Chunk
from .model import evidence_node_id
from .store import GraphStore

IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
HOSTPORT_RE = re.compile(r"\b([a-z0-9][a-z0-9.-]*[a-z0-9]):(\d{2,5})\b")
ENV_VAR_RE = re.compile(r"^([A-Z][A-Z0-9_]{2,})=(.*)$", re.MULTILINE)
HOSTNAME_RE = re.compile(r"\b([a-z0-9-]+(?:\.[a-z0-9-]+)+)\b")
ERROR_RE = re.compile(
    r"\b(ECONNREFUSED|ECONNRESET|ETIMEDOUT|EADDRINUSE|ENOTFOUND|EHOSTUNREACH"
    r"|Connection refused|timed? ?out|HTTP 5\d\d|502 Bad Gateway|OOMKilled)\b",
    re.IGNORECASE,
)
TICKET_RE = re.compile(r"\b(?:#|ticket-|TICKET-)(\d{3,6})\b")
INET_RE = re.compile(r"^\s+inet (\d{1,3}(?:\.\d{1,3}){3})/", re.MULTILINE)
SS_PROC_RE = re.compile(r'users:\(\("([^"]+)"')

# hostname-looking tokens that are actually filenames or noise
_FILE_EXT_NOISE = {
    "log", "env", "md", "txt", "json", "js", "py", "sh", "conf", "service", "yaml", "yml",
    "socket", "target", "timer", "pid", "lock", "gz", "html", "css",
    "pem", "crt", "key", "cert", "pub",
}
_HOST_NOISE = {"e.g", "i.e", "vs", "etc"}

# source files under problem/ or docs/: dotted tokens are method calls
# (json.stringify, this.connections.push), not hostnames - skip host
# extraction there or minified JS floods the graph with junk host nodes
_CODE_EXTS = {"js", "mjs", "cjs", "ts", "tsx", "jsx", "map", "html", "css", "py"}


def _is_code_file(file_path: str) -> bool:
    return file_path.rsplit(".", 1)[-1].lower() in _CODE_EXTS


def build_graph(chunks: list[Chunk], manifests: list[Manifest], store: GraphStore) -> None:
    machines = {m.machine_id: m for m in manifests}

    # -- structural tier ------------------------------------------------
    for m in manifests:
        store.get_or_create("machine", m.machine_id, label=f"machine {m.hostname}")
        for svc in m.services:
            node = store.get_or_create("service", svc, machine_id=m.machine_id, label=f"service {svc} on {m.machine_id}")
            store.add_edge(node.id, evidence_node_id("machine", m.machine_id), "located_on")

    files_seen: set[str] = set()
    for chunk in chunks:
        fid = evidence_node_id("file", chunk.file_path, machine_id=chunk.machine_id)
        if fid not in files_seen:
            files_seen.add(fid)
            store.get_or_create("file", chunk.file_path, machine_id=chunk.machine_id, label=chunk.file_path)
            store.add_edge(fid, evidence_node_id("machine", chunk.machine_id), "located_on")
            svc = _owning_service(chunk.file_path)
            if svc and svc in machines.get(chunk.machine_id, Manifest("", "", "", "", "")).services:
                store.add_edge(
                    evidence_node_id("service", svc, machine_id=chunk.machine_id), fid, "has_config",
                    attrs={"src_chunk": chunk.id},
                )

    # -- machine address book (for the cross-ref pass) ------------------
    machine_ips: dict[str, str] = {}  # ip -> machine_id
    for chunk in chunks:
        if chunk.file_path == "network.txt" and "ip addr" in chunk.text.splitlines()[0]:
            for ip in INET_RE.findall(chunk.text):
                if not ip.startswith("127."):
                    machine_ips[ip] = chunk.machine_id
    machine_hostnames = {m.hostname: m.machine_id for m in manifests} | {m.machine_id: m.machine_id for m in manifests}

    # -- extracted tier -------------------------------------------------
    for chunk in chunks:
        fid = evidence_node_id("file", chunk.file_path, machine_id=chunk.machine_id)
        # machine-wide captures are the machine node's evidence; without this,
        # talks_to fallback edges to machine nodes have no renderable endpoint
        if chunk.file_path in ("system.txt", "network.txt"):
            store.add_evidence(evidence_node_id("machine", chunk.machine_id), chunk.id)
        # a service's own files (status, journal, config) are its evidence
        svc = _owning_service(chunk.file_path)
        if svc and svc in machines.get(chunk.machine_id, Manifest("", "", "", "", "")).services:
            sid = evidence_node_id("service", svc, machine_id=chunk.machine_id)
            store.add_evidence(sid, chunk.id)
            if sid not in chunk.mentions:
                chunk.mentions.append(sid)
        for type_, value in _extract_entities(chunk.text, with_hostnames=not _is_code_file(chunk.file_path)):
            node = store.get_or_create(type_, value)
            store.add_evidence(node.id, chunk.id)
            if node.id not in chunk.mentions:
                chunk.mentions.append(node.id)
            store.add_edge(fid, node.id, "mentions")
        # every chunk is evidence for its own file node too
        store.add_evidence(fid, chunk.id)

    # -- listens_on from ss sections ------------------------------------
    listeners: dict[tuple[str, str], str] = {}  # (machine_id, port) -> service node id
    for chunk in chunks:
        if chunk.file_path != "network.txt" or "ss " not in chunk.text.splitlines()[0]:
            continue
        for line in chunk.text.splitlines()[1:]:
            toks = line.split()
            if not toks or toks[0].upper() != "LISTEN" or len(toks) < 4:
                continue
            port = toks[3].rsplit(":", 1)[-1]  # local address column, e.g. 0.0.0.0:3001
            if not port.isdigit():
                continue
            proc_match = SS_PROC_RE.search(line)
            proc = (proc_match.group(1) if proc_match else "").lower()
            svc = _match_service(proc, machines.get(chunk.machine_id))
            if svc:
                svc_id = evidence_node_id("service", svc, machine_id=chunk.machine_id)
                port_node = store.get_or_create("port", port)
                store.add_evidence(port_node.id, chunk.id)
                store.add_edge(svc_id, port_node.id, "listens_on")
                listeners[(chunk.machine_id, port)] = svc_id

    # -- cross-reference pass: the money edge ---------------------------
    for chunk in chunks:
        svc = _owning_service(chunk.file_path)
        if not svc or "/config/" not in chunk.file_path:
            continue
        src_id = evidence_node_id("service", svc, machine_id=chunk.machine_id)
        if src_id not in store.nodes:
            continue
        for host, port in _config_targets(chunk.text):
            target_machine = _resolve(host, chunk.machine_id, machine_ips, machine_hostnames)
            if target_machine:
                dst = listeners.get((target_machine, port or "")) or evidence_node_id("machine", target_machine)
                store.add_edge(src_id, dst, "talks_to", attrs={"src_chunk": chunk.id})
            else:
                host_node = store.get_or_create("host", host)
                store.add_evidence(host_node.id, chunk.id)
                store.add_edge(src_id, host_node.id, "talks_to", attrs={"dangling": True, "src_chunk": chunk.id})


def _owning_service(file_path: str) -> str | None:
    parts = file_path.split("/")
    if len(parts) >= 2 and parts[0] == "services":
        return parts[1]
    return None


def _match_service(proc: str, manifest: Manifest | None) -> str | None:
    if not manifest:
        return None
    for svc in manifest.services:
        if proc and (svc in proc or proc in svc):
            return svc
    # node processes: match by convention when only one service exists
    if proc in ("node", "nodejs") and len(manifest.services) == 1:
        return manifest.services[0]
    return None


def _extract_entities(text: str, with_hostnames: bool = True):
    seen = set()
    for ip in IP_RE.findall(text):
        if _valid_ip(ip) and ("ip", ip) not in seen:
            seen.add(("ip", ip))
    for var, _val in ENV_VAR_RE.findall(text):
        if ("env_var", var) not in seen:
            seen.add(("env_var", var))
    if with_hostnames:
        for host in HOSTNAME_RE.findall(text.lower()):
            if _valid_hostname(host) and ("host", host) not in seen:
                seen.add(("host", host))
    for err in ERROR_RE.findall(text):
        key = ("error", err.upper().replace(" ", "_"))
        if key not in seen:
            seen.add(key)
    for ticket in TICKET_RE.findall(text):
        if ("ticket", ticket) not in seen:
            seen.add(("ticket", ticket))
    for _host, port in HOSTPORT_RE.findall(text.lower()):
        if ("port", port) not in seen and 1 <= int(port) <= 65535:
            seen.add(("port", port))
    return sorted(seen)


def _config_targets(text: str) -> list[tuple[str, str | None]]:
    """(host, port) pairs a config points at: env values and host:port tokens."""
    targets: list[tuple[str, str | None]] = []
    env = dict(ENV_VAR_RE.findall(text))
    for key, val in env.items():
        val = val.strip().strip('"').strip("'")
        m = re.match(r"^(?:https?://)?([a-z0-9.-]+?)(?::(\d{2,5}))?(?:/.*)?$", val.lower())
        if m and ("HOST" in key or "URL" in key or "ADDR" in key or "ENDPOINT" in key):
            host, port = m.group(1), m.group(2)
            if _valid_hostname(host) or _valid_ip(host) or host == "localhost":
                port = port or env.get(key.replace("HOST", "PORT"), None)
                targets.append((host, port))
    return targets


def _resolve(host: str, own_machine: str, machine_ips: dict[str, str], machine_hostnames: dict[str, str]) -> str | None:
    if host in ("localhost", "127.0.0.1", "0.0.0.0"):
        return own_machine
    if host in machine_ips:
        return machine_ips[host]
    if host in machine_hostnames:
        return machine_hostnames[host]
    return None


def _valid_ip(ip: str) -> bool:
    return all(0 <= int(p) <= 255 for p in ip.split("."))


def _valid_hostname(host: str) -> bool:
    if _valid_ip(host) if IP_RE.fullmatch(host) else False:
        return False
    last = host.rsplit(".", 1)[-1]
    if last in _FILE_EXT_NOISE or host in _HOST_NOISE:
        return False
    if any(part == "" for part in host.split(".")):
        return False
    return "." in host and not host.replace(".", "").isdigit()
