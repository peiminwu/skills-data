import akshare as ak
import pandas as pd
import argparse
from datetime import datetime, timedelta
import calendar
from pathlib import Path

def get_last_month_end(date):
    # 获取上个月最后一天
    first_day = date.replace(day=1)
    last_month_end = first_day - timedelta(days=1)
    return last_month_end

def get_year_end(date):
    # 获取去年最后一天
    year_end = datetime(date.year-1, 12, 31)
    return year_end

def get_month_end(date):
    # 获取当前月最后一天
    _, last_day = calendar.monthrange(date.year, date.month)
    month_end = date.replace(day=last_day)
    if month_end > date:  # 如果月末还没到
        month_end = get_last_month_end(date)
    return month_end

def get_last_trading_row(df, target_date):
    # 获取目标日期之前最近一个交易日的数据
    filtered_df = df[df['date'] <= target_date].sort_values('date')
    if filtered_df.empty:
        return None
    return filtered_df.iloc[-1]

def get_etf_data(symbol, current_date):
    # 获取ETF数据
    try:
        df = ak.stock_us_daily(symbol=symbol, adjust="qfq")
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 获取关键日期
        month_end = get_month_end(current_date)
        prev_month_end = get_last_month_end(month_end)
        year_end = get_year_end(month_end)
        
        # 获取收盘价
        month_end_row = get_last_trading_row(df, month_end)
        prev_month_end_row = get_last_trading_row(df, prev_month_end)
        year_end_row = get_last_trading_row(df, year_end)

        if month_end_row is None or prev_month_end_row is None or year_end_row is None:
            raise ValueError("Missing price data for one or more key dates")

        month_end_price = month_end_row['close']
        prev_month_end_price = prev_month_end_row['close']
        year_end_price = year_end_row['close']
        
        # 计算回报率
        monthly_return = (month_end_price / prev_month_end_price - 1) * 100
        ytd_return = (month_end_price / year_end_price - 1) * 100
        
        return {
            'month_end_price': round(month_end_price, 2),
            'prev_month_end_price': round(prev_month_end_price, 2),
            'year_end_price': round(year_end_price, 2),
            'monthly_return': round(monthly_return, 1),
            'ytd_return': round(ytd_return, 1),
            'month_end_date': month_end_row['date'].strftime('%Y-%m-%d'),
            'prev_month_end_date': prev_month_end_row['date'].strftime('%Y-%m-%d')
        }
    except Exception as e:
        print(f"Error getting data for {symbol}: {str(e)}")
        return None

def parse_args():
    parser = argparse.ArgumentParser(description="生成ETF月度回报CSV")
    parser.add_argument(
        "--as-of",
        help="统计日期，格式 YYYYMMDD，且必须为自然月月末日期",
    )
    return parser.parse_args()

def parse_as_of_date(as_of_value):
    if not as_of_value:
        return datetime.now()

    try:
        as_of_date = datetime.strptime(as_of_value, "%Y%m%d")
    except ValueError as exc:
        raise ValueError("--as-of 格式必须为 YYYYMMDD") from exc

    _, last_day = calendar.monthrange(as_of_date.year, as_of_date.month)
    if as_of_date.day != last_day:
        raise ValueError("--as-of 必须传入自然月月末日期")

    return as_of_date

def main():
    args = parse_args()

    # ETF列表和名称映射
    etf_list = {
        'IVV': 'iShares核心标普500 ETF',
        'EWJ': 'iShares MSCI日本ETF',
        'EZU': 'iShares MSCI欧元区ETF',
        'EEM': 'iShares MSCI新兴市场ETF',
        'MCHI': 'iShares MSCI中国ETF',
        'GOVT': 'iShares美国国债ETF',
        'LQD': 'iShares投资级公司债ETF',
        'GLD': 'SPDR黄金ETF',
        'IBIT': 'iShares比特币信托'
    }
    
    # 获取当前日期
    current_date = parse_as_of_date(args.as_of)
    
    # 创建结果列表
    results = []
    
    # 获取每个ETF的数据
    for symbol, name in etf_list.items():
        data = get_etf_data(symbol, current_date)
        if data:
            results.append({
                'Symbol': symbol,
                'Name': name,
                'Monthly Return (%)': f"{data['monthly_return']:.1f}%",
                'YTD Return (%)': f"{data['ytd_return']:.1f}%",
                'Month End Date': data['month_end_date'],
                'Month End Price': data['month_end_price'],
                'Previous Month End Date': data['prev_month_end_date'],
                'Previous Month End Price': data['prev_month_end_price'],
            })
    
    # 创建DataFrame并保存到CSV
    column_order = [
        'Symbol',
        'Name',
        'Monthly Return (%)',
        'YTD Return (%)',
        'Month End Date',
        'Month End Price',
        'Previous Month End Date',
        'Previous Month End Price',
    ]
    df = pd.DataFrame(results, columns=column_order)

    output_dir = Path.cwd() / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    actual_month_end_date = df['Month End Date'].iloc[0] if not df.empty else get_month_end(current_date).strftime('%Y-%m-%d')
    dated_filename = output_dir / f'etf_performance_{actual_month_end_date}.csv'
    df.to_csv(dated_filename, index=False, encoding='utf_8_sig')

    print(f"数据已保存到{dated_filename}")

if __name__ == "__main__":
    main()
