import os
import json
import time
import feedparser
import requests
import trafilatura
from google import genai

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
    """將收集好的文章批次送給 Gemini 進行結構化分析 (含自動重試機制)"""
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
    
    # 💡 新增：自動重試機制
    max_retries = 1
    for attempt in range(max_retries):
        try:
            print(f"🤖 交由 Gemini 處理批次 ({len(articles)} 篇)... (嘗試 {attempt + 1}/{max_retries})")
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config={'response_mime_type': 'application/json'}
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
            
            # 💡 成功處理完畢，基礎冷卻 10 秒後跳出重試迴圈
            time.sleep(15)
            return 
            
        except Exception as e:
            error_msg = str(e)
            
            # 👇 就是這行！這是拔掉遮罩的終極指令，讓 Google 告訴我們它到底在抱怨什麼
            print(f"🛑 [深度除錯] 來自 Google 的真實報錯：\n{error_msg}\n-------------------")
            
            # 判斷是否為 429 頻率限制
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                wait_time = (attempt + 1) * 15 # 第一次等15秒，第二次等30秒...
                print(f"⚠️ 觸發 API 頻率限制 (429)，系統自動冷卻 {wait_time} 秒後重試...")
                time.sleep(wait_time)
            else:
                print(f"❌ AI 處理發生嚴重錯誤 ({source_name}): {error_msg}")
                break # 如果不是 429，就直接放棄該批次
                
    
# ================= 4. 主程式流程 =================

def main():
    if not GEMINI_API_KEY:
        print("❌ 致命錯誤：找不到 GEMINI_API_KEY 環境變數！")
        return

    print("🔥 GIB 工業級情報引擎啟動中...")
    
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
            # 防重複檢查
            if is_new_link(entry.link):
                print(f"  🌟 發現新文章：{entry.title}")
                
                # 嘗試抓取全文，若失敗則退回使用 RSS 摘要
                full_content = get_full_text(entry.link)
                if not full_content:
                    full_content = entry.get('summary', entry.get('description', '無內文'))
                
                new_articles.append({
                    "title": entry.title,
                    "url": entry.link,
                    "content": full_content[:1500] # 截斷內文以節省 Token
                })
            else:
                # 👇 加上這行日誌，讓「安靜跳過」變成「看得到的跳過」
                print(f"  ⏭️ 跳過已讀文章：{entry.title}")
                
        # 批次處理：每 3 篇文章打包一次發給 Gemini，優化效能與配額
        batch_size = 3
        for i in range(0, len(new_articles), batch_size):
            batch = new_articles[i:i+batch_size]
            process_batch(source_name, batch)

    print("\n🏁 GIB 排程執行完畢。")

if __name__ == "__main__":
    main()
