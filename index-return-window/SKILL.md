---
name: index-return-window
description: 抓取特定指数过去一段时间的价格与回报，基于 AkShare/Pandas 合并多市场指数数据，计算按交易日对齐的 daily return，并导出一个 xlsx。用户请求包含“回报”且涉及指数、价格、收益计算、导出表格，或要求把抓价/算收益脚本合并成一个工具或 skill 时使用。
---

# Index Return Window

## Purpose

把多市场指数的价格抓取、日期对齐、日回报计算和导出整合成一次执行。

默认支持：
1. 标普 500 (`.INX`)
2. 纳斯达克 (`.IXIC`)
3. 恒生指数 (`HSI`)
4. 沪深 300 (`sh000300`)

## Workflow

1. 优先执行 `scripts/index_return_window.py`，不要再拆成“先抓数、再读 CSV 计算”的两步流程。
2. 如果不传时间参数，默认只输出最新交易日；如果传了 `--days` 或 `--start/--end`，则按指定窗口输出，并额外回看一段缓冲区避免首日回报因为缺少前值而失真。
3. 各指数先单独抓取并标准化为：
   - `date`
   - `<Label>_close`
4. 以 `date` 做外连接合并，保留各市场休市差异。
5. 日回报计算规则：
   - `daily return = 当日收盘价 / 前一个有效收盘价 - 1`
   - 当日无价格时标记为 `休市`
   - 序列首个有效价格且没有前值时留空
6. 只导出到当前工作目录下的 `output/`：
   - `index_returns_<最后交易日>.xlsx`

## Run Pattern

默认执行：

```bash
python3 /Users/pennyair/.codex/skills/index-return-window/scripts/index_return_window.py
```

常用变体：

```bash
python3 /Users/pennyair/.codex/skills/index-return-window/scripts/index_return_window.py --days 60 --symbols .INX,.IXIC,HSI
python3 /Users/pennyair/.codex/skills/index-return-window/scripts/index_return_window.py --end 2026-02-28
python3 /Users/pennyair/.codex/skills/index-return-window/scripts/index_return_window.py --start 2026-01-01 --end 2026-02-28
```

## Parameters

1. `--days`
   可选；表示向前回看多少个自然日。
2. `--start`
   显式起始日期，格式 `YYYY-MM-DD`。
3. `--end`
   显式结束日期，格式 `YYYY-MM-DD`；若不传时间参数，默认以最新交易日作为结果日期。
4. `--symbols`
   逗号分隔，表示只跑默认指数池中的部分指数。
5. `--config`
   可选 JSON 配置文件；只有用户要求默认指数池之外的标的时再使用。

## Implementation Rules

1. 对每个源数据先显式标准化 `date` 和 `close` 列，再合并。
2. 美股接口可能返回较长历史，先抓全量再按窗口过滤，不假设接口支持日期参数。
3. 回报列在 xlsx 中应保留数值；只有休市单元格写 `休市`。
4. 只输出一个 xlsx，不再输出 CSV。
5. 单个指数抓取失败时保留错误并继续处理其他指数。
6. 文件名使用最终表格中的最后交易日，不保留请求结束日或时间戳。

## Output Expectations

1. 最终说明里要写清楚统计区间，例如 `2026-02-01` 到 `2026-02-27`。
2. 若某天某市场休市，xlsx 展示列应明确显示 `休市`，而不是错误地算成 `0`。
3. 如果不传时间参数，结果默认落到最新交易日。
4. 如果用户要新增指数，优先扩展脚本内的 registry；只有需要频繁切换不同标的池时才传 `--config`。
