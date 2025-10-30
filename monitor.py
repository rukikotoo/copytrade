# /d:/hyperliquid-bot/hyperliquid-bot/monitor.py
import time
from typing import List, Dict, Optional
from hyperliquid.info import Info
from hyperliquid.utils import constants

def get_nonzero_positions(user_state: Dict) -> List[Dict]:
    """从 user_state 返回所有非零仓位（每项是 position 字段）。"""
    results = []
    for ap in user_state.get("assetPositions", []):
        pos = ap.get("position", {})
        try:
            szi = float(pos.get("szi", 0))
        except (TypeError, ValueError):
            szi = 0.0
        if szi != 0:
            results.append(pos)
    return results

def fetch_user_positions(address: str, info: Optional[Info] = None) -> List[Dict]:
    """
    获取指定地址的持仓列表并返回处理后的信息列表。
    如果未传入 info，会内部创建一个 Info 实例（并在返回前关闭它的 ws）。
    返回项示例：
      {
        "coin": "BTC",
        "direction_is_buy": True,
        "leverage": 5,
        "size": 0.123,
        "mid": 60000.0,
        "value_usd": 7380.0,
        "raw_position": {...}
      }
    """
    created_info = False
    if info is None:
        info = Info(base_url=constants.MAINNET_API_URL)
        created_info = True

    try:
        all_mids = info.all_mids() or {}
        user_state = info.user_state(address) or {}
        positions = get_nonzero_positions(user_state)
        result = []

        for pos in positions:
            coin = pos.get("coin", "?")
            try:
                mid = float(all_mids.get(coin, 0) or 0)
            except (TypeError, ValueError):
                mid = 0.0

            try:
                szi = float(pos.get("szi", 0))
            except (TypeError, ValueError):
                szi = 0.0

            direction_is_buy = szi > 0
            try:
                lev_val = pos.get("leverage", {}).get("value")
                leverage = int(lev_val) if lev_val is not None else 0
            except (TypeError, ValueError):
                leverage = 0

            size = abs(szi)
            value_usd = size * mid

            result.append({
                "coin": coin,
                "direction_is_buy": direction_is_buy,
                "leverage": leverage,
                "size": size,
                "mid": mid,
                "value_usd": value_usd,
                "raw_position": pos,
            })
        return result
    finally:
        if created_info:
            try:
                info.ws_manager.close()
            except Exception:
                pass

# 可选：保留一个命令行运行时的简单监控示例
def main_loop(target_address: str, loop_sleep_seconds: int = 30):
    info = Info(base_url=constants.MAINNET_API_URL)
    try:
        print(f"监控地址: {target_address}")
        while True:
            print(f"\n----- {time.strftime('%Y-%m-%d %H:%M:%S')} -----")
            positions = fetch_user_positions(target_address, info=info)
            if not positions:
                print("目标当前无非零持仓。")
            else:
                for p in positions:
                    print(f"{p['coin']} | {'多' if p['direction_is_buy'] else '空'} | "
                          f"杠杆: {p['leverage']}x | 数量: {p['size']} | "
                          f"名义价值: ${p['value_usd']:.2f} | 价格: ${p['mid']:.2f}")
            time.sleep(loop_sleep_seconds)
    except KeyboardInterrupt:
        print("手动中断，退出。")
    finally:
        try:
            info.ws_manager.close()
        except Exception:
            pass

if __name__ == "__main__":
    TARGET_USER_ADDRESS = "0xc20ac4dc4188660cbf555448af52694ca62b0734"
    main_loop(TARGET_USER_ADDRESS, loop_sleep_seconds=30)