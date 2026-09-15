from dataclasses import dataclass
from typing import Dict


@dataclass
class MarketState:
    """
    Unified representation of the global financial market state.

    This structure is designed to become the input representation
    for the future financial neural architecture.
    """

    # Market dynamics
    price_trend: float
    momentum: float
    volatility: float
    liquidity: float
    volume: float

    # Market structure
    breadth: float
    positioning: float
    sentiment: float

    # Macro environment
    interest_rates: float
    inflation: float
    growth: float
    monetary_policy: float

    # Currency and credit conditions
    usd_strength: float
    credit_conditions: float

    # Cross-asset relationships
    cross_asset_strength: Dict[str, float]

    # Current market regime
    regime: str

    # Model uncertainty
    uncertainty: float

    def to_vector(self) -> list[float]:
        """
        Convert the market state into a numerical vector.

        This vector will later become one of the core inputs
        to the financial neural network.
        """

        vector = [
            self.price_trend,
            self.momentum,
            self.volatility,
            self.liquidity,
            self.volume,
            self.breadth,
            self.positioning,
            self.sentiment,
            self.interest_rates,
            self.inflation,
            self.growth,
            self.monetary_policy,
            self.usd_strength,
            self.credit_conditions,
            self.uncertainty,
        ]

        vector.extend(self.cross_asset_strength.values())

        return vector
