import requests
import json

# 請貼上你剛才複製的 GAS URL
GAS_URL = "https://script.google.com/macros/s/AKfycbwDMd6KtEO_96DqLlcICc5PL2g0k6DVOEqiX_M-ZM0bRDefJsQSwaTbhgNTyXCDURuRIA/exec"

def test_link():
    payload = {
        "message": "哈囉！這是來自 Python 的第一條測試訊息。"
    }
    
    print("🚀 正在嘗試發送資料到 Google Sheets...")
    
    try:
        # GAS 的 Web App 在處理 POST 時會發生 302 重導向，requests 會自動處理
        response = requests.post(GAS_URL, json=payload)
        
        if response.status_code == 200:
            print(f"成功回傳內容：{response.text}")
        else:
            print(f"❌ 失敗！狀態碼：{response.status_code}")
            
    except Exception as e:
        print(f"❌ 發生異常：{str(e)}")

if __name__ == "__main__":
    test_link()
