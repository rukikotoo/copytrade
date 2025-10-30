import json
import os
import time
from decimal import Decimal, ROUND_DOWN
# trade.py

import okx.Account as Account
import okx.Trade as Trade
# ... 其他 import ...
import time
from decimal import Decimal, ROUND_DOWN

# ⬇️ 新增这两个 import
import logging
import os
# 引入OKX SDK和Hyperliquid监控函数
import okx.Account as Account
import okx.Trade as Trade
from monitor import fetch_user_positions # 确保 monitor.py 和此脚本在同一目录

# =======================【1. 核心配置】=======================
# --- 跟单配置 ---
# 设置您希望用于跟单的总名义价值 (USD)。程序会按此比例缩放目标仓位。
MY_TOTAL_COPY_USD = Decimal('100.0')

# 目标钱包地址
TARGET_USER_ADDRESS = "0xc20ac4dc4188660cbf555448af52694ca62b0734"

# --- OKX API 配置 ---
CONFIG_FILE = 'config.json'

# 设置OKX交易环境: "1" for demo trading, "0" for live trading
# 🟢 强烈建议先在模拟盘("1")测试！
FLAG = "1" 

# --- 交易参数 ---
# OKX合约的下单数量精度(sz字段)。如果遇到新币种下单失败，请在此处添加或修改。
# 格式: "交易对": Decimal('精度')
CONTRACT_PRECISION = {
    "BTC-USDT-SWAP": Decimal('0.01'),
    "ETH-USDT-SWAP": Decimal('0.01'),
    "SOL-USDT-SWAP": Decimal('0.1'),
    "BNB-USDT-SWAP": Decimal('1'),
    "DOGE-USDT-SWAP": Decimal('1'),
    "XRP-USDT-SWAP": Decimal('1'),
    # 可根据需要添加更多币种...
}
# ==========================================================

# =======================【2. 初始化与设置】=======================

# --- 读取OKX API配置 ---
api_key, secret_key, passphrase = "", "", ""
if not os.path.exists(CONFIG_FILE):
    print(f"❌ 错误：找不到配置文件 {CONFIG_FILE}。")
    exit()
try:
    with open(CONFIG_FILE, 'r') as f:
        config_data = json.load(f)
    api_key = config_data.get("api_key")
    secret_key = config_data.get("secret_key")
    passphrase = config_data.get("passphrase")
    print("✅ 成功读取OKX配置信息。")
except Exception as e:
    print(f"❌ 读取配置文件时发生错误: {e}")
    exit()

# --- 初始化OKX API客户端 ---
try:
    accountAPI = Account.AccountAPI(api_key, secret_key, passphrase, False, FLAG)
    tradeAPI = Trade.TradeAPI(api_key, secret_key, passphrase, False, FLAG)
    print("✅ OKX API 客户端初始化成功。")
except Exception as e:
    print(f"❌ 初始化OKX API客户端失败: {e}")
    exit()

# =======================【3. 辅助函数】=======================

def prepare_my_positions(okx_positions_data):
    """将OKX API返回的持仓数据整理成易于处理的字典。"""
    my_positions = {}
    if okx_positions_data.get('code') == '0':
        for pos in okx_positions_data.get('data', []):
            if pos.get('pos') and float(pos.get('pos')) != 0:
                instId = pos['instId']
                size = Decimal(pos.get('pos', '0'))
                # ในโหมด net_mode, pos > 0 หมายถึง long, pos < 0 หมายถึง short
                direction_is_buy = True if size > 0 else False
                size = abs(size) # 我们只关心绝对值大小
                my_positions[instId] = {"size": size, "direction_is_buy": direction_is_buy}
    return my_positions


def sync_positions():
    """核心同步逻辑函数，包含获取数据、计算比例、执行交易。"""
    print("\n🚀 开始新一轮持仓同步...")

    # --- 步骤 A: 获取目标持仓 (Hyperliquid) ---
    try:
        target_positions_raw = fetch_user_positions(TARGET_USER_ADDRESS, info=None) or []
        print(f"  - 成功获取目标持仓，共 {len(target_positions_raw)} 个。")
    except Exception as e:
        print(f"  - ❌ 获取目标持仓失败: {e}")
        return # 本轮同步中止

    # --- 步骤 B: 获取我的持仓 (OKX) ---
    try:
        my_positions_raw = accountAPI.get_positions()
        my_positions = prepare_my_positions(my_positions_raw)
        print(f"  - 成功获取我的OKX持仓，共 {len(my_positions)} 个。")
    except Exception as e:
        print(f"  - ❌ 获取我的OKX持仓失败: {e}")
        return # 本轮同步中止

    # --- 步骤 C: 计算缩放比例 ---
    target_total_value_usd = sum(Decimal(str(p['value_usd'])) for p in target_positions_raw)
    scaling_factor = (MY_TOTAL_COPY_USD / target_total_value_usd) if target_total_value_usd > 0 else Decimal('0')
    
    if target_total_value_usd > 0:
        print(f"  - 目标总名义价值: ${target_total_value_usd:,.2f}")
        print(f"  - 我的跟单总名义价值: ${MY_TOTAL_COPY_USD:,.2f}")
        print(f"  - 计算出的缩放比例: {scaling_factor:.6f} (或 {scaling_factor:.2%})")
    else:
        print("  - 目标当前无持仓，将清空所有相关仓位。")

    # --- 步骤 D: 计算缩放后的目标仓位 ---
    scaled_target_positions = {}
    for p in target_positions_raw:
        instId = f"{p['coin']}-USDT-SWAP"
        scaled_size = Decimal(str(p['size'])) * scaling_factor
        scaled_target_positions[instId] = {
            "size": scaled_size,
            "direction_is_buy": p['direction_is_buy'],
            "leverage": str(p.get('leverage', '10')) # 杠杆倍数保持不变
        }

    # --- 步骤 E: 遍历所有相关合约，计算差异并执行交易 ---
    all_instIds = set(scaled_target_positions.keys()) | set(my_positions.keys())
    for instId in all_instIds:
        print(f"\n  --- 正在处理: {instId} ---")
        
        target = scaled_target_positions.get(instId)
        mine = my_positions.get(instId)
        precision = CONTRACT_PRECISION.get(instId)

        if not precision:
            print(f"  - ⚠️ 警告: 未在 `CONTRACT_PRECISION` 中找到 {instId} 的下单精度，跳过此币种。")
            continue

        target_signed_size = target['size'] if target and target['direction_is_buy'] else -target['size'] if target else Decimal('0')
        my_signed_size = mine['size'] if mine and mine['direction_is_buy'] else -mine['size'] if mine else Decimal('0')
        trade_amount = target_signed_size - my_signed_size

        print(f"  - 缩放后目标: {'多' if target_signed_size > 0 else '空' if target_signed_size < 0 else '无'} {abs(target_signed_size):.8f}")
        print(f"  - 我的当前:   {'多' if my_signed_size > 0 else '空' if my_signed_size < 0 else '无'} {abs(my_signed_size):.8f}")

        # 如果差异小于最小精度，则无需操作
        if abs(trade_amount) < precision:
            print(f"  - ✅ 仓位已同步或差异过小，无需操作。")
            continue

        trade_side = "buy" if trade_amount > 0 else "sell"
        # 使用精度对下单数量进行向下取整，避免超量
        trade_size_str = str(abs(trade_amount).quantize(precision, rounding=ROUND_DOWN))

        if Decimal(trade_size_str) == 0:
            print(f"  - ✅ 调整量小于最小精度({precision})，忽略。")
            continue

        print(f"  - ➡️ 准备执行操作: {trade_side.upper()} {trade_size_str} {instId}")

        # 下单前，先确保杠杆设置正确
        if target:
            res_lev = accountAPI.set_leverage(instId=instId, lever=target['leverage'], mgnMode="cross")
            if res_lev['code'] != '0':
                print(f"  - ❌ 设置杠杆失败: {res_lev.get('data', [{}])[0].get('sMsg')}，跳过此订单。")
                continue

        # 执行市价单
        result = tradeAPI.place_order(
            instId=instId, tdMode="cross", side=trade_side,
            posSide="net", ordType="market", sz=trade_size_str
        )

        if result.get("code") == "0":
            print(f"  - ✅ 订单请求成功, 订单ID: {result.get('data', [{}])[0].get('ordId')}")
        else:
            data = result.get('data', [{}])[0]
            print(f"  - ❌ 订单请求失败, Code: {data.get('sCode')}, Msg: {data.get('sMsg')}")
            
    print("\n✅ 本轮同步操作完成！")
# 位于 sync_positions() 函数与 if __name__ == "__main__": 之间

