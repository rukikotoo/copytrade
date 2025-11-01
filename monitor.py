# monitor.py (您提供的可用版本)

import time
from typing import List, Dict, Optional
from hyperliquid.info import Info
from hyperliquid.utils import constants
from decimal import Decimal # 引入Decimal以提高精度

def get_nonzero_positions(user_state: Dict) -> List[Dict]:
    """从 user_state 返回所有非零仓位（每项是 position 字段）。"""
    results = []
    for ap in user_state.get("assetPositions", []):
        pos = ap.get("position", {})
        try:
            # 使用Decimal进行比较，避免浮点数精度问题
            szi = Decimal(pos.get("szi", '0'))
        except Exception:
            szi = Decimal('0')
        if not szi.is_zero():
            results.append(pos)
    return results

def fetch_user_positions(address: str, info: Optional[Info] = None) -> List[Dict]:
    """
    获取指定地址的持仓列表并返回处理后的信息列表。
    返回的数据已经转换为Decimal以保证精度。
    """
    created_info = False
    if info is None:
        # 增加 skip_ws=True 以避免不必要的websocket连接
        info = Info(base_url=constants.MAINNET_API_URL, skip_ws=True)
        created_info = True

    try:
        all_mids = info.all_mids() or {}
        user_state = info.user_state(address) or {}
        positions = get_nonzero_positions(user_state)
        result = []

        for pos in positions:
            coin = pos.get("coin", "?")
            
            # 统一使用Decimal处理所有数值
            mid = Decimal(all_mids.get(coin, '0'))
            szi = Decimal(pos.get("szi", '0'))
            
            direction_is_buy = szi > 0
            
            try:
                lev_val = pos.get("leverage", {}).get("value")
                leverage = Decimal(lev_val) if lev_val is not None else Decimal('0')
            except Exception:
                leverage = Decimal('0')

            size = szi.copy_abs()
            value_usd = size * mid

            result.append({
                "coin": coin,
                "direction_is_buy": direction_is_buy,
                "leverage": leverage,
                "size": size, # size 是 Decimal
                "value_usd": value_usd, # value_usd 是 Decimal
                # 以下字段是为了调试和兼容，trade.py中不直接使用
                "mid": mid,
                "raw_position": pos,
            })
        return result
    finally:
        # 如果是内部创建的info实例，尝试关闭它
        if created_info and hasattr(info, 'ws_manager'):
            try:
                info.ws_manager.close()
            except Exception:
                pass

# 主循环部分保持不变，用于独立测试 monitor.py
if __name__ == "__main__":
    TARGET_USER_ADDRESS = "0xc20ac4dc4188660cbf555448af52694ca62b0734"
    info = Info(base_url=constants.MAINNET_API_URL, skip_ws=True)
    while True:
        print(f"\n----- {time.strftime('%Y-%m-%d %H:%M:%S')} -----")
        positions = fetch_user_positions(TARGET_USER_ADDRESS, info=info)
        if not positions:
            print("目标当前无非零持仓。")
        else:
            for p in positions:
                print(f"{p['coin']} | {'多' if p['direction_is_buy'] else '空'} | "
                      f"杠杆: {p['leverage']}x | 数量: {p['size']} | "
                      f"名义价值: ${p['value_usd']:.2f}")
        time.sleep(30)