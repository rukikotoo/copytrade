
# check_instrument_details.py
import okx.PublicData as PublicData

# --- 配置 ---
# 在这里输入你想查询的合约ID
INSTRUMENT_IDS_TO_CHECK = [
    "BTC-USDT-SWAP", 
    "BNB-USDT-SWAP"
] 
FLAG = "1"  # "1" 代表模拟盘, "0" 代表实盘
# --- 配置结束 ---

def get_instrument_details(instId, flag):
    """从OKX获取并打印合约的详细参数。"""
    try:
        publicAPI = PublicData.PublicAPI(flag=flag)
        result = publicAPI.get_instruments(instType="SWAP", instId=instId)

        if result.get('code') == '0' and result.get('data'):
            info = result['data'][0]
            print(f"✅ 成功获取【{instId}】的参数:")
            print("-" * 40)
            # lotSz 是交易数量的步进值，也就是我们需要的下单精度
            lot_size = info.get('lotSz')
            print(f"  - 最小下单数量 (lotSz): {lot_size}")
            print(f"  - 价格精度 (tickSz): {info.get('tickSz')}")
            print(f"  - 最小下单张数 (minSz): {info.get('minSz')}")
            print("-" * 40)
            
            if lot_size:
                print(f"🎯 结论: 在 trade.py 的 CONTRACT_PRECISION 字典中,")
                print(f"   为 \"{instId}\" 设置的值应该是: Decimal('{lot_size}')")
            else:
                print("⚠️ 未找到 lotSz，无法给出结论。")
        else:
            print(f"❌ 获取【{instId}】参数失败。 API响应: {result}")

    except Exception as e:
        print(f"查询 {instId} 时发生异常: {e}")

if __name__ == "__main__":
    env = "模拟盘" if FLAG == '1' else "实盘"
    print(f"环境: {env}\n")
    
    for inst_id in INSTRUMENT_IDS_TO_CHECK:
        get_instrument_details(inst_id, FLAG)
        print("\n" + "="*50 + "\n")