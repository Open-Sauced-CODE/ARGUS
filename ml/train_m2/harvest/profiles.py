"""The two sampling profiles of the harvest contract, as data.

Contract (CONTRACT_HARVEST.md):
  sample 0 (both profiles): temperature 0.0, seed 0, top_p not sent (null in the file)
  profile A, samples 1-7  : temperature 0.7, seed = sample_idx, top_p not sent
  profile B, samples 1-7  : temperature 1.0, top_p 0.95, seed = 1000 + sample_idx
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

SCHEMA_VERSION = "m2.harvest.v1"
GENERATORS = ("zeroshot", "sft", "rft", "rft_v2")
PROFILES = ("A", "B")
N_SAMPLES = 8


@dataclass(frozen=True)
class SampleParams:
    """Decoding parameters for one generation."""

    temperature: float
    top_p: Optional[float]
    seed: int


def sample_params(profile: str, sample_idx: int, temperature_override: Optional[float] = None) -> SampleParams:
    """Return the exact decoding parameters for (profile, sample_idx).

    temperature_override replaces the temperature of samples 1-7 only. It exists for local experiments
    (for example the T=1.2 and T=1.4 checks in the pilot); output made with it must never go into the
    contract folders.
    """
    if profile not in PROFILES:
        raise ValueError("profile must be one of %s, got %r" % (PROFILES, profile))
    if not isinstance(sample_idx, int) or isinstance(sample_idx, bool) or not 0 <= sample_idx < N_SAMPLES:
        raise ValueError("sample_idx must be an integer from 0 to %d, got %r" % (N_SAMPLES - 1, sample_idx))
    if sample_idx == 0:
        return SampleParams(0.0, None, 0)
    if profile == "A":
        temperature, top_p, seed = 0.7, None, sample_idx
    else:
        temperature, top_p, seed = 1.0, 0.95, 1000 + sample_idx
    if temperature_override is not None:
        temperature = float(temperature_override)
    return SampleParams(temperature, top_p, seed)
