import okx.Trade as Trade
import okx.Funding as Funding
import json
import os
import okx.Account as Account
import okx.MarketData as MarketData
def display_positions_summary(api_response):
    """
    解析 accountAPI.get_positions() 的返回结果，并打印清晰的持仓总结。

    参数:
        api_response (dict): accountAPI.get_positions() 返回的字典数据。
    """
    
    # --- 1. 检查 API 状态 ---
    if api_response.get('code') != '0':
        print(f"❌ API 请求失败。错误码: {api_response.get('code', 'N/A')}")
        print(f"错误信息: {api_response.get('msg', '无')}")
        return

    positions = api_response.get('data', [])
    
    if not positions:
        print("✅ API 请求成功。当前账户无任何活跃持仓。")
        return

    # --- 2. 打印持仓总结 ---
    print("=" * 40)
    print("📈 账户当前活跃持仓总结")
    print("=" * 40)

    for pos in positions:
        # 确定持仓方向和盈亏状态
        pos_size = float(pos.get('pos', 0))
        avg_px = float(pos.get('avgPx', 0))
        mark_px = float(pos.get('markPx', 0))
        upl = float(pos.get('upl', 0))
        
        # 判断多空方向 (简化判断：假设 posSide='net'，且 pos > 0)
        # 实际方向更依赖于业务逻辑，这里根据价格关系辅助判断
        direction = "多头 (Long)" if mark_px > avg_px else "空头 (Short)"
        if pos_size < 0:
            direction = "空头 (Short)"

        # 格式化数字
        upl_formatted = f"{upl:+.8f}"
        upl_status = "🟢 盈利" if upl > 0 else ("🔴 亏损" if upl < 0 else "⚪️ 持平")
        
        # 打印详细信息
        print(f"**合约ID**: {pos.get('instId', 'N/A')} ({pos.get('instType', 'N/A')})")
        print(f"**模式**: {pos.get('mgnMode', 'N/A').upper()} 杠杆: {pos.get('lever', 'N/A')}x")
        print("-" * 20)
        print(f"➡️ **方向/大小**: {direction} / {pos_size} 张")
        print(f"➡️ **开仓均价**: {avg_px:,.4f}")
        print(f"➡️ **最新标记价**: {mark_px:,.4f}")
        print(f"➡️ **未实现盈亏 (UPL)**: {upl_formatted} {pos.get('ccy', 'N/A')} {upl_status}")
        
        # 风险指标
        liq_px = pos.get('liqPx')
        liq_info = liq_px if liq_px else "N/A (全仓模式或风险低)"
        
        print(f"➡️ **保证金率**: {float(pos.get('mgnRatio', 0)):,.2f}%")
        print(f"➡️ **强平价格**: {liq_info}")
        print("-" * 40)
def query_and_print_assets(api_key, secret_key, passphrase, flag, min_equity_threshold=1e-8):
    """
    查询账户资产并打印非零项。返回原始 JSON 响应以便外部使用（赋值给 result）。
    """
    accountAPI = Account.AccountAPI(api_key, secret_key, passphrase, False, flag)
    json_response = accountAPI.get_account_balance()

    try:
        details = json_response['data'][0]['details']
        total_eq = json_response['data'][0].get('totalEq', 'N/A')
        
        print(f"💰 账户总权益 (USD): {total_eq}\n")
        print("--- 筛选后的非零资产列表 ---")
        print("{:<8} {:<20} {:<20} {:<20}".format(
            "币种", "权益 (eq)", "可用余额", "美元估值 (eqUsd)"
        ))
        print("-" * 68)

        for item in details:
            try:
                equity_float = float(item.get('eq', 0))
            except (ValueError, TypeError):
                continue

            if equity_float > min_equity_threshold:
                print("{:<8} {:<20} {:<20} {:<20}".format(
                    item.get('ccy', ''),
                    item.get('eq', ''),
                    item.get('availBal', ''),
                    item.get('eqUsd', '')
                ))

        print("-" * 68)

    except (IndexError, KeyError, TypeError) as e:
        print(f"解析 JSON 结构失败，请检查键名或数据结构: {e}")

    return json_response