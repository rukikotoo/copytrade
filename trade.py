import json
import os
import time
from decimal import Decimal, ROUND_DOWN
import logging
import traceback

# 引入OKX SDK和我们最终确认可用的 monitor.py
import okx.Account as Account
import okx.Trade as Trade
from monitor import fetch_user_positions # 直接使用，无需再传入info客户端

# =======================【1. 核心配置】=======================
MY_TOTAL_COPY_USD = Decimal('10000.0')
TARGET_USER_ADDRESS = "0xc20ac4dc4188660cbf555448af52694ca62b0734"
CONFIG_FILE = 'config.json'
FLAG = "1"

# 目标地址币种数量的精度，保持不变。
CONTRACT_PRECISION = {
    "BTC-USDT-SWAP": Decimal('0.0001'),
    "ETH-USDT-SWAP": Decimal('0.001'),
    "SOL-USDT-SWAP": Decimal('0.01'),
    "BNB-USDT-SWAP": Decimal('0.01'),
    "DOGE-USDT-SWAP": Decimal('10'),
    "XRP-USDT-SWAP": Decimal('1'),
}

# 🚀 【已存在配置】OKX 合约面值 (1张合约 = 多少币)
CONTRACT_FACE_VALUE = {
    "BTC-USDT-SWAP": Decimal('0.01'), 
    "ETH-USDT-SWAP": Decimal('0.1'),
    "SOL-USDT-SWAP": Decimal('1'), 
    "BNB-USDT-SWAP": Decimal('0.01'),
    "DOGE-USDT-SWAP": Decimal('1000'),
    "XRP-USDT-SWAP": Decimal('100'),
    # 🚨 重要：请务必根据 OKX 合约信息核实
}

# 🚀 【新增配置】OKX 合约的最小下单张数单位 (szInc)
# 这是下单时 sz 参数的最小变动增量（Lot Size）。
# 经查，BTC/ETH等主流币最小为0.01张，DOGE/XRP等小币种常为1张。
CONTRACT_LOT_PRECISION = {
    "BTC-USDT-SWAP": Decimal('0.01'),  
    "ETH-USDT-SWAP": Decimal('0.01'),  
    "SOL-USDT-SWAP": Decimal('0.01'),     
    "BNB-USDT-SWAP": Decimal('1'),  
    "DOGE-USDT-SWAP": Decimal('0.01'),    
    "XRP-USDT-SWAP": Decimal('0.01'),     
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

# 【重要改动】我们不再在这里初始化 Hyperliquid 的 Info 客户端
# 因为新版的 monitor.py 会在内部自行处理

# =======================【3. 辅助函数】=======================
# (prepare_my_positions 函数保持不变)
def prepare_my_positions(okx_positions_data):
    my_positions = {}
    if okx_positions_data.get('code') == '0':
        for pos in okx_positions_data.get('data', []):
            if pos.get('pos') and float(pos.get('pos')) != 0:
                instId = pos['instId']
                # 注意：OKX返回的 pos 已经是张数
                size = Decimal(pos.get('pos', '0'))
                direction_is_buy = True if size > 0 else False
                size = abs(size)
                my_positions[instId] = {"size": size, "direction_is_buy": direction_is_buy}
    return my_positions


def sync_positions(target_positions_raw):
    print("\n🚀 开始执行持仓同步...")
    try:
        # 获取我的OKX持仓，注意：OKX返回的持仓 pos 是【张数】
        my_positions_raw = accountAPI.get_positions()
        my_positions = prepare_my_positions(my_positions_raw)
        print(f"  - 成功获取我的OKX持仓，共 {len(my_positions)} 个。")
    except Exception as e:
        print(f"  - ❌ 获取我的OKX持仓失败: {e}")
        return

    target_total_value_usd = sum(p['value_usd'] for p in target_positions_raw) # 返回值已经是Decimal
    scaling_factor = (MY_TOTAL_COPY_USD / target_total_value_usd) if target_total_value_usd > 0 else Decimal('0')
    
    if target_total_value_usd > 0:
        print(f"  - 目标总名义价值: ${target_total_value_usd:,.2f}")
        print(f"  - 我的跟单总名义价值: ${MY_TOTAL_COPY_USD:,.2f}")
        print(f"  - 计算出的缩放比例: {scaling_factor:.6f}")
    else:
        print("  - 目标当前无持仓，将清空所有相关仓位。")

    scaled_target_positions = {}
    for p in target_positions_raw:
        instId = f"{p['coin']}-USDT-SWAP"
        scaled_size = p['size'] * scaling_factor # scaled_size 仍是币的数量（例如 BTC 数量）
        scaled_target_positions[instId] = {
            "size": scaled_size,
            "direction_is_buy": p['direction_is_buy'],
            "leverage": str(p.get('leverage', '10'))
        }

    all_instIds = set(scaled_target_positions.keys()) | set(my_positions.keys())
    for instId in all_instIds:
        print(f"\n  --- 正在处理: {instId} ---")
        
        target = scaled_target_positions.get(instId)
        mine = my_positions.get(instId)
        precision = CONTRACT_PRECISION.get(instId)
        face_value = CONTRACT_FACE_VALUE.get(instId) # 🚨 获取合约面值
        # 🚨 【修改点 1】获取最小张数精度
        lot_precision = CONTRACT_LOT_PRECISION.get(instId) 

        if not precision:
            print(f"  - ⚠️ 警告: 未在 `CONTRACT_PRECISION` 中找到 {instId} 的下单精度，跳过此币种。")
            continue
        if not face_value:
             print(f"  - ⚠️ 警告: 未在 `CONTRACT_FACE_VALUE` 中找到 {instId} 的合约面值，跳过此币种。")
             continue
        if not lot_precision:
             print(f"  - ⚠️ 警告: 未在 `CONTRACT_LOT_PRECISION` 中找到 {instId} 的最小张数精度，跳过此币种。")
             continue


        # 1. 将目标数量（币本位）转换为合约张数
        target_face_value = target['size'] / face_value if target and face_value > 0 else Decimal('0')
        
        # 2. 获取我的当前张数
        my_current_size = mine['size'] if mine else Decimal('0')

        # 3. 计算目标张数和我的张数之间的差值（张数差）
        target_signed_size = target_face_value if target and target['direction_is_buy'] else -target_face_value if target else Decimal('0')
        my_signed_size = my_current_size if mine and mine['direction_is_buy'] else -my_current_size if mine else Decimal('0')
        
        trade_amount_lots = target_signed_size - my_signed_size 
        
        # 将 BTC 数量差值精度转换为张数差值精度进行比较，以保持原有逻辑
        precision_lots = precision / face_value

        print(f"  - 缩放后目标: {'多' if target_signed_size > 0 else '空' if target_signed_size < 0 else '无'} {abs(target_signed_size):.8f} 张")
        print(f"  - 我的当前:   {'多' if my_signed_size > 0 else '空' if my_signed_size < 0 else '无'} {abs(my_signed_size):.8f} 张")

        # 使用张数差值和张数精度进行比较
        if abs(trade_amount_lots) < precision_lots:
            print(f"  - ✅ 仓位已同步或差异过小（小于 {precision_lots:.8f} 张），无需操作。")
            continue

        trade_side = "buy" if trade_amount_lots > 0 else "sell"
        
        # 4. 🚨 【修改点 2】对需要交易的张数向下取整到最近的 lot_precision 张
        trade_size_decimal = abs(trade_amount_lots).quantize(lot_precision, rounding=ROUND_DOWN)
        trade_size_str = str(trade_size_decimal)

        # 最小订单量检查 (最小订单量就是最小增量 lot_precision 张)
        MIN_ORDER_SIZE_LOTS = lot_precision
        if trade_size_decimal < MIN_ORDER_SIZE_LOTS:
            print(f"  - ✅ 调整量 {trade_size_decimal} 张小于最小订单量 {MIN_ORDER_SIZE_LOTS} 张，忽略。")
            continue
            
        print(f"  - ➡️ 准备执行操作: {trade_side.upper()} {trade_size_str} {instId} (张数)")

        if target:
            res_lev = accountAPI.set_leverage(instId=instId, lever=target['leverage'], mgnMode="cross")
            if res_lev['code'] != '0':
                print(f"  - ❌ 设置杠杆失败: {res_lev.get('data', [{}])[0].get('sMsg')}，跳过此订单。")
                continue

        # 5. 使用转换后的张数进行下单
        result = tradeAPI.place_order(
            instId=instId, tdMode="cross", side=trade_side,
            posSide="net", ordType="market", sz=trade_size_str # 传入张数
        )

        if result.get("code") == "0":
            print(f"  - ✅ 订单请求成功, 订单ID: {result.get('data', [{}])[0].get('ordId')}")
        else:
            data = result.get('data', [{}])[0]
            print(f"  - ❌ 订单请求失败, Code: {data.get('sCode')}, Msg: {data.get('sMsg')}")
            
    print("\n✅ 本轮同步操作完成！")


# (log_pnl_snapshot, simplify_positions_for_comparison, check_self_positions_for_stop 等函数保持不变)

def log_pnl_snapshot(account_api, pnl_logger, note=""):
    try:
        res_balance = account_api.get_account_balance()
        total_equity = "N/A"
        if res_balance.get('code') == '0' and res_balance.get('data'):
            total_equity = res_balance['data'][0].get('totalEq', 'N/A')

        res_positions = account_api.get_positions()
        total_unrealized_pnl = Decimal('0')
        positions_count = 0
        if res_positions.get('code') == '0' and res_positions.get('data'):
            active_positions = [p for p in res_positions['data'] if p.get('pos') and float(p.get('pos')) != 0]
            positions_count = len(active_positions)
            for pos in active_positions:
                total_unrealized_pnl += Decimal(pos.get('upl', '0'))
        
        total_unrealized_pnl = f"{total_unrealized_pnl:.2f}"
        log_message = f"{total_equity},{total_unrealized_pnl},{positions_count},{note}"
        pnl_logger.info(log_message)
        print(f"💰 已记录盈亏快照: 总权益 ${total_equity}, 未实现盈亏 ${total_unrealized_pnl}, 持仓数 {positions_count}")

    except Exception as e:
        print(f"❌ 记录盈亏快照时发生错误: {e}")
        pnl_logger.error(f"N/A,N/A,N/A,记录时发生错误: {e}")


def simplify_positions_for_comparison(positions_raw):
    simplified = {}
    if not positions_raw:
        return simplified
    for pos in positions_raw:
        # 确保比较时使用一致的类型
        simplified[pos['coin']] = (Decimal(str(pos['size'])), pos['direction_is_buy'])
    return simplified


def check_self_positions_for_stop(account_api):
    try:
        my_positions_raw = account_api.get_positions()
        if my_positions_raw.get('code') == '0':
            for pos in my_positions_raw.get('data', []):
                if pos.get('pos') and float(pos.get('pos')) != 0:
                    return False
            return True
        else:
            print(f"  - ⚠️ 警告: 检查自身仓位时API调用失败，无法判断是否停止。Code: {my_positions_raw.get('code')}")
            return False
    except Exception as e:
        print(f"  - ❌ 检查自身仓位时发生异常: {e}")
        return False


# =======================【4. 主程序入口】=======================
if __name__ == "__main__":
    
    # 日志和账户模式设置... (无变化)
    log_file = 'pnl_log.csv'
    write_header = not os.path.exists(log_file)
    pnl_logger = logging.getLogger('pnl_logger')
    pnl_logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    formatter = logging.Formatter('%(asctime)s,%(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    handler.setFormatter(formatter)
    if not pnl_logger.handlers:
        pnl_logger.addHandler(handler)
    if write_header:
        pnl_logger.info("Timestamp,TotalEquity_USD,UnrealizedPnL_USD,PositionsCount,Note")
    print(f"✅ 盈亏日志将记录在: {log_file}")

    print("\n🚦 正在设置账户为净持仓模式 (net_mode)...")
    try:
        res_mode = accountAPI.set_position_mode(posMode="net_mode")
        if res_mode.get('code') == '0':
            print("✅ 账户持仓模式确认为 净持仓模式 (net_mode)。")
        else:
            print(f"❌ 设置净持仓模式失败: {res_mode.get('msg', '无详细错误信息')}")
            exit()
    except Exception as e:
        print(f"❌ 调用 set_position_mode 时发生异常: {e}，程序退出。")
        exit()

    # --- 启动前：获取并记录初始状态 ---
    print("\n🔍 正在获取目标初始仓位状态...")
    last_known_simplified_positions = {}
    try:
        # 【重要改动】直接调用，不再传入infoAPI
        initial_target_positions = fetch_user_positions(TARGET_USER_ADDRESS) or []
        
        # 确认获取到的仓位数量
        print(f"  - 成功获取初始状态，目标当前有 {len(initial_target_positions)} 个仓位。")
        if not initial_target_positions:
            print("  - 警告：获取到的目标仓位为空，请确认目标地址是否确实无持仓。")

        last_known_simplified_positions = simplify_positions_for_comparison(initial_target_positions)
        
        # 仅当目标真的有仓位时，才进行初次同步
        if initial_target_positions:
            sync_positions(initial_target_positions)
        
        log_pnl_snapshot(accountAPI, pnl_logger, note="机器人启动初始状态")
        
    except Exception as e:
        print(f"❌ 在启动阶段获取初始仓位失败，程序退出: {e}")
        traceback.print_exc()
        exit()

    # --- 启动主循环 ---
    print("\n🎉 跟单机器人启动成功！进入高频监控模式...")
    print("   每秒检查一次，检测到目标交易或自身仓位清空时会采取行动。")
    print("   提示: 在OKX手动清空所有仓位可自动停止本程序。")
    
    while True:
        try:
            if check_self_positions_for_stop(accountAPI):
                print("\n\n🛑 停止信号：检测到您的OKX账户已无任何持仓。")
                print("   机器人将自动停止运行...")
                log_pnl_snapshot(accountAPI, pnl_logger, note="检测到仓位清空，机器人自动停止")
                break 

            # 【重要改动】直接调用，不再传入infoAPI
            current_target_positions = fetch_user_positions(TARGET_USER_ADDRESS) or []
            current_simplified_positions = simplify_positions_for_comparison(current_target_positions)

            if current_simplified_positions != last_known_simplified_positions:
                print("\n🔔 检测到目标仓位变化！正在执行跟单操作...")
                sync_positions(current_target_positions)
                print("\n🔍 正在记录跟单后的盈亏快照...")
                log_pnl_snapshot(accountAPI, pnl_logger, note="检测到目标交易后同步")
                last_known_simplified_positions = current_simplified_positions
                print("\n...返回高频监控模式...")
            else:
                # 仓位无变化，静默等待
                pass

            time.sleep(10)

        except KeyboardInterrupt:
            print("\n🛑 程序被手动中断 (Ctrl+C)，正在退出...")
            log_pnl_snapshot(accountAPI, pnl_logger, note="机器人手动中断")
            break
        except Exception as e:
            print(f"\n💥 主循环发生未知错误: {type(e).__name__} - {e}")
            log_pnl_snapshot(accountAPI, pnl_logger, note=f"主循环发生错误: {e}")
            if 'SSL' in str(e) or 'Connection' in str(e) or 'Max retries' in str(e):
                print("   检测到网络/SSL错误，可能是临时问题。将等待较长时间后重试...")
                time.sleep(60)
            else:
                traceback.print_exc()
                print("   发生未知类型错误，等待 30 秒后重试...")
                time.sleep(30)