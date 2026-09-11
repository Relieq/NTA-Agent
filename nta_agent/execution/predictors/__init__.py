"""Predictors: turn GameState into decision inputs (economy now; battle later)."""

from nta_agent.execution.predictors.economy import EconomyPredictor, ResourceForecast

__all__ = ["EconomyPredictor", "ResourceForecast"]
