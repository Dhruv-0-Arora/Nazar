"""Ethernet link watcher: session state machine + neighbor parsing."""

from dataclasses import replace

from brain.api.server import create_app
from brain.ingest.ethernet import EthernetWatcher, parse_neighbors
from conftest import FakeLLM

NEIGH_OUTPUT = """\
fe80::408:4412:3a20:c606 lladdr 38:7c:76:04:4b:52 REACHABLE
fe80::dead:beef:0:1 lladdr aa:bb:cc:dd:ee:ff STALE
fe80::bad0:0:0:1 lladdr 11:22:33:44:55:66 FAILED
2001:db8::1 lladdr 11:22:33:44:55:66 REACHABLE
"""


def test_parse_neighbors_filters_dead_and_non_linklocal():
    peers = parse_neighbors(NEIGH_OUTPUT)
    assert peers == ["fe80::408:4412:3a20:c606", "fe80::dead:beef:0:1"]


class Harness:
    def __init__(self, cfg, registry):
        self.carrier = False
        self.pulls: list[str] = []
        self.pull_ok = True
        self.clock = 0.0
        self.watcher = EthernetWatcher(
            cfg,
            registry,
            carrier_fn=lambda iface: self.carrier,
            discover_fn=lambda iface: ["fe80::peer"],
            pull_fn=lambda cfg_, peer: (self.pulls.append(peer), self.pull_ok)[1],
            now_fn=lambda: self.clock,
        )

    def tick(self, dt=11.0):
        self.clock += dt
        self.watcher.tick()


def make_harness(cfg):
    eth_cfg = replace(cfg, eth_iface="eth0", eth_user="demo")
    app = create_app(eth_cfg, llm=FakeLLM([]))
    return Harness(eth_cfg, app.state.registry), app.state.registry


def test_pulls_once_per_cable_session(cfg):
    h, _ = make_harness(cfg)
    h.tick()
    assert h.pulls == []  # cable down: nothing

    h.carrier = True
    h.tick()
    assert h.pulls == ["fe80::peer"]  # link-up: pull
    h.tick()
    h.tick()
    assert h.pulls == ["fe80::peer"]  # session done: no re-pull while connected

    h.carrier = False
    h.tick()
    h.carrier = True
    h.tick()
    assert h.pulls == ["fe80::peer", "fe80::peer"]  # replug: new session pulls again


def test_failed_pull_retries_with_backoff(cfg):
    h, _ = make_harness(cfg)
    h.pull_ok = False
    h.carrier = True
    h.tick()
    assert len(h.pulls) == 1
    h.tick(dt=1.0)  # inside the retry interval: no attempt
    assert len(h.pulls) == 1
    h.tick(dt=11.0)
    assert len(h.pulls) == 2  # retried after the interval


def test_demo_reset_rearms_the_session(cfg):
    h, registry = make_harness(cfg)
    h.carrier = True
    h.tick()
    assert len(h.pulls) == 1
    registry.reset()  # demo reset bumps the epoch
    h.tick()
    assert len(h.pulls) == 2  # same cable session, but reset re-armed it
