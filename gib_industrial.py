import os
import sys
import json
import time
import feedparser
import requests
import trafilatura
from google import genai
from google.genai import types

# ================= 1. 系統配置區 =================
# 從環境變數讀取機密資訊 (保護你的金鑰不外流)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TG_TOKEN = os.getenv("TG_TOKEN")
GAS_URL = os.getenv("GAS_URL")

# 你的 Telegram Chat ID (前面已確認)
TG_CHAT_ID = "6460606782"

# 情報源清單：可自由擴充任何支援 RSS 的網址
SOURCES = {
    "Hacker News": "https://news.ycombinator.com/rss",
    "TechCrunch": "https://techcrunch.com/feed/",
    # "Reddit ML": "https://www.reddit.com/r/MachineLearning/.rss" # 備用範例
}

# 歷史紀錄資料庫檔名
DB_FILE = "processed_urls.json"

# 備援模型清單，依優先順序嘗試
MODELS_BACKUP = [
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-2.5-flash-lite"
]

# ================= 2. 核心功能模組 =================

def is_new_link(url):
    """防重複機制：檢查連結是否已處理過，並更新本地 JSON 資料庫"""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            try:
                processed_list = json.load(f)
            except json.JSONDecodeError:
                processed_list = []
    else:
        processed_list = []
    
    # 若已存在，跳過處理
    if url in processed_list:
        return False
    
    # 若是新文章，加入清單並限制最大長度為 300 筆 (避免檔案過大)
    processed_list.append(url)
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(processed_list[-300:], f, ensure_ascii=False, indent=2)
    return True

def get_full_text(url):
    """深度閱讀機制：繞過廣告與版型，直接抓取網頁純內文"""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            result = trafilatura.extract(downloaded)
            # 限制長度，避免單篇文章消耗過多 Token
            return result[:1200] if result else "" 
    except Exception as e:
        print(f"⚠️ 內文抓取失敗 ({url}): {e}")
    return ""

def send_to_telegram(text):
    """推播機制：將美化後的 Markdown 訊息傳送到手機"""
    if not TG_TOKEN:
        print("⚠️ 缺少 TG_TOKEN，跳過推播。")
        return

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Telegram 發送失敗: {e}")

def send_to_gas(message):
    """歸檔機制：將精簡版文字傳送至 Google Sheets"""
    if not GAS_URL:
        return
    try:
        requests.post(GAS_URL, json={"message": message}, timeout=10)
    except Exception as e:
        print(f"❌ GAS 寫入失敗: {e}")

# ================= 3. AI 批次處理模組 =================

def process_batch(source_name, articles):
    """將收集好的文章批次送給 Gemini 進行結構化分析（含模型備援與自動重試機制）"""
    if not articles:
        return
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    你是一位資深科技趨勢分析師。請分析以下來自【{source_name}】的 {len(articles)} 篇文章。
    請直接輸出一個 JSON 陣列，不要包含任何 Markdown 標記（如 ```json）。
    
    每個 JSON 物件必須包含以下欄位：
    - "title": 文章繁體中文標題 (若原文是英文請翻譯)
    - "url": 保持原網址
    - "summary": 用一句話精準總結核心重點
    - "insight": 給開發者或商業人士的兩點深度啟發
    - "term": 挑選一個關鍵術語 (保留原文) 並簡短解釋
    
    待處理內容如下：
    {json.dumps(articles, ensure_ascii=False)}
    """
    
    # 遍歷所有備援模型，依序進行處理
    for model_name in MODELS_BACKUP:
        # 針對每個模型的重試機制，例如處理 429 頻率限制的重試
        max_retries = 1
        for attempt in range(max_retries):
            try:
                print(f"🤖 嘗試使用模型【{model_name}】處理批次 ({len(articles)} 篇)... (嘗試 {attempt + 1}/{max_retries})")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                
                insights = json.loads(response.text)
                
                for item in insights:
                    tg_msg = (
                        f"📡 *[{source_name}]* \n\n"
                        f"🚀 *{item.get('title', '無標題')}*\n\n"
                        f"📝 *重點摘要*：\n{item.get('summary', '')}\n\n"
                        f"💡 *技術洞察*：\n{item.get('insight', '')}\n\n"
                        f"🔖 *關鍵術語*：\n`{item.get('term', '')}`\n\n"
                        f"🔗 [點此閱讀原文]({item.get('url', '')})"
                    )
                    send_to_telegram(tg_msg)
                    
                    sheet_msg = f"[{source_name}] {item.get('title', '')}\n啟發：{item.get('insight', '')}\n術語：{item.get('term', '')}"
                    send_to_gas(sheet_msg)
                    
                    time.sleep(1) # TG 發送間隔
                
                # 成功處理完畢，基礎冷卻 15 秒後跳出重試與備援迴圈
                time.sleep(15)
                return 
                
            except Exception as e:
                error_msg = str(e)
                print(f"🛑 [深度除錯] 嘗試模型【{model_name}】失敗，真實報錯：\n{error_msg}\n-------------------")
                
                # 判斷是否為 429 頻率限制，若是則在該模型下進行冷卻重試
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    wait_time = (attempt + 1) * 15
                    print(f"⚠️ 觸發 API 頻率限制 (429)，系統自動冷卻 {wait_time} 秒後重試該模型...")
                    time.sleep(wait_time)
                else:
                    # 如果不是 429，可能是模型不存在（404）或不支援，跳出重試迴圈並切換到下一個備援模型
                    print(f"❌ 模型【{model_name}】發生嚴重錯誤，準備切換至下一個備援模型。")
                    break
                    
    raise RuntimeError(f"已嘗試所有備援模型，皆無法成功處理批次 ({source_name})。")
                
    
# ================= 4. 主程式流程 =================

def main():
    # 解決 Windows 環境下 stdout/stderr 預設編碼 (例如 CP950) 無法編碼 Emoji 的問題
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    if not GEMINI_API_KEY:
        print("❌ 致命錯誤：找不到 GEMINI_API_KEY 環境變數！")
        sys.exit(1)

    print("🔥 GIB 工業級情報引擎啟動中...")
    
    try:
        for source_name, source_url in SOURCES.items():
            print(f"\n🔍 開始掃描情報源：{source_name}")
            
            try:
                feed = feedparser.parse(source_url)
            except Exception as e:
                print(f"⚠️ RSS 解析失敗 ({source_name}): {e}")
                continue
                
            new_articles = []
            
            # 每次掃描檢查最新的 5 則
            for entry in feed.entries[:5]:
                link = entry.get('link', '')
                title = entry.get('title', '無標題')
                
                if not link:
                    continue
                
                # 防重複檢查
                if is_new_link(link):
                    print(f"  🌟 發現新文章：{title}")
                    
                    # 嘗試抓取全文，若失敗則退回使用 RSS 摘要
                    full_content = get_full_text(link)
                    if not full_content:
                        full_content = entry.get('summary', entry.get('description', '無內文'))
                    
                    new_articles.append({
                        "title": title,
                        "url": link,
                        "content": full_content[:1500] # 截斷內文以節省 Token
                    })
                else:
                    print(f"  ⏭️ 跳過已讀文章：{title}")
                    
            # 批次處理：每 3 篇文章打包一次發給 Gemini，優化效能與配額
            batch_size = 3
            for i in range(0, len(new_articles), batch_size):
                batch = new_articles[i:i+batch_size]
                process_batch(source_name, batch)
                
    except Exception as e:
        print(f"❌ 系統執行過程中發生未預期的致命錯誤：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n🏁 GIB 排程執行完畢。")

if __name__ == "__main__":
    main()
