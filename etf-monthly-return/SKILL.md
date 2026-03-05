---
name: etf-monthly-return
description: 生成 ETF 月度回报表，基于 AkShare/Pandas 抓取 ETF 历史价格，计算月度收益和年初至今收益，并导出 CSV。用户请求“做 ETF 月报”“输出某月末 ETF 回报”“导出包含实际月末交易日的 ETF 表格”“调整 ETF 月报列顺序或文件命名”时使用。
---

# ETF Monthly Return

## Purpose

生成 ETF 月度回报结果表，并输出 CSV 文件。默认输出字段为：
1. `Symbol`
2. `Name`
3. `Monthly Return (%)`
4. `YTD Return (%)`
5. `Month End Date`
6. `Month End Price`
7. `Previous Month End Date`
8. `Previous Month End Price`

## Workflow

1. 优先使用 skill 内置脚本：`scripts/etf_performance.py`。
2. 以目标日期的“已完成月末”为统计口径；如果目标日期尚未到自然月末，则回退到上个月末。
3. 对每个 ETF 提取以下三个锚点价格：
   - 实际月末交易日价格
   - 上月末实际交易日价格
   - 上年末实际交易日价格
4. 计算：
   - `Monthly Return (%) = 月末价格 / 上月末价格 - 1`
   - `YTD Return (%) = 月末价格 / 上年末价格 - 1`
5. 输出一个 CSV 到当前工作目录下的 `output/`：
   - `output/etf_performance_<YYYY-MM-DD>.csv`

## Implementation Rules

1. 对 `date` 列先做 `pd.to_datetime`，再显式 `sort_values('date')`。
2. 不直接使用 `df[df['date'] <= target].iloc[-1]`；先过滤，再检查是否为空。
3. `Month End Date` 必须写实际成交日，不写自然月末占位日期。
4. 列顺序固定为本 skill 定义顺序，除非用户明确要求修改。
5. CSV 编码使用 `utf_8_sig`，避免中文乱码。

## Run Pattern

默认在目标线程工作目录执行：

```bash
python3 /Users/pennyair/.codex/skills/etf-monthly-return/scripts/etf_performance.py --as-of 20260131
```

其中：
1. `--as-of` 格式固定为 `YYYYMMDD`
2. `--as-of` 必须是自然月月末日期
3. CSV 必须保存到当前工作目录下的 `output/`

## Output Expectations

1. 最终结果需要明确说明统计截止日和实际月末交易日。
2. 如果 `2026-01-31` 这类日期不是交易日，输出中必须写明实际使用的是最近交易日，例如 `2026-01-30`。
3. 若单个 ETF 拉数失败，保留错误信息并继续处理剩余 ETF。

详细检查项见：`references/output-spec.md`