# =======================【3.5 记录盈亏快照】=======================
def log_pnl_snapshot(account_api, pnl_logger, note=""):
    """
    获取当前账户的盈亏快照并记录到日志中。
    :param account_api: Account API 实例
    :param pnl_logger: 配置好的 logger 实例
    :param note: 本次记录的备注信息
    """
    try:
        # 1. 获取账户总权益
        res_balance = account_api.get_account_balance()
        total_equity = "N/A"
        if res_balance.get('code') == '0' and res_balance.get('data'):
            # totalEq 是以USD计价的账户总权益，是衡量总体盈亏最核心的指标
            total_equity = res_balance['data'][0].get('totalEq', 'N/A')

        # 2. 获取所有持仓的未实现盈亏
        res_positions = account_api.get_positions()
        total_unrealized_pnl = Decimal('0')
        positions_count = 0
        if res_positions.get('code') == '0' and res_positions.get('data'):
            positions_data = res_positions['data']
            positions_count = len(positions_data)
            for pos in positions_data:
                # upl 是未实现盈亏
                total_unrealized_pnl += Decimal(pos.get('upl', '0'))
        
        # 格式化为两位小数
        total_unrealized_pnl = f"{total_unrealized_pnl:.2f}"

        # 3. 准备写入日志
        # 我们使用 info 级别来记录，日志消息的格式要严格对应CSV的列
        log_message = f"{total_equity},{total_unrealized_pnl},{positions_count},{note}"
        pnl_logger.info(log_message)
        
        print(f"💰 已记录盈亏快照: 总权益 ${total_equity}, 未实现盈亏 ${total_unrealized_pnl}, 持仓数 {positions_count}")

    except Exception as e:
        print(f"❌ 记录盈亏快照时发生错误: {e}")
        pnl_logger.error(f"N/A,N/A,N/A,记录时发生错误: {e}")
# =======================【4. 主程序入口】=======================
if __name__ == "__main__":
    
    # --- 初始化 API 客户端 (这部分您已经有了，保持不变) ---
    # ... 您的 API 客户端初始化代码 ...
    
    # --- 关键：初始化盈亏日志记录器 ---
    log_file = 'pnl_log.csv'
    # 检查日志文件是否存在，如果不存在，则先写入CSV表头
    write_header = not os.path.exists(log_file)

    pnl_logger = logging.getLogger('pnl_logger')
    pnl_logger.setLevel(logging.INFO)
    # 使用 FileHandler 将日志写入文件
    handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    # 定义日志格式：时间,消息主体。这样可以直接生成CSV文件
    formatter = logging.Formatter('%(asctime)s,%(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    
    # 防止重复添加 handler
    if not pnl_logger.handlers:
        pnl_logger.addHandler(handler)

    if write_header:
        pnl_logger.info("Timestamp,TotalEquity_USD,UnrealizedPnL_USD,PositionsCount,Note")
    print(f"✅ 盈亏日志将记录在: {log_file}")

    # --- 启动前检查：设置账户为净持仓模式 ---
    print("\n🚦 正在设置账户为净持仓模式 (net_mode)...")
    try:
        # ... 您原有的设置持仓模式的代码块保持不变 ...
        res_mode = accountAPI.set_position_mode(posMode="net_mode")
        if res_mode.get('code') == '0':
            print("✅ 账户持仓模式确认为 净持仓模式 (net_mode)。")
        else:
            # ... 省略错误处理部分，保持原样 ...
            error_message = res_mode.get('msg', '无详细错误信息')
            print(f"❌ 设置净持仓模式失败: {error_message}")
            exit()
    except Exception as e:
        print(f"❌ 调用 set_position_mode 时发生未预料的异常: {e}，程序退出。")
        exit()

    # --- 启动主循环 ---
    print("\n🎉 跟单机器人启动成功！开始监控和同步持仓...")
    
    # 在循环开始前，先记录一次初始状态
    log_pnl_snapshot(accountAPI, pnl_logger, note="机器人启动初始状态")
    
    while True:
        try:
            sync_positions()
            
            # ---【新增】在每轮同步后，记录一次盈亏快照 ---
            print("\n🔍 正在记录当前盈亏快照...")
            log_pnl_snapshot(accountAPI, pnl_logger, note="常规同步后")
            
            # 设定轮询间隔
            wait_seconds = 15
            print(f"\n🕒 等待 {wait_seconds} 秒后进行下一轮同步...")
            time.sleep(wait_seconds)
        except KeyboardInterrupt:
            print("\n🛑 程序被手动中断，正在退出...")
            # 退出前记录最后一次状态
            log_pnl_snapshot(accountAPI, pnl_logger, note="机器人手动停止")
            break
        except Exception as e:
            import traceback
            print(f"\n💥 主循环发生未知错误: {e}")
            traceback.print_exc()
            # 发生错误时也记录一下
            log_pnl_snapshot(accountAPI, pnl_logger, note=f"主循环发生错误: {e}")
            print("🕒 等待 60 秒后重试...")
            time.sleep(60)