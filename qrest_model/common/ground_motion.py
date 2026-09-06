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
