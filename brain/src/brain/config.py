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
    )
