#!/home/chenxiang.101/miniconda3/envs/py312/bin/python
"""Serve the local TimesFM 3.0 checkpoint over HTTP."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from timesfm3 import ModelConfig, TimesFM3Evaluator


class PredictRequest(BaseModel):
    context: list[float] | list[list[float]] = Field(
        ...,
        description="Univariate (T,) or multivariate (V, T) context.",
    )
    horizon: int = Field(..., ge=1, le=2048)
    return_quantiles: bool = True
    use_symmetric_averaging: bool = False


class ServerState:
    def __init__(self, checkpoint: Path, device: str) -> None:
        self.checkpoint = checkpoint
        self.device = self._resolve_device(device)
        self.forecaster = TimesFM3Evaluator(
            ModelConfig(
                checkpoint_path=str(checkpoint),
                per_core_batch_size=1,
                device=self.device,
            )
        )

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but torch.cuda.is_available() is False")
        return device


def _normalize_context(raw: list[float] | list[list[float]]) -> np.ndarray:
    array = np.asarray(raw, dtype=np.float32)
    if array.ndim not in (1, 2):
        raise HTTPException(status_code=400, detail="context must be 1D or 2D numeric array")
    if array.shape[-1] < 32:
        raise HTTPException(status_code=400, detail="context length must be at least 32")
    if not np.isfinite(array).all():
        raise HTTPException(status_code=400, detail="context contains NaN or inf")
    return array


def build_app(state: ServerState) -> FastAPI:
    app = FastAPI(title="TimesFM3 HTTP Server", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "checkpoint": str(state.checkpoint),
            "device": state.device,
            "torch": torch.__version__,
            "cuda_build": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
        }

    @app.post("/predict")
    def predict(request: PredictRequest) -> dict[str, Any]:
        context = _normalize_context(request.context)
        output = next(
            state.forecaster.predict_batch(
                [context],
                horizon=request.horizon,
                return_quantiles=request.return_quantiles,
                use_symmetric_averaging=request.use_symmetric_averaging,
            )
        )
        forecast = np.asarray(output.forecast)
        response: dict[str, Any] = {
            "forecast": forecast.tolist(),
            "forecast_shape": list(forecast.shape),
        }
        if request.return_quantiles:
            quantiles = np.asarray(output.quantiles)
            response["quantiles"] = quantiles.tolist()
            response["quantiles_shape"] = list(quantiles.shape)
        return response

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("/home/chenxiang.101/checkpoints/timesfm-3.0"),
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8333)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.checkpoint.is_dir():
        raise SystemExit(f"checkpoint directory does not exist: {args.checkpoint}")
    for filename in ("config.json", "model.safetensors"):
        if not (args.checkpoint / filename).is_file():
            raise SystemExit(f"checkpoint is incomplete; missing: {args.checkpoint / filename}")
    app = build_app(ServerState(args.checkpoint, args.device))
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
