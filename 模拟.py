
import okx.Trade as Trade
import okx.Funding as Funding
import json
import os
import okx.Account as Account
import okx.MarketData as MarketData
from utils import query_and_print_assets, display_positions_summary
# 定义配置文件名
CONFIG_FILE = 'config.json'

# 检查文件是否存在
if not os.path.exists(CONFIG_FILE):
    print(f"错误：找不到配置文件 {CONFIG_FILE}。请确保文件已创建并保存在正确的位置。")
else:
    try:
        # 使用 with 语句打开并读取 JSON 文件
        with open(CONFIG_FILE, 'r') as f:
            # 加载 JSON 数据
            config_data = json.load(f)

        # 从字典中提取变量
        api_key = config_data.get("api_key")
        secret_key = config_data.get("secret_key")
        passphrase = config_data.get("passphrase")

        # 打印验证（生产环境中请避免直接打印敏感密钥）
        print("✅ 成功读取配置信息：")
        print(f"API Key: {api_key[:8]}... (已部分隐藏)")
        print(f"Secret Key: {secret_key[:8]}... (已部分隐藏)")
        print(f"Passphrase: {passphrase[:4]}... (已部分隐藏)")
        
    except json.JSONDecodeError:
        print(f"错误：文件 {CONFIG_FILE} 不是有效的 JSON 格式。请检查文件内容。")
    except Exception as e:
        print(f"读取文件时发生未知错误: {e}")

flag = "1"  # live trading:0 , demo trading：1


# 调用一次并将返回值赋给 result 供后续使用/打印
query_and_print_assets(api_key, secret_key, passphrase, flag)
accountAPI = Account.AccountAPI(api_key, secret_key, passphrase, False, flag)
display_positions_summary(accountAPI.get_positions())
#mgnMode = "cross" (全仓/跨币种模式)： 在全仓模式下，该设置对 该合约的所有持仓 生效。多头和空头都使用同一个杠杆倍数，并共享同一保证金池。
result = accountAPI.set_leverage(
    instId = "BTC-USDT-SWAP",
    lever = "5",
    mgnMode = "cross"
)
tradeAPI = Trade.TradeAPI(api_key, secret_key, passphrase, False, flag)
result = accountAPI.set_position_mode(
    posMode="net_mode"
)

# market order

result = tradeAPI.place_order(
    instId="BTC-USDT-SWAP",
    tdMode="cross",
    side="sell",
    posSide="net",
    ordType="market",
    sz="0.1"
)
if result["code"] == "0":
    print("Successful order request，order_id = ",result["data"][0]["ordId"])
else:
    print("Unsuccessful order request，error_code = ",result["data"][0]["sCode"], ", Error_message = ", result["data"][0]["sMsg"])





