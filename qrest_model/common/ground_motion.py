"""Ground motion loading and synthesis."""

from __future__ import annotations

from pathlib import Path
import numpy as np

from qrest_model.schema import GroundMotionConfig


def load_ground_motion(config: GroundMotionConfig, base_dir: str | Path = ".") -> dict[str, np.ndarray]:
    dt = config.dt
    n_steps = int(round(config.duration / dt)) + 1
    time = np.arange(n_steps, dtype=float) * dt
    if time.size < 2:
        raise ValueError("ground_motion duration and dt must produce at least two samples.")
    base_dir = Path(base_dir)

    ax = _load_component(config.ax_file, base_dir, time, dt) * config.ax_scale
    ay = _load_component(config.ay_file, base_dir, time, dt) * config.ay_scale
    if config.ax_file is None and config.ay_file is None:
        if config.motion_type == "stochastic":
            ax, ay = _stochastic_motion(time, config.stochastic)
        else:
            ax, ay = _synthetic_motion(time, config.synthetic)
    return {"time": time, "ax": ax, "ay": ay}


def _load_component(path: str | None, base_dir: Path, time: np.ndarray, dt: float) -> np.ndarray:
    if path is None:
        return np.zeros_like(time)
    source_path = base_dir / path
    data = np.loadtxt(source_path, delimiter=None)
    data = np.asarray(data, dtype=float)
    if data.size == 0:
        raise ValueError(f"Ground motion file {source_path} is empty.")
    if not np.all(np.isfinite(data)):
        raise ValueError(f"Ground motion file {source_path} contains NaN or Inf.")
    if data.ndim == 1:
        source_time = np.arange(data.size, dtype=float) * dt
        source_accel = data
    else:
        if data.ndim != 2 or data.shape[1] != 2:
            raise ValueError(
                f"Ground motion file {source_path} must contain one acceleration column or two time/acceleration columns."
            )
        source_time = data[:, 0]
        source_accel = data[:, 1]
        if np.any(np.diff(source_time) <= 0.0):
            raise ValueError(f"Ground motion file {source_path} time column must be strictly increasing.")
        source_dt = np.diff(source_time)
        if source_dt.size and not np.allclose(source_dt, dt, rtol=1.0e-3, atol=1.0e-9):
            raise ValueError(
                f"Ground motion file {source_path} time step is inconsistent with configured dt={dt}."
            )
    if time[-1] > source_time[-1] + 1.0e-9:
        raise ValueError(
            f"ground_motion.duration extends beyond the data range in {source_path}."
        )
    return np.interp(time, source_time, source_accel, left=0.0, right=0.0)


def _synthetic_motion(time: np.ndarray, raw: dict) -> tuple[np.ndarray, np.ndarray]:
    decay = float(raw.get("decay", 0.08))
    envelope = np.exp(-decay * time) * (1.0 - np.exp(-3.0 * time))
    ax = envelope * _synthetic_component(
        time,
        raw.get("components_x"),
        amplitude=float(raw.get("amplitude_x", 0.15)),
        frequency=float(raw.get("frequency_x", 1.2)),
        phase=float(raw.get("phase_x", 0.0)),
    )
    ay = envelope * _synthetic_component(
        time,
        raw.get("components_y"),
        amplitude=float(raw.get("amplitude_y", 0.08)),
        frequency=float(raw.get("frequency_y", 0.8)),
        phase=float(raw.get("phase_y", 0.35)),
    )
    return ax, ay


def _synthetic_component(
    time: np.ndarray,
    components: list[dict] | None,
    *,
    amplitude: float,
    frequency: float,
    phase: float,
) -> np.ndarray:
    if components is None:
        return amplitude * np.sin(2.0 * np.pi * frequency * time + phase)
    values = np.zeros_like(time)
    for index, component in enumerate(components):
        values += float(component.get("amplitude", 0.0)) * np.sin(
            2.0 * np.pi * float(component["frequency"]) * time
            + float(component.get("phase", 0.0))
        )
        if not np.all(np.isfinite(values)):
            raise ValueError(f"synthetic component {index} produced non-finite ground motion.")
    return values


def _stochastic_motion(time: np.ndarray, raw: dict) -> tuple[np.ndarray, np.ndarray]:
    if raw.get("seed") is None:
        raise ValueError("ground_motion stochastic excitation requires an explicit seed.")
    rng = np.random.default_rng(int(raw["seed"]))
    ax = rng.normal(
        float(raw.get("mean_x", raw.get("mean", 0.0))),
        _stochastic_std(raw, "x"),
        size=time.shape,
    )
    ay = rng.normal(
        float(raw.get("mean_y", raw.get("mean", 0.0))),
        _stochastic_std(raw, "y"),
        size=time.shape,
    )
    band = _stochastic_band(raw)
    if band is not None:
        dt = float(time[1] - time[0])
        ax = _band_limit(ax, dt, *band)
        ay = _band_limit(ay, dt, *band)
    if not np.all(np.isfinite(ax)) or not np.all(np.isfinite(ay)):
        raise ValueError("stochastic excitation produced non-finite ground motion.")
    return ax, ay


def _stochastic_std(raw: dict, axis: str) -> float:
    value = raw.get(f"std_{axis}", raw.get(f"amplitude_{axis}", raw.get("std", raw.get("amplitude", 0.05))))
    std = float(value)
    if std < 0.0:
        raise ValueError("stochastic excitation std/amplitude must be non-negative.")
    return std


def _stochastic_band(raw: dict) -> tuple[float | None, float | None] | None:
    band = raw.get("band") or raw.get("frequency_band")
    if band is None:
        return None
    if isinstance(band, dict):
        low = band.get("low_hz", band.get("low"))
        high = band.get("high_hz", band.get("high"))
    else:
        low, high = band
    low_value = None if low is None else float(low)
    high_value = None if high is None else float(high)
    if low_value is not None and low_value < 0.0:
        raise ValueError("stochastic excitation low frequency must be non-negative.")
    if high_value is not None and high_value <= 0.0:
        raise ValueError("stochastic excitation high frequency must be positive.")
    if low_value is not None and high_value is not None and low_value >= high_value:
        raise ValueError("stochastic excitation frequency band must satisfy low < high.")
    return low_value, high_value


def _band_limit(values: np.ndarray, dt: float, low_hz: float | None, high_hz: float | None) -> np.ndarray:
    spectrum = np.fft.rfft(values)
    frequencies = np.fft.rfftfreq(values.size, d=dt)
    mask = np.ones_like(frequencies, dtype=bool)
    if low_hz is not None:
        mask &= frequencies >= low_hz
    if high_hz is not None:
        mask &= frequencies <= high_hz
    spectrum[~mask] = 0.0
    return np.fft.irfft(spectrum, n=values.size)
