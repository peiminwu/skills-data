#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import akshare as ak
import pandas as pd
from xlsxwriter.utility import xl_rowcol_to_cell


@dataclass(frozen=True)
class IndexSpec:
    key: str
    label: str
    source: str
    symbol: str
    adjust: str = "qfq"


@dataclass(frozen=True)
class WindowConfig:
    start: pd.Timestamp | None
    end: pd.Timestamp
    fetch_start: pd.Timestamp
    latest_only: bool
    trading_days: int | None


DEFAULT_SPECS: list[IndexSpec] = [
    IndexSpec(key=".INX", label="标普", source="us", symbol=".INX"),
    IndexSpec(key=".IXIC", label="纳斯达克", source="us", symbol=".IXIC"),
    IndexSpec(key="HSI", label="恒指", source="hk", symbol="HSI"),
    IndexSpec(key="sh000300", label="沪深300", source="cn_a_tx", symbol="sh000300"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="抓取多市场指数价格并计算过去一段时间的日回报。"
    )
    parser.add_argument("--days", type=int, help="统计最近多少个自然日。")
    parser.add_argument("--start", help="起始日期，格式 YYYY-MM-DD。")
    parser.add_argument("--end", help="结束日期，格式 YYYY-MM-DD，默认今天。")
    parser.add_argument(
        "--buffer-days",
        type=int,
        default=14,
        help="为回报计算额外回看的自然日天数，默认 14。",
    )
    parser.add_argument(
        "--symbols",
        help="逗号分隔，只运行默认指数池中的部分标的，例如 .INX,.IXIC,HSI。",
    )
    parser.add_argument(
        "--config",
        help="自定义 JSON 配置文件路径。配置文件为对象数组，字段包含 key/label/source/symbol。",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="输出目录，默认当前工作目录下的 output。",
    )
    return parser.parse_args()


def parse_date(value: str) -> pd.Timestamp:
    return pd.Timestamp(datetime.strptime(value, "%Y-%m-%d").date())


def resolve_window(args: argparse.Namespace) -> WindowConfig:
    end = parse_date(args.end) if args.end else pd.Timestamp(datetime.now().date())
    latest_only = args.days is None and args.start is None and args.end is None

    if args.start:
        start = parse_date(args.start)
    elif args.days is not None:
        start = None
    else:
        start = end

    if start is not None and start > end:
        raise ValueError("start 不能晚于 end。")

    reference_start = start if start is not None else end
    fetch_start = reference_start - pd.Timedelta(days=max(args.buffer_days, 1))
    if latest_only:
        fetch_start = end - pd.Timedelta(days=max(args.buffer_days, 14))

    if args.days is not None:
        fetch_start = end - pd.Timedelta(days=max(args.days * 3, args.buffer_days, 30))

    return WindowConfig(
        start=start,
        end=end,
        fetch_start=fetch_start,
        latest_only=latest_only,
        trading_days=args.days,
    )


def load_specs(args: argparse.Namespace) -> list[IndexSpec]:
    if args.config:
        config_path = Path(args.config)
        specs_data = json.loads(config_path.read_text(encoding="utf-8"))
        return [IndexSpec(**item) for item in specs_data]

    specs = DEFAULT_SPECS
    if not args.symbols:
        return specs

    requested = [item.strip() for item in args.symbols.split(",") if item.strip()]
    allowed = {spec.key: spec for spec in specs}
    missing = [item for item in requested if item not in allowed]
    if missing:
        raise ValueError(f"未在默认指数池中找到: {', '.join(missing)}")
    return [allowed[item] for item in requested]


def normalize_price_frame(df: pd.DataFrame, label: str) -> pd.DataFrame:
    if df is None or df.empty:
        raise ValueError("返回空数据。")

    frame = df.copy()
    if "date" in frame.columns:
        date_series = frame["date"]
    elif "index" in frame.columns:
        date_series = frame["index"]
    else:
        date_series = frame.index

    frame["date"] = pd.to_datetime(date_series, errors="coerce")
    if frame["date"].isna().all():
        raise ValueError("无法识别日期列。")

    if "close" not in frame.columns:
        raise ValueError("缺少 close 列。")

    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame[["date", "close"]].dropna(subset=["date"]).sort_values("date")
    frame = frame.drop_duplicates(subset=["date"], keep="last")
    return frame.rename(columns={"close": f"{label}_close"})


def fetch_us(spec: IndexSpec, fetch_start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    del fetch_start, end
    return normalize_price_frame(ak.stock_us_daily(symbol=spec.symbol, adjust=spec.adjust), spec.label)


def fetch_hk(spec: IndexSpec, fetch_start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    del fetch_start, end
    return normalize_price_frame(ak.stock_hk_daily(symbol=spec.symbol, adjust=spec.adjust), spec.label)


def fetch_cn_a_tx(spec: IndexSpec, fetch_start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    df = ak.stock_zh_a_hist_tx(
        symbol=spec.symbol,
        start_date=fetch_start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust=spec.adjust,
    )
    return normalize_price_frame(df, spec.label)


FETCHERS: dict[str, Callable[[IndexSpec, pd.Timestamp, pd.Timestamp], pd.DataFrame]] = {
    "us": fetch_us,
    "hk": fetch_hk,
    "cn_a_tx": fetch_cn_a_tx,
}


def fetch_price_table(
    specs: list[IndexSpec], window: WindowConfig
) -> tuple[pd.DataFrame, list[str]]:
    merged: pd.DataFrame | None = None
    errors: list[str] = []

    for spec in specs:
        fetcher = FETCHERS.get(spec.source)
        if fetcher is None:
            errors.append(f"{spec.label}: 不支持的数据源 {spec.source}")
            continue

        try:
            frame = fetcher(spec, window.fetch_start, window.end)
            frame = frame[(frame["date"] >= window.fetch_start) & (frame["date"] <= window.end)].copy()
            if frame.empty:
                raise ValueError("窗口内没有可用数据。")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{spec.label}: {exc}")
            continue

        merged = frame if merged is None else merged.merge(frame, on="date", how="outer")

    if merged is None or merged.empty:
        raise RuntimeError("所有指数都抓取失败，没有可导出的数据。")

    merged = merged.sort_values("date").reset_index(drop=True)
    merged["weekday"] = merged["date"].dt.day_name()
    return merged, errors


def build_output_frame(price_df: pd.DataFrame, specs: list[IndexSpec], window: WindowConfig) -> pd.DataFrame:
    output_df = price_df.copy()
    return_columns: list[str] = []
    close_columns: list[str] = []

    for spec in specs:
        close_col = f"{spec.label}_close"
        if close_col not in output_df.columns:
            continue

        return_col = f"{spec.label}_日回报"
        previous_valid_close = output_df[close_col].ffill().shift(1)
        output_df[return_col] = output_df[close_col].div(previous_valid_close).sub(1).mul(100).round(1)
        output_df[return_col] = output_df[return_col].astype(object)
        output_df.loc[output_df[close_col].isna(), return_col] = "休市"
        return_columns.append(return_col)
        close_columns.append(close_col)

    if window.latest_only:
        valid_rows = output_df[(output_df["date"] >= window.fetch_start) & (output_df["date"] <= window.end)]
        latest_trade_date = valid_rows["date"].max()
        if pd.isna(latest_trade_date):
            raise RuntimeError("未找到最新交易日。")
        output_df = output_df[output_df["date"] == latest_trade_date].reset_index(drop=True)
    elif window.trading_days is not None:
        valid_rows = output_df[output_df["date"] <= window.end].copy()
        available_close_columns = [column for column in close_columns if column in valid_rows.columns]
        valid_rows = valid_rows[valid_rows[available_close_columns].notna().any(axis=1)]
        output_df = valid_rows.tail(window.trading_days).reset_index(drop=True)
        if output_df.empty:
            raise RuntimeError("指定交易日窗口内没有可导出的数据。")
    else:
        output_df = output_df[
            (output_df["date"] >= window.start) & (output_df["date"] <= window.end)
        ].reset_index(drop=True)
        if output_df.empty:
            raise RuntimeError("指定区间内没有可导出的交易日数据。")

    ordered_columns = ["date", "weekday", *return_columns, *close_columns]
    remaining_columns = [column for column in output_df.columns if column not in ordered_columns]
    output_df = output_df[[*ordered_columns, *remaining_columns]]
    output_df["date"] = output_df["date"].dt.strftime("%Y-%m-%d")
    return output_df


def export_results(output_df: pd.DataFrame, specs: list[IndexSpec], output_dir: Path) -> Path:
    actual_dates = pd.to_datetime(output_df["date"], errors="coerce")
    last_trade_date = actual_dates.max()
    if pd.isna(last_trade_date):
        raise RuntimeError("无法确定最后交易日。")

    output_dir.mkdir(parents=True, exist_ok=True)
    xlsx_path = output_dir / f"index_returns_{last_trade_date.strftime('%Y%m%d')}.xlsx"

    with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
        output_df.to_excel(writer, sheet_name="returns", index=False)

        workbook = writer.book
        worksheet = writer.sheets["returns"]
        percent_point_format = workbook.add_format({"num_format": '0.0"%"'})
        green_format = workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})
        red_format = workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
        center_format = workbook.add_format({"align": "center", "valign": "vcenter"})
        center_percent_format = workbook.add_format(
            {"num_format": '0.0"%"', "align": "center", "valign": "vcenter"}
        )

        header = output_df.columns.tolist()
        for col_idx, column_name in enumerate(header):
            worksheet.write(0, col_idx, column_name, center_format)

        for spec in specs:
            return_col = f"{spec.label}_日回报"
            if return_col not in header:
                continue

            col_idx = header.index(return_col)
            worksheet.set_column(col_idx, col_idx, 12, center_percent_format)
            for row_idx, value in enumerate(output_df[return_col], start=1):
                if isinstance(value, (int, float)) and not pd.isna(value):
                    worksheet.write_number(row_idx, col_idx, float(value), center_percent_format)
                elif value == "休市":
                    worksheet.write_string(row_idx, col_idx, value, center_format)
            first_cell = xl_rowcol_to_cell(1, col_idx)
            worksheet.conditional_format(
                1,
                col_idx,
                len(output_df),
                col_idx,
                {
                    "type": "formula",
                    "criteria": f'=AND(ISNUMBER({first_cell}),{first_cell}>2)',
                    "format": green_format,
                },
            )
            worksheet.conditional_format(
                1,
                col_idx,
                len(output_df),
                col_idx,
                {
                    "type": "formula",
                    "criteria": f'=AND(ISNUMBER({first_cell}),{first_cell}<-2)',
                    "format": red_format,
                },
            )

        worksheet.freeze_panes(1, 0)
        worksheet.set_column(0, 1, 14, center_format)
        worksheet.set_column(2, len(output_df.columns) - 1, 12, center_format)

    return xlsx_path


def main() -> int:
    args = parse_args()
    window = resolve_window(args)
    specs = load_specs(args)

    price_df, errors = fetch_price_table(specs, window)
    output_df = build_output_frame(price_df, specs, window)
    xlsx_path = export_results(output_df, specs, Path(args.output_dir))

    actual_start = output_df["date"].iloc[0]
    actual_end = output_df["date"].iloc[-1]
    print(f"统计区间: {actual_start} 至 {actual_end}")
    print(f"Excel: {xlsx_path.resolve()}")
    if errors:
        print("以下指数抓取失败或被跳过：")
        for message in errors:
            print(f"- {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
