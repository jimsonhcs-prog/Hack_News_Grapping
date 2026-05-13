# 🔥 GIB (Gemini Intelligence Batch) 
### 工業級科技情報自動化引擎

**GIB** 是一個高效能的情報處理引擎，專為科技追蹤者與決策者設計[cite: 6]。它能自動監控 RSS 情報源、深度抓取網頁內文、利用 Gemini AI 進行結構化摘要[cite: 6]。

> **當前版本**: v3.0 (Grounding & Batching Optimized)[cite: 6]
> **運作日期**: 2026-05-13[cite: 6]
> **核心目標**: 將「被動接收資訊」升級為「自動產出洞察」[cite: 6]。

---

## 🚀 系統核心技術模組

### 1. 🔍 深度閱讀機制 (Deep Extraction)
整合了 `trafilatura` 庫，自動剔除網頁廣告並優化內文截斷以節省 Token[cite: 6]。

### 2. 🛡️ 工業級防護與抗壓 (Reliability)
系統具備防重複資料庫 (`processed_urls.json`) 與 429 智能退避機制，能應對 API 頻率限制[cite: 6]。

### 3. 🧠 AI 批次處理與結構化輸出 (AI Synergy)
預設每 3 篇文章打包一次，產出繁體中文摘要、技術啟發與關鍵術語解釋[cite: 6]。

---

## 🛠 配置與部署
請確保環境中配置以下金鑰：`GEMINI_API_KEY`、`TG_TOKEN`、`GAS_URL`[cite: 6]。
情報源可在 `main.py` 的 `SOURCES` 字典中自由增減[cite: 6]。

---
*Created by J-hub(問股) Nexus Group | 2026-05-13*[cite: 6]
