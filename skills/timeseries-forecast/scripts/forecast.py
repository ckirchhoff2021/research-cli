#!/usr/bin/env python3
"""TimesFM3 时序预测技能核心脚本。

封装 TimesFM3 HTTP 服务（默认 http://10.37.9.155:8333）：
  health     健康检查
  forecast   单变量/多变量预测，支持 CSV/JSON/行内输入、缺失值填充、重采样、
             分位数输出、预留段回测（backtest）与预测图绘制

只依赖 requests / numpy / pandas / Pillow。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

DEFAULT_BASE_URL = os.environ.get("TIMESFM3_BASE_URL", "http://10.37.9.155:8333")
MIN_CONTEXT = 32
MAX_HORIZON = 2048
REPO_OUTPUTS = Path(__file__).resolve().parents[3] / "outputs" / "timesfm_forecast"


# ----------------------------------------------------------------------------
# 服务调用
# ----------------------------------------------------------------------------

class TimesFMError(RuntimeError):
    """服务调用或输入校验错误。"""


def health(base_url: str, timeout: float = 10) -> dict:
    try:
        r = requests.get(f"{base_url}/health", timeout=timeout)
    except requests.RequestException as e:
        raise TimesFMError(f"无法连接服务 {base_url}/health：{e}") from e
    if r.status_code != 200:
        raise TimesFMError(f"健康检查失败 HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def predict(base_url: str, context: np.ndarray, horizon: int,
            return_quantiles: bool = True, use_symmetric_averaging: bool = False,
            timeout: float = 300) -> dict:
    if context.ndim == 1:
        payload_ctx = [float(x) for x in context]
    elif context.ndim == 2:
        payload_ctx = [[float(x) for x in row] for row in context]
    else:
        raise TimesFMError(f"context 只支持 1D/2D，实际 {context.ndim}D")
    payload = {
        "context": payload_ctx,
        "horizon": int(horizon),
        "return_quantiles": bool(return_quantiles),
        "use_symmetric_averaging": bool(use_symmetric_averaging),
    }
    try:
        r = requests.post(f"{base_url}/predict", json=payload, timeout=timeout)
    except requests.RequestException as e:
        raise TimesFMError(f"预测请求失败：{e}") from e
    if r.status_code != 200:
        try:
            detail = r.json()
        except Exception:
            detail = r.text[:300]
        raise TimesFMError(f"预测失败 HTTP {r.status_code}: {json.dumps(detail, ensure_ascii=False)[:400]}")
    return r.json()


# ----------------------------------------------------------------------------
# 数据加载与预处理
# ----------------------------------------------------------------------------

def _fill_frame(df: pd.DataFrame, strategy: str) -> tuple[pd.DataFrame, dict]:
    """把缺失/inf 填充为有限值，返回 (填充后DataFrame, 统计信息)。"""
    stats = {"missing": int(df.isna().sum().sum()),
             "inf": int(np.isinf(df.select_dtypes(include=[np.number]).to_numpy()).sum())}
    df = df.copy()
    df = df.replace([np.inf, -np.inf], np.nan)
    if strategy == "linear":
        df = df.interpolate(method="linear", limit_direction="both")
    elif strategy in ("ffill", "bfill", "mean", "zero"):
        if strategy == "ffill":
            df = df.ffill().bfill()
        elif strategy == "bfill":
            df = df.bfill().ffill()
        elif strategy == "mean":
            df = df.fillna(df.mean(numeric_only=True)).ffill().bfill()
        else:
            df = df.fillna(0.0)
    else:
        raise TimesFMError(f"未知填充策略 {strategy}")
    if not np.isfinite(df.to_numpy(dtype=float)).all():
        raise TimesFMError("缺失值填充后仍存在 NaN/inf（通常是整列为空），请检查数据或更换 --fill 策略")
    stats["filled"] = stats["missing"] + stats["inf"]
    return df, stats


def _normalize_freq(freq: str) -> str:
    """兼容 pandas 2.x 旧频率别名（pandas 3.0 起 H/T/S/M/Y 等大写别名被移除）。"""
    import re
    m = re.fullmatch(r"(\d*)\s*([A-Za-z]+)", str(freq).strip())
    if not m:
        return str(freq)
    num, unit = m.group(1) or "1", m.group(2)
    legacy = {"H": "h", "T": "min", "S": "s", "L": "ms", "U": "us", "N": "ns",
              "M": "ME", "Y": "YE", "Q": "QE"}
    return num + legacy.get(unit, unit)


def load_series(args) -> tuple[np.ndarray, list[str], pd.DatetimeIndex | None, dict]:
    """返回 (values [T] 或 [V,T], 变量名列表, 时间索引或None, 预处理信息)。"""
    info: dict = {}
    if args.values:
        try:
            values = np.array([float(x) for x in args.values.split(",") if x.strip()], dtype=float)
        except ValueError as e:
            raise TimesFMError(f"--values 必须是逗号分隔的数值：{e}") from e
        names = ["series"]
        time_idx = None
    elif args.json:
        data = json.loads(Path(args.json).read_text(encoding="utf-8"))
        if isinstance(data, list) and data and isinstance(data[0], list):
            row_lens = {len(row) for row in data}
            if len(row_lens) != 1:
                raise TimesFMError(
                    f"多变量各序列长度必须一致，实际长度集合 {sorted(row_lens)}")
        try:
            arr = np.array(data, dtype=float)
        except (ValueError, TypeError) as e:
            raise TimesFMError(f"JSON 无法转为规则数值数组（需 1D 或等长 2D）：{e}") from e
        if arr.ndim == 1:
            names = ["series"]
        elif arr.ndim == 2:
            names = [f"series_{i}" for i in range(arr.shape[0])]
            if arr.shape[1] < arr.shape[0] and arr.shape[0] > 1:
                # 约定 API 为 (V,T)；若用户给的是 (T,V) 且 V<T，提示而非静默
                pass
        else:
            raise TimesFMError(f"JSON 只支持 1D/2D 数组，实际 {arr.ndim}D")
        values, time_idx = arr, None
    elif args.csv:
        df = pd.read_csv(args.csv)
        if not args.value_col:
            raise TimesFMError("读取 CSV 时必须用 --value-col 指定数值列（多变量用逗号分隔多个列名）")
        cols = [c.strip() for c in args.value_col.split(",") if c.strip()]
        missing_cols = [c for c in cols if c not in df.columns]
        if missing_cols:
            raise TimesFMError(f"CSV 中找不到列 {missing_cols}；可用列：{list(df.columns)}")
        if args.time_col:
            if args.time_col not in df.columns:
                raise TimesFMError(f"CSV 中找不到时间列 {args.time_col!r}；可用列：{list(df.columns)}")
            df[args.time_col] = pd.to_datetime(df[args.time_col], errors="coerce")
            if df[args.time_col].isna().any():
                raise TimesFMError(f"时间列 {args.time_col!r} 存在无法解析的时间")
            df = df.sort_values(args.time_col).set_index(args.time_col)
        work = df[cols].apply(pd.to_numeric, errors="coerce")
        if args.resample:
            if not args.time_col:
                raise TimesFMError("--resample 需要配合 --time-col 使用")
            args.resample = _normalize_freq(args.resample)
            work = work.resample(args.resample).mean()
            info["resampled_freq"] = args.resample
            info["resampled_len"] = int(len(work))
        work, fill_stats = _fill_frame(work, args.fill)
        info.update({f"fill_{k}": v for k, v in fill_stats.items()})
        time_idx = work.index if args.time_col else None
        values = work.to_numpy(dtype=float).T  # (V, T)
        names = cols
        if values.shape[0] == 1:
            values = values[0]
    else:
        raise TimesFMError("必须提供输入：--csv / --json / --values 三选一")

    # 非 CSV 的 NaN/inf：先尝试按策略填充
    flat_len = values.shape[-1]
    if np.isnan(values).any() or np.isinf(values).any():
        if args.csv:
            raise TimesFMError("内部错误：CSV 预处理后仍有非法值")
        df = pd.DataFrame(values.T if values.ndim == 2 else values.reshape(-1, 1))
        df, stats = _fill_frame(df, args.fill)
        values = df.to_numpy(dtype=float).T if values.ndim == 2 else df.to_numpy(dtype=float).T[0]
        info.update({f"fill_{k}": v for k, v in stats.items()})

    if flat_len < MIN_CONTEXT:
        raise TimesFMError(f"时间长度至少 {MIN_CONTEXT} 个点，实际 {flat_len}（TimesFM 服务硬性约束）")
    if values.ndim == 2:
        lens = {len(row) for row in values}
        if len(lens) != 1:
            raise TimesFMError("多变量各序列长度必须一致（服务端也会以 400 拒绝不等长输入）")
    if not np.isfinite(np.asarray(values, dtype=float)).all():
        raise TimesFMError("context 不能包含 NaN/inf：请用 --fill 指定填充策略")
    return values, names, time_idx, info


# ----------------------------------------------------------------------------
# 指标
# ----------------------------------------------------------------------------

def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    err = y_pred - y_true
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    denom = np.maximum(np.abs(y_true), 1e-8)
    mape = float(np.mean(np.abs(err) / denom) * 100)
    naive = np.full_like(y_true, y_true[0] if len(y_true) else 0.0)
    # 朴素基线：用留出段起点之前的最后一个历史值平移
    mae_naive = float(np.mean(np.abs(naive - y_true)))
    improve = float((1 - mae / mae_naive) * 100) if mae_naive > 1e-12 else 0.0
    return {"mae": round(mae, 6), "rmse": round(rmse, 6), "mape_pct": round(mape, 3),
            "mae_naive_baseline": round(mae_naive, 6),
            "improvement_vs_naive_pct": round(improve, 1)}


# ----------------------------------------------------------------------------
# 绘图（Pillow，无 matplotlib 依赖）
# ----------------------------------------------------------------------------

def _load_font(size: int):
    from PIL import ImageFont
    for fp in ("/System/Library/Fonts/STHeiti Light.ttc", "/System/Library/Fonts/PingFang.ttc",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
               "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_chart(panels: list[dict], path: Path, suptitle: str) -> None:
    from PIL import Image, ImageDraw
    font_title, font_name, font_small = _load_font(18), _load_font(15), _load_font(13)

    n = len(panels)
    cols = 1 if n <= 2 else 2
    rows = math.ceil(n / cols)
    pw, ph, gap = 760, 260, 26
    ml, mr, mt, mb = 64, 20, 46, 34
    W = cols * pw + (cols + 1) * gap
    H = mt + rows * ph + (rows - 1) * gap + mb + 24
    img = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(img, "RGBA")
    dr.text((W // 2, 16), suptitle, fill=(30, 30, 30), anchor="ma", font=font_title)
    BLUE, RED, GRID, GRAY = (59, 110, 165), (209, 73, 91), (235, 235, 235), (150, 150, 150)

    for idx, p in enumerate(panels):
        r, c = divmod(idx, cols)
        x0 = gap + c * (pw + gap)
        y0 = mt + r * (ph + gap)
        iw, ih = pw - ml - mr, ph - 24 - mb
        hist_full, fc, q = p["hist"], p.get("fc"), p.get("q")
        hist = hist_full[:-len(p["bt_true"])] if p.get("bt_true") is not None else hist_full
        bt_true, bt_fc = p.get("bt_true"), p.get("bt_fc")
        pieces = [hist]
        if bt_true is not None:
            pieces += [bt_true]
        if q is not None:
            pieces.append(q.ravel())
        if fc is not None:
            pieces.append(fc)
        allv = np.concatenate(pieces)
        ymin, ymax = float(allv.min()), float(allv.max())
        ymin -= (ymax - ymin) * 0.06 or 0.5
        ymax += (ymax - ymin) * 0.06 or 0.5
        total_t = len(hist) + (len(bt_true) if bt_true is not None else 0) + (len(fc) if fc is not None else 0)

        def X(i):
            return x0 + ml + i / max(total_t - 1, 1) * iw

        def Y(v):
            return y0 + 24 + (ymax - v) / (ymax - ymin) * ih

        for gy in np.linspace(ymin, ymax, 5):
            yy = Y(gy)
            dr.line([(x0 + ml, yy), (x0 + pw - mr, yy)], fill=GRID)
            dr.text((x0 + ml - 8, yy - 5), f"{gy:.2g}", fill=(130, 130, 130), anchor="rs")
        cut = len(hist) - 1
        dr.line([(X(cut), y0 + 24), (X(cut), y0 + 24 + ih)], fill=GRAY, width=1)
        if bt_true is not None and fc is not None:
            cut2 = len(hist) + len(bt_true) - 1
            dr.line([(X(cut2), y0 + 24), (X(cut2), y0 + 24 + ih)], fill=GRAY, width=1)
        dr.text((x0 + ml + 8, y0 + 6), p["name"], fill=(40, 40, 40), font=font_name)

        if q is not None and fc is not None:
            base = len(hist) + (len(bt_true) if bt_true is not None else 0)
            tf = np.arange(base, base + len(fc))
            band = ([(X(i), Y(v)) for i, v in zip(tf, q[:, 0])]
                    + [(X(i), Y(v)) for i, v in zip(tf[::-1], q[::-1, -1])])
            dr.polygon(band, fill=RED + (22,))
        dr.line([(X(i), Y(v)) for i, v in enumerate(hist)], fill=BLUE, width=2)
        if bt_true is not None and bt_fc is not None:
            tt = np.arange(len(hist), len(hist) + len(bt_true))
            dr.line([(X(i), Y(v)) for i, v in zip(tt, bt_true)], fill=(60, 160, 90), width=2)
            dr.line([(X(i), Y(v)) for i, v in zip(tt, bt_fc)], fill=(230, 150, 40), width=2)
        if fc is not None:
            base = len(hist) + (len(bt_true) if bt_true is not None else 0)
            tf = np.arange(base, base + len(fc))
            dr.line([(X(i), Y(v)) for i, v in zip(tf, fc)], fill=RED, width=2)
    dr.text((gap, H - 20), "蓝=历史　红=未来预测　绿=回测真实值　橙=回测预测　红带=分位数区间",
            fill=(110, 110, 110), font=font_small)
    img.save(path)


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------

def cmd_health(args):
    info = health(args.base_url)
    print(json.dumps(info, ensure_ascii=False, indent=2))


def cmd_forecast(args):
    t_start = time.time()
    values, names, time_idx, prep_info = load_series(args)
    multivariate = values.ndim == 2
    V = values.shape[0] if multivariate else 1
    T = values.shape[-1]
    if not 1 <= args.horizon <= MAX_HORIZON:
        raise TimesFMError(f"horizon 必须在 1..{MAX_HORIZON} 之间，实际 {args.horizon}")

    out_dir = Path(args.out) if args.out else REPO_OUTPUTS / time.strftime("run_%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    result = {"base_url": args.base_url, "params": {
        "context_len": int(T), "variates": int(V), "names": names,
        "horizon": args.horizon, "return_quantiles": args.quantiles,
        "use_symmetric_averaging": args.symmetric_averaging,
    }, "preprocessing": prep_info}

    # ---- 回测：用末尾 backtest 段做留出评估 ----
    backtest = None
    bt_forecast = None
    if args.backtest:
        bt = min(args.backtest, T - MIN_CONTEXT)
        if bt <= 0:
            raise TimesFMError("backtest 长度过大：留出后剩余上下文不足 32 点")
        bt_ctx = values[..., :T - bt]
        t0 = time.time()
        bt_resp = predict(args.base_url, bt_ctx, bt, return_quantiles=False,
                          use_symmetric_averaging=args.symmetric_averaging)
        bt_latency = round(time.time() - t0, 2)
        bt_fc = np.array(bt_resp["forecast"], dtype=float)
        bt_true = values[..., T - bt:]
        bt_forecast = bt_fc
        if multivariate:
            backtest = {"holdout": bt, "latency_s": bt_latency, "per_variate": {
                names[i]: metrics(bt_true[i], bt_fc[i]) for i in range(V)}}
        else:
            backtest = {"holdout": bt, "latency_s": bt_latency, **metrics(bt_true, bt_fc)}
        result["backtest"] = backtest
        print(f"[回测] 留出最后 {bt} 点："
              + (json.dumps(backtest, ensure_ascii=False) if not multivariate else
                 "；".join(f"{n} MAE={m['mae']}" for n, m in backtest['per_variate'].items())))

    # ---- 正式未来预测 ----
    t0 = time.time()
    resp = predict(args.base_url, values, args.horizon,
                   return_quantiles=args.quantiles,
                   use_symmetric_averaging=args.symmetric_averaging)
    latency = round(time.time() - t0, 2)
    forecast = np.array(resp["forecast"], dtype=float)
    quantiles = np.array(resp["quantiles"], dtype=float) if args.quantiles and resp.get("quantiles") else None
    result["latency_s"] = latency
    result["elapsed_total_s"] = round(time.time() - t_start, 2)
    result["forecast_shape"] = list(forecast.shape)

    # ---- 时间标签 ----
    if time_idx is not None:
        try:
            future_idx = pd.date_range(time_idx[-1], periods=args.horizon + 1,
                                       freq=pd.infer_freq(time_idx) or args.resample or "D")[1:]
            future_labels = [str(x) for x in future_idx]
        except Exception:
            future_labels = list(range(T, T + args.horizon))
    else:
        future_labels = list(range(T, T + args.horizon))

    # ---- 落盘 forecast.csv ----
    if multivariate:
        frame = pd.DataFrame({"step": future_labels})
        for i, name in enumerate(names):
            frame[f"{name}__forecast"] = forecast[i]
            if quantiles is not None:
                for qi, qv in enumerate(quantiles[i].T):
                    frame[f"{name}__q{qi}"] = qv
    else:
        frame = pd.DataFrame({"step": future_labels, "forecast": forecast})
        if quantiles is not None:
            for qi, qv in enumerate(quantiles.T):
                frame[f"q{qi}"] = qv
    csv_path = out_dir / "forecast.csv"
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # ---- summary.json ----
    head = lambda a: [round(float(x), 4) for x in np.asarray(a).reshape(-1)[:6]]
    result["files"] = {"forecast_csv": str(csv_path)}
    result["preview"] = {"forecast_head": (
        {names[i]: head(forecast[i]) for i in range(V)} if multivariate else head(forecast))}
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- 绘图 ----
    panels = []
    bt = args.backtest if args.backtest else 0
    if multivariate:
        for i, name in enumerate(names):
            panels.append({
                "name": name, "hist": values[i], "fc": forecast[i],
                "q": quantiles[i] if quantiles is not None else None,
                "bt_true": values[i, T - bt:] if bt else None,
                "bt_fc": bt_forecast[i] if bt else None,
            })
    else:
        panels.append({
            "name": names[0], "hist": values, "fc": forecast,
            "q": quantiles,
            "bt_true": values[T - bt:] if bt else None,
            "bt_fc": bt_forecast if bt else None,
        })
    chart_path = out_dir / "forecast.png"
    draw_chart(panels, chart_path,
               f"TimesFM3 forecast · context={T}, horizon={args.horizon}, variates={V}")
    result["files"]["chart_png"] = str(chart_path)
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[预测] shape={list(forecast.shape)}，服务耗时 {latency}s，总耗时 {result['elapsed_total_s']}s")
    print(f"[输出] {out_dir}")
    print(json.dumps(result["preview"], ensure_ascii=False, indent=2))


def build_parser():
    p = argparse.ArgumentParser(description="TimesFM3 时序预测技能")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"服务地址，默认 {DEFAULT_BASE_URL}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="检查服务健康状态")

    f = sub.add_parser("forecast", help="时序预测")
    src = f.add_argument_group("输入（三选一）")
    src.add_argument("--csv", help="CSV 文件路径")
    src.add_argument("--json", help="JSON 文件路径：1D 数组 [T] 或 2D 数组 [V,T]")
    src.add_argument("--values", help="行内逗号分隔数值，如 1,2,3,...（单变量）")
    f.add_argument("--value-col", help="CSV 数值列名；多变量传多个列名，逗号分隔")
    f.add_argument("--time-col", help="CSV 时间列名（可被解析为时间）")
    f.add_argument("--resample", help="按 pandas 频率重采样（需 --time-col），如 15min/1H/1D")
    f.add_argument("--fill", default="linear",
                   choices=["linear", "ffill", "bfill", "mean", "zero"],
                   help="缺失值/inf 填充策略，默认 linear 线性插值")
    f.add_argument("--horizon", type=int, default=32, help=f"预测步数 1..{MAX_HORIZON}，默认 32")
    f.add_argument("--quantiles", action=argparse.BooleanOptionalAction, default=True,
                   help="是否返回分位数（默认开启，--no-quantiles 关闭）")
    f.add_argument("--symmetric-averaging", action="store_true", help="透传 TimesFM 对称平均参数")
    f.add_argument("--backtest", type=int, default=0,
                   help="留出末尾 N 个真实点做回测评估（MAE/RMSE/MAPE，并与朴素基线对比）")
    f.add_argument("--out", help="输出目录，默认 outputs/timesfm_forecast/run_<时间戳>")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command == "health":
            cmd_health(args)
        else:
            cmd_forecast(args)
    except TimesFMError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
