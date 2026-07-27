"""Environment-driven configuration. Every tunable lives here, nowhere else."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    home: Path
    ollama_url: str
    model: str
    max_turns: int
    debounce_s: float
    poll_interval_s: float
    port: int
    parallel: int
    autorun: bool
    llm_timeout_s: float
    think_final: bool  # thinking mode on the conclude turn
    usb_watch: bool = True  # auto-scan for plugged-in client sticks (ADR-0012)
    usb_sources: tuple[str, ...] = ()  # extra outbox paths beyond mount globs
    full_ctx_chars: int = 300_000  # budget for full-context injection
    num_ctx: int = 32_768  # ollama context window; full-context mode needs headroom
    # graph organizer, the embedding pair-model (ADR-0016)
    organize: bool = True
    embed_model: str = "qwen3-embedding:8b"
    embed_timeout_s: float = 30.0
    org_sim_threshold: float = 0.72
    org_max_edges_per_chunk: int = 3
    org_max_edges: int = 300
    # ethernet link watcher (cable twin of usb auto-scan); off until iface+user set
    eth_iface: str = ""
    eth_user: str = ""
    eth_remote_dir: str = "~/bundles"
    eth_collect_cmd: str = ""  # optional remote command run before each pull

    @property
    def inbox(self) -> Path:
        return self.home / "inbox"

    @property
    def staging(self) -> Path:
        return self.inbox / ".staging"

    @property
    def rejected(self) -> Path:
        return self.inbox / "rejected"

    @property
    def runs(self) -> Path:
        return self.home / "runs"

    def ensure_dirs(self) -> None:
        for p in (self.inbox, self.staging, self.rejected, self.runs):
            p.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    env = os.environ
    return Config(
        home=Path(env.get("BRAIN_HOME", "~/brain")).expanduser(),
        ollama_url=env.get("OLLAMA_URL", "http://127.0.0.1:11434"),
        model=env.get("BRAIN_MODEL", "qwen3.5:122b"),
        max_turns=int(env.get("BRAIN_MAX_TURNS", "5")),
        debounce_s=float(env.get("BRAIN_DEBOUNCE_S", "10")),
        poll_interval_s=float(env.get("BRAIN_POLL_S", "2")),
        port=int(env.get("BRAIN_PORT", "8000")),
        parallel=int(env.get("OLLAMA_NUM_PARALLEL", "1")),
        autorun=env.get("BRAIN_AUTORUN", "1") not in ("0", "false", "no"),
        llm_timeout_s=float(env.get("BRAIN_LLM_TIMEOUT_S", "120")),
        think_final=env.get("BRAIN_THINK_FINAL", "0") in ("1", "true", "yes"),
        usb_watch=env.get("BRAIN_USB_WATCH", "1") not in ("0", "false", "no"),
        usb_sources=tuple(p for p in env.get("BRAIN_USB_SOURCES", "").split(":") if p),
        full_ctx_chars=int(env.get("BRAIN_FULL_CTX_CHARS", "300000")),
        num_ctx=int(env.get("BRAIN_NUM_CTX", "32768")),
        organize=env.get("BRAIN_ORGANIZE", "1") not in ("0", "false", "no"),
        embed_model=env.get("BRAIN_EMBED_MODEL", "qwen3-embedding:8b"),
        embed_timeout_s=float(env.get("BRAIN_EMBED_TIMEOUT_S", "30")),
        org_sim_threshold=float(env.get("BRAIN_ORG_SIM_THRESHOLD", "0.72")),
        org_max_edges_per_chunk=int(env.get("BRAIN_ORG_MAX_EDGES_PER_CHUNK", "3")),
        org_max_edges=int(env.get("BRAIN_ORG_MAX_EDGES", "300")),
        eth_iface=env.get("BRAIN_ETH_IFACE", ""),
        eth_user=env.get("BRAIN_ETH_USER", ""),
        eth_remote_dir=env.get("BRAIN_ETH_REMOTE_DIR", "~/bundles"),
        eth_collect_cmd=env.get("BRAIN_ETH_COLLECT_CMD", ""),
    )
