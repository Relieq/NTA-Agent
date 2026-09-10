"""NTA-Agent — autonomous agent for Ninety Thousand Acres.

Layered architecture (see docs/ROADMAP.md):
  io/         hybrid I/O: ADB+vision adapter (this phase) and API adapter (later)
  state/      normalized GameState shared by every layer
  execution/  deterministic "hands": rule engine + predictors
  brain/      LLM "brain": sparse high-level strategy decisions
"""

__version__ = "0.0.1"
