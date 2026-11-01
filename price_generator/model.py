"""Synthetic OHLCV price paths with conditional noisy volume.

The built-in profiles are illustrative starting values, not calibrated market
forecasts. Pass locally calibrated profiles for development style imitation.
The engine has no date, session, or market-calendar concept.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import random
from typing import Mapping


class AssetClass(str, Enum):
    STOCKS = "stocks"
    SPOT_CRYPTO = "spot_crypto"


class SimulationModel(str, Enum):
    REGIME_SWITCHING = "regime_switching"
    MEAN_REVERTING = "mean_reverting"
    JUMP_DIFFUSION = "jump_diffusion"


SIMULATION_MODEL_LABELS: Mapping[SimulationModel, str] = {
    SimulationModel.REGIME_SWITCHING: "Regime switching",
    SimulationModel.MEAN_REVERTING: "Mean reverting",
    SimulationModel.JUMP_DIFFUSION: "Jump diffusion",
}

SIMULATION_MODEL_DESCRIPTIONS: Mapping[SimulationModel, str] = {
    SimulationModel.REGIME_SWITCHING: "Moves through upward, sideways, and downward phases.",
    SimulationModel.MEAN_REVERTING: "Wanders around its generated baseline and tends to return toward it.",
    SimulationModel.JUMP_DIFFUSION: "Uses a noisy path with occasional sudden price jumps.",
}


BAR_INTERVAL_SECONDS: Mapping[str, int] = {
    "1m": 60,
    "2m": 120,
    "5m": 300,
    "15m": 900,
    "1h": 3_600,
    "2h": 7_200,
    "3h": 10_800,
    "4h": 14_400,
}


@dataclass(frozen=True)
class Regime:
    """Parameters for one state in the simulated market process.

    ``drift_per_hour`` is the expected simple-price return per simulated hour;
    the log-price process applies it as geometric Brownian drift
    (``drift - volatility² / 2``). ``volatility_per_sqrt_hour`` is log-return
    volatility per square-root hour. Regime duration is exponential and
    measured in simulated hours.
    """

    name: str
    drift_per_hour: float
    volatility_per_sqrt_hour: float
    volume_activity: float
    mean_duration_hours: float
    next_regimes: Mapping[str, float]


@dataclass(frozen=True)
class RegimeSwitchingProfile:
    """Developer-tunable asset-class parameters for a synthetic scenario."""

    asset_class: AssetClass
    starting_price: float
    mean_volume_per_hour: float
    volume_noise_sigma: float
    return_volume_sensitivity: float
    regimes: Mapping[str, Regime]
    initial_regime_weights: Mapping[str, float]

    @property
    def volume_unit(self) -> str:
        if AssetClass(self.asset_class) is AssetClass.STOCKS:
            return "shares"
        return "base-asset units"

    @property
    def price_unit(self) -> str:
        if AssetClass(self.asset_class) is AssetClass.STOCKS:
            return "synthetic price per share"
        return "synthetic quote units per base asset"


@dataclass(frozen=True)
class OHLCVBar:
    """A forming or completed bar, timestamped by elapsed simulated time."""

    open: float
    high: float
    low: float
    close: float
    volume: float
    interval_seconds: int
    start_simulated_seconds: float
    elapsed_simulated_seconds: float
    simulation_model: str
    regimes: tuple[str, ...]
    price_unit: str
    volume_unit: str
    is_synthetic: bool
    is_closed: bool


@dataclass(frozen=True)
class AdvanceResult:
    """Bars completed during an advance and the latest forming bar."""

    completed_bars: tuple[OHLCVBar, ...]
    forming_bar: OHLCVBar
    current_regime: str
    simulated_seconds: float


def default_profile(asset_class: AssetClass | str) -> RegimeSwitchingProfile:
    """Return an illustrative default profile for the requested asset class.

    These broad defaults make the engine runnable before local OHLCV samples
    are available. Tune them from development samples before treating the
    generated distribution as representative of a particular market.
    """

    asset = AssetClass(asset_class)
    if asset is AssetClass.STOCKS:
        starting_price = 100.0
        mean_volume_per_hour = 25_000.0
        volatility_per_24_simulated_hours = 0.01
        drift_per_24_simulated_hours = 0.0004
        dwell_hours = {"upward": 24.0, "sideways": 36.0, "downward": 18.0}
        activity = {"upward": 0.95, "sideways": 0.8, "downward": 1.2}
        vol_scale = {"upward": 1.0, "sideways": 0.8, "downward": 1.25}
    else:
        starting_price = 1_000.0
        mean_volume_per_hour = 10.0
        volatility_per_24_simulated_hours = 0.05
        drift_per_24_simulated_hours = 0.0012
        dwell_hours = {"upward": 18.0, "sideways": 24.0, "downward": 12.0}
        activity = {"upward": 1.0, "sideways": 0.75, "downward": 1.3}
        vol_scale = {"upward": 1.0, "sideways": 0.8, "downward": 1.3}

    # Transition weights describe relative likelihoods; they are normalized
    # when a transition occurs. A transition is sampled by simulated time,
    # independently of the selected bar interval.
    transition_weights = {
        "upward": {"sideways": 0.8, "downward": 0.2},
        "sideways": {"upward": 0.5, "downward": 0.5},
        "downward": {"sideways": 0.8, "upward": 0.2},
    }
    regimes = {
        "upward": Regime(
            name="upward",
            drift_per_hour=drift_per_24_simulated_hours / 24.0,
            volatility_per_sqrt_hour=(volatility_per_24_simulated_hours / math.sqrt(24.0))
            * vol_scale["upward"],
            volume_activity=activity["upward"],
            mean_duration_hours=dwell_hours["upward"],
            next_regimes=transition_weights["upward"],
        ),
        "sideways": Regime(
            name="sideways",
            drift_per_hour=0.0,
            volatility_per_sqrt_hour=(volatility_per_24_simulated_hours / math.sqrt(24.0))
            * vol_scale["sideways"],
            volume_activity=activity["sideways"],
            mean_duration_hours=dwell_hours["sideways"],
            next_regimes=transition_weights["sideways"],
        ),
        "downward": Regime(
            name="downward",
            drift_per_hour=-drift_per_24_simulated_hours / 24.0,
            volatility_per_sqrt_hour=(volatility_per_24_simulated_hours / math.sqrt(24.0))
            * vol_scale["downward"],
            volume_activity=activity["downward"],
            mean_duration_hours=dwell_hours["downward"],
            next_regimes=transition_weights["downward"],
        ),
    }
    return RegimeSwitchingProfile(
        asset_class=asset,
        starting_price=starting_price,
        mean_volume_per_hour=mean_volume_per_hour,
        volume_noise_sigma=0.55,
        return_volume_sensitivity=0.65,
        regimes=regimes,
        initial_regime_weights={"upward": 0.2, "sideways": 0.6, "downward": 0.2},
    )


class RegimeSwitchingSimulator:
    """Advance one open-ended synthetic OHLCV stream.

    ``advance_wall_time`` converts elapsed wall-clock seconds into simulated
    time so a full selected bar takes ``wall_seconds_per_bar`` seconds. It
    returns every bar closed during the call plus the current forming bar.
    Omitting ``seed`` gives a fresh stochastic run; passing one is intended for
    repeatable developer debugging.
    """

    _EPSILON = 1e-9

    def __init__(
        self,
        asset_class: AssetClass | str,
        bar_interval: str,
        *,
        wall_seconds_per_bar: float = 3.0,
        max_internal_step_seconds: float = 5.0,
        seed: int | None = None,
        profile: RegimeSwitchingProfile | None = None,
        simulation_model: SimulationModel | str = SimulationModel.REGIME_SWITCHING,
    ) -> None:
        try:
            self.asset_class = AssetClass(asset_class)
        except ValueError as exc:
            raise ValueError(f"Unsupported asset class: {asset_class!r}") from exc
        try:
            self.interval_seconds = BAR_INTERVAL_SECONDS[bar_interval]
        except KeyError as exc:
            choices = ", ".join(BAR_INTERVAL_SECONDS)
            raise ValueError(f"Unsupported bar interval {bar_interval!r}; choose {choices}") from exc
        try:
            self.simulation_model = SimulationModel(simulation_model)
        except ValueError as exc:
            choices = ", ".join(model.value for model in SimulationModel)
            raise ValueError(f"Unsupported simulation model {simulation_model!r}; choose {choices}") from exc

        self.wall_seconds_per_bar = self._positive_finite(
            "wall_seconds_per_bar", wall_seconds_per_bar
        )
        self.max_internal_step_seconds = self._positive_finite(
            "max_internal_step_seconds", max_internal_step_seconds
        )
        self.profile = profile or default_profile(self.asset_class)
        if AssetClass(self.profile.asset_class) is not self.asset_class:
            raise ValueError("Profile asset_class must match the simulator asset_class")
        self._validate_profile(self.profile)

        self._rng = random.Random(seed)
        if self.simulation_model is SimulationModel.REGIME_SWITCHING:
            self._regime_name = self._weighted_choice(self.profile.initial_regime_weights)
            self._regime_time_remaining = self._sample_regime_duration()
            initial_bar_regimes = [self._regime_name]
        else:
            self._regime_name = self.simulation_model.value
            self._regime_time_remaining = math.inf
            initial_bar_regimes = []
        self._simulated_seconds = 0.0
        self._log_price = math.log(self.profile.starting_price)
        self._bar_elapsed_seconds = 0.0
        self._bar_start_seconds = 0.0
        self._bar_open = self.profile.starting_price
        self._bar_high = self.profile.starting_price
        self._bar_low = self.profile.starting_price
        self._bar_close = self.profile.starting_price
        self._bar_volume = 0.0
        self._bar_regimes = initial_bar_regimes

    @property
    def current_regime(self) -> str:
        return self._regime_name

    @property
    def simulated_seconds(self) -> float:
        return self._simulated_seconds

    @property
    def current_bar(self) -> OHLCVBar:
        return self._snapshot(is_closed=False)

    def advance_wall_time(self, elapsed_wall_seconds: float) -> AdvanceResult:
        """Advance the stream and return closed bars plus the live bar state."""

        elapsed = float(elapsed_wall_seconds)
        if not math.isfinite(elapsed) or elapsed < 0.0:
            raise ValueError("elapsed_wall_seconds must be finite and non-negative")
        remaining = elapsed * self.interval_seconds / self.wall_seconds_per_bar
        completed: list[OHLCVBar] = []

        while remaining > self._EPSILON:
            if self._regime_time_remaining <= self._EPSILON:
                self._transition_regime()

            until_bar_close = self.interval_seconds - self._bar_elapsed_seconds
            step = min(
                remaining,
                self.max_internal_step_seconds,
                until_bar_close,
                self._regime_time_remaining,
            )
            if step <= self._EPSILON:
                # Boundary rounding can leave a tiny remainder. Snap to the
                # corresponding boundary so the loop always makes progress.
                if until_bar_close <= self._EPSILON:
                    completed.append(self._finish_bar())
                    continue
                if self._regime_time_remaining <= self._EPSILON:
                    self._transition_regime()
                    continue
                break

            regime_changed_at_boundary = False
            self._simulate_step(step)
            remaining = max(0.0, remaining - step)
            self._simulated_seconds += step
            self._bar_elapsed_seconds += step
            self._regime_time_remaining = max(0.0, self._regime_time_remaining - step)

            bar_closed = self._bar_elapsed_seconds >= self.interval_seconds - self._EPSILON
            regime_changed = self._regime_time_remaining <= self._EPSILON

            # Close the old bar before applying a regime transition at the
            # same simulated instant. The new regime starts in the next bar.
            if bar_closed:
                completed.append(self._finish_bar())
            if regime_changed:
                self._transition_regime()
                regime_changed_at_boundary = True
            if regime_changed_at_boundary and bar_closed:
                self._bar_regimes = [self._regime_name]

        return AdvanceResult(
            completed_bars=tuple(completed),
            forming_bar=self._snapshot(is_closed=False),
            current_regime=self._regime_name,
            simulated_seconds=self._simulated_seconds,
        )

    def _simulate_step(self, simulated_seconds: float) -> None:
        dt_hours = simulated_seconds / 3_600.0
        regime = self._calibration_regime()
        sigma = regime.volatility_per_sqrt_hour
        diffusion_scale = sigma * math.sqrt(dt_hours)
        activity = regime.volume_activity

        if self.simulation_model is SimulationModel.REGIME_SWITCHING:
            regime = self.profile.regimes[self._regime_name]
            sigma = regime.volatility_per_sqrt_hour
            diffusion_scale = sigma * math.sqrt(dt_hours)
            activity = regime.volume_activity
            log_return = (
                (regime.drift_per_hour - 0.5 * sigma * sigma) * dt_hours
                + diffusion_scale * self._rng.gauss(0.0, 1.0)
            )
        elif self.simulation_model is SimulationModel.MEAN_REVERTING:
            mean_reversion_per_hour = 0.12
            baseline_log_price = math.log(self.profile.starting_price)
            log_drift = mean_reversion_per_hour * (baseline_log_price - self._log_price)
            log_return = log_drift * dt_hours + diffusion_scale * self._rng.gauss(0.0, 1.0)
        else:
            jump_intensity, jump_size_sigma = self._jump_parameters()
            jump_count = self._poisson_count(jump_intensity * dt_hours)
            jump_compensation = jump_intensity * (math.exp(0.5 * jump_size_sigma**2) - 1.0)
            jump_return = sum(
                self._rng.gauss(0.0, jump_size_sigma) for _ in range(jump_count)
            )
            log_return = (
                (-0.5 * sigma * sigma - jump_compensation) * dt_hours
                + diffusion_scale * self._rng.gauss(0.0, 1.0)
                + jump_return
            )

        self._log_price += log_return
        self._bar_close = math.exp(self._log_price)
        self._bar_high = max(self._bar_high, self._bar_close)
        self._bar_low = min(self._bar_low, self._bar_close)
        if (
            self.simulation_model is SimulationModel.REGIME_SWITCHING
            and self._regime_name not in self._bar_regimes
        ):
            self._bar_regimes.append(self._regime_name)

        move_scale = max(diffusion_scale, self._EPSILON)
        move_activity = 1.0 + self.profile.return_volume_sensitivity * (
            min(abs(log_return) / move_scale, 8.0)
        )
        volume_noise = self._rng.lognormvariate(
            -0.5 * self.profile.volume_noise_sigma**2,
            self.profile.volume_noise_sigma,
        )
        self._bar_volume += (
            self.profile.mean_volume_per_hour
            * dt_hours
            * activity
            * move_activity
            * volume_noise
        )

    def _finish_bar(self) -> OHLCVBar:
        closed = self._snapshot(is_closed=True)
        self._bar_start_seconds += self.interval_seconds
        self._bar_elapsed_seconds = 0.0
        self._bar_open = self._bar_close
        self._bar_high = self._bar_close
        self._bar_low = self._bar_close
        self._bar_volume = 0.0
        self._bar_regimes = (
            [self._regime_name]
            if self.simulation_model is SimulationModel.REGIME_SWITCHING
            else []
        )
        return closed

    def _snapshot(self, *, is_closed: bool) -> OHLCVBar:
        volume = self._bar_volume
        if self.asset_class is AssetClass.STOCKS:
            volume = float(round(volume))
        else:
            volume = round(volume, 8)
        return OHLCVBar(
            open=self._bar_open,
            high=self._bar_high,
            low=self._bar_low,
            close=self._bar_close,
            volume=volume,
            interval_seconds=self.interval_seconds,
            start_simulated_seconds=self._bar_start_seconds,
            elapsed_simulated_seconds=self._bar_elapsed_seconds,
            simulation_model=self.simulation_model.value,
            regimes=tuple(self._bar_regimes),
            price_unit=self.profile.price_unit,
            volume_unit=self.profile.volume_unit,
            is_synthetic=True,
            is_closed=is_closed,
        )

    def _transition_regime(self) -> None:
        if self.simulation_model is not SimulationModel.REGIME_SWITCHING:
            return
        current = self.profile.regimes[self._regime_name]
        if current.next_regimes:
            self._regime_name = self._weighted_choice(current.next_regimes)
        self._regime_time_remaining = self._sample_regime_duration()

    def _sample_regime_duration(self) -> float:
        mean_seconds = self.profile.regimes[self._regime_name].mean_duration_hours * 3_600.0
        return max(self._rng.expovariate(1.0 / mean_seconds), 1e-6)

    def _calibration_regime(self) -> Regime:
        return self.profile.regimes.get("sideways", next(iter(self.profile.regimes.values())))

    def _jump_parameters(self) -> tuple[float, float]:
        if self.asset_class is AssetClass.STOCKS:
            return 0.06, 0.02
        return 0.22, 0.045

    def _poisson_count(self, expected_events: float) -> int:
        """Draw an exact Poisson count with Knuth's method."""

        threshold = math.exp(-expected_events)
        product = 1.0
        count = 0
        while product > threshold:
            count += 1
            product *= self._rng.random()
        return count - 1

    def _weighted_choice(self, weights: Mapping[str, float]) -> str:
        total = sum(weights.values())
        draw = self._rng.random() * total
        cumulative = 0.0
        last_name: str | None = None
        for name, weight in weights.items():
            last_name = name
            cumulative += weight
            if draw < cumulative:
                return name
        if last_name is None:
            raise ValueError("Cannot choose from an empty weight mapping")
        return last_name

    @staticmethod
    def _positive_finite(name: str, value: float) -> float:
        numeric = float(value)
        if not math.isfinite(numeric) or numeric <= 0.0:
            raise ValueError(f"{name} must be finite and greater than zero")
        return numeric

    @staticmethod
    def _validate_profile(profile: RegimeSwitchingProfile) -> None:
        if not math.isfinite(profile.starting_price) or profile.starting_price <= 0.0:
            raise ValueError("Profile starting_price must be finite and greater than zero")
        if not math.isfinite(profile.mean_volume_per_hour) or profile.mean_volume_per_hour <= 0.0:
            raise ValueError("Profile mean_volume_per_hour must be finite and greater than zero")
        if not math.isfinite(profile.volume_noise_sigma) or profile.volume_noise_sigma < 0.0:
            raise ValueError("Profile volume_noise_sigma must be finite and non-negative")
        if (
            not math.isfinite(profile.return_volume_sensitivity)
            or profile.return_volume_sensitivity < 0.0
        ):
            raise ValueError("Profile return_volume_sensitivity must be finite and non-negative")
        if not profile.regimes:
            raise ValueError("Profile must define at least one regime")

        for name, regime in profile.regimes.items():
            if name != regime.name:
                raise ValueError(f"Regime key {name!r} must match its name {regime.name!r}")
            values = (
                regime.drift_per_hour,
                regime.volatility_per_sqrt_hour,
                regime.volume_activity,
                regime.mean_duration_hours,
            )
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"Regime {name!r} parameters must be finite")
            if regime.volatility_per_sqrt_hour <= 0.0:
                raise ValueError(f"Regime {name!r} volatility must be greater than zero")
            if regime.volume_activity <= 0.0 or regime.mean_duration_hours <= 0.0:
                raise ValueError(f"Regime {name!r} activity and duration must be greater than zero")
            for target, weight in regime.next_regimes.items():
                if target not in profile.regimes:
                    raise ValueError(f"Regime {name!r} transitions to undefined regime {target!r}")
                if not math.isfinite(weight) or weight < 0.0:
                    raise ValueError(f"Transition weights for {name!r} must be finite and non-negative")
            if regime.next_regimes and sum(regime.next_regimes.values()) <= 0.0:
                raise ValueError(f"Regime {name!r} transition weights must sum to greater than zero")

        if not profile.initial_regime_weights:
            raise ValueError("Profile must define initial regime weights")
        for name, weight in profile.initial_regime_weights.items():
            if name not in profile.regimes:
                raise ValueError(f"Initial regime weights include undefined regime {name!r}")
            if not math.isfinite(weight) or weight < 0.0:
                raise ValueError("Initial regime weights must be finite and non-negative")
        if sum(profile.initial_regime_weights.values()) <= 0.0:
            raise ValueError("Initial regime weights must sum to greater than zero")


PriceSimulator = RegimeSwitchingSimulator


def create_simulator(
    asset_class: AssetClass | str,
    bar_interval: str,
    *,
    simulation_model: SimulationModel | str = SimulationModel.REGIME_SWITCHING,
    wall_seconds_per_bar: float = 3.0,
    max_internal_step_seconds: float = 5.0,
    seed: int | None = None,
    profile: RegimeSwitchingProfile | None = None,
) -> PriceSimulator:
    """Create an OHLCV simulator using the selected price-path model."""

    return PriceSimulator(
        asset_class,
        bar_interval,
        wall_seconds_per_bar=wall_seconds_per_bar,
        max_internal_step_seconds=max_internal_step_seconds,
        seed=seed,
        profile=profile,
        simulation_model=simulation_model,
    )
