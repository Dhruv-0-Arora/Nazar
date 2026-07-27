"""Ethernet link watcher: the cable twin of the USB auto-scan.

Plug the demo server in via direct ethernet and the Brain notices the carrier
coming up, discovers the peer's IPv6 link-local address (no DHCP, no DNS - see
AIRGAP-SSH.md), optionally runs a collect command on the peer over SSH, and
pulls the newest bundle into the inbox. From there the inbox watcher's normal
debounce + autorun takes over, so connecting the cable IS starting the run.

Enabled only when BRAIN_ETH_IFACE and BRAIN_ETH_USER are set; SSH must be
key-authenticated (BatchMode) exactly as `brain pull` requires.
"""

import asyncio
import re
import subprocess
import time
import traceback
from pathlib import Path
from typing import Callable

from ..config import Config

FE80_RE = re.compile(r"\b(fe80::[0-9a-f:]+)\b", re.IGNORECASE)
RETRY_INTERVAL_S = 10.0


def carrier_up(iface: str) -> bool:
    try:
        return Path(f"/sys/class/net/{iface}/carrier").read_text().strip() == "1"
    except OSError:
        return False


def parse_neighbors(neigh_output: str) -> list[str]:
    """fe80 peers from `ip -6 neigh show dev <iface>`, dead entries excluded."""
    peers = []
    for line in neigh_output.splitlines():
        if "FAILED" in line or "INCOMPLETE" in line:
            continue
        m = FE80_RE.search(line)
        if m and m.group(1) not in peers:
            peers.append(m.group(1))
    return peers


def discover_peers(iface: str) -> list[str]:
    """All-nodes multicast ping to populate the neighbor table, then read it."""
    subprocess.run(
        ["ping6", "-c", "2", "-W", "1", "-I", iface, f"ff02::1%{iface}"],
        capture_output=True,
        timeout=10,
        check=False,
    )
    out = subprocess.run(["ip", "-6", "neigh", "show", "dev", iface], capture_output=True, text=True, timeout=10, check=False)
    return parse_neighbors(out.stdout)


def collect_and_pull(cfg: Config, peer: str) -> bool:
    """Optionally run the remote collect command, then pull the newest bundle.
    ssh takes the bare scoped literal; scp needs it bracketed."""
    from ..cli import _pull  # deferred: cli imports config, avoid import cycles at module load

    ssh_host = f"{cfg.eth_user}@{peer}%{cfg.eth_iface}"
    scp_host = f"{cfg.eth_user}@[{peer}%{cfg.eth_iface}]"
    if cfg.eth_collect_cmd:
        proc = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", ssh_host, cfg.eth_collect_cmd],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode != 0:
            print(f"[ethernet] collect on {peer} failed: {proc.stderr.strip()[:200]}")
            return False
    return _pull(cfg, ssh_host, cfg.eth_remote_dir, scp_host=scp_host) == 0


class EthernetWatcher:
    """One tick per poll; injectable probes keep it unit-testable."""

    def __init__(
        self,
        cfg: Config,
        registry,
        *,
        carrier_fn: Callable[[str], bool] = carrier_up,
        discover_fn: Callable[[str], list[str]] = discover_peers,
        pull_fn: Callable[[Config, str], bool] = collect_and_pull,
        now_fn: Callable[[], float] = time.monotonic,
    ):
        self.cfg = cfg
        self.registry = registry
        self._carrier = carrier_fn
        self._discover = discover_fn
        self._pull = pull_fn
        self._now = now_fn
        self._was_up = False
        self._session_done = False
        self._last_attempt = 0.0
        self._epoch = registry.epoch

    def tick(self) -> None:
        # a demo reset re-arms the watcher: the still-connected peer re-pulls
        if self.registry.epoch != self._epoch:
            self._epoch = self.registry.epoch
            self._session_done = False

        up = self._carrier(self.cfg.eth_iface)
        if up and not self._was_up:
            self._session_done = False  # fresh cable session
        self._was_up = up
        if not up or self._session_done:
            return
        if self._now() - self._last_attempt < RETRY_INTERVAL_S:
            return
        self._last_attempt = self._now()

        for peer in self._discover(self.cfg.eth_iface):
            if self._pull(self.cfg, peer):
                print(f"[ethernet] pulled from {peer}; inbox watcher takes it from here")
                self._session_done = True
                return


async def ethernet_loop(cfg: Config, registry) -> None:
    if not cfg.eth_iface or not cfg.eth_user:
        return
    watcher = EthernetWatcher(cfg, registry)
    interval = max(cfg.poll_interval_s, 3.0)
    while True:
        try:
            await asyncio.to_thread(watcher.tick)
        except Exception:  # noqa: BLE001 - the watcher must survive anything
            traceback.print_exc()
        await asyncio.sleep(interval)
