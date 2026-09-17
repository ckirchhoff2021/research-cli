#!/home/chenxiang.101/miniconda3/envs/py312/bin/python
"""Client examples for the local TimesFM3 HTTP server."""

from __future__ import annotations

import argparse
import json
import math
import urllib.request


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode())


def _post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode())


def make_univariate_context(length: int = 256) -> list[float]:
    return [
        50.0 + 0.12 * step + 8.0 * math.sin(2.0 * math.pi * step / 24.0)
        for step in range(length)
    ]


def make_multivariate_context(length: int = 256) -> list[list[float]]:
    return [
        [50.0 + 0.08 * step + 6.0 * math.sin(2.0 * math.pi * step / 24.0) for step in range(length)],
        [20.0 + 0.03 * step + 3.0 * math.cos(2.0 * math.pi * step / 12.0) for step in range(length)],
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://10.37.9.155:8333")
    args = parser.parse_args()

    health = _get_json(f"{args.base_url}/health")
    print("== health ==")
    print(json.dumps(health, ensure_ascii=False, indent=2))

    univariate_payload = {
        "context": make_univariate_context(),
        "horizon": 12,
        "return_quantiles": True,
        "use_symmetric_averaging": False,
    }
    univariate = _post_json(f"{args.base_url}/predict", univariate_payload)
    print("\n== univariate predict ==")
    print("forecast_shape =", univariate["forecast_shape"])
    print("quantiles_shape =", univariate.get("quantiles_shape"))
    print("forecast[:3] =", [round(value, 4) for value in univariate["forecast"][:3]])
    print("quantiles[0] =", [round(value, 4) for value in univariate["quantiles"][0]])

    multivariate_payload = {
        "context": make_multivariate_context(),
        "horizon": 8,
        "return_quantiles": True,
        "use_symmetric_averaging": False,
    }
    multivariate = _post_json(f"{args.base_url}/predict", multivariate_payload)
    print("\n== multivariate predict ==")
    print("forecast_shape =", multivariate["forecast_shape"])
    print("quantiles_shape =", multivariate.get("quantiles_shape"))
    print("forecast[0][:3] =", [round(value, 4) for value in multivariate["forecast"][0][:3]])
    print("forecast[1][:3] =", [round(value, 4) for value in multivariate["forecast"][1][:3]])

    print("\nDone.")


if __name__ == "__main__":
    main()
