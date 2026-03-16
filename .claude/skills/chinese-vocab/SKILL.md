---
name: chinese-vocab
description: 從 Zoom 聊天記錄或詞彙列表建立中文詞彙填空卡片 (Cloze cards)。Use when the user wants to create Anki flashcards from Chinese vocabulary lists or chat logs.
argument-hint: "[vocab-file] [--dry-run]"
disable-model-invocation: true
---

# 中文詞彙 Anki 卡片製作器

從 Zoom 聊天記錄或詞彙列表建立中文詞彙填空卡片 (Cloze cards)。

## 參數 (Arguments)

* `$ARGUMENTS` - 詞彙檔案路徑，可選擇加上 `--dry-run`

解析參數：
- 若包含 `--dry-run`：設定 DRY_RUN=true，在終端機預覽卡片
- 否則：DRY_RUN=false，將卡片加入 Anki

## 工作流程 (Workflow)

### 1. 提取詞彙（中文詞彙不可排除）

讀取詞彙檔案並提取中文詞彙。尋找：

* Zoom 聊天匯出常見格式：一行 header（例如 `2026-03-15 08:41:55 從 Ben Lo 對 所有人:`），下一行縮排 payload；**只從 payload 行提取詞語**
* 單行聊天格式：`從 Name 對 所有人: 詞語`
* 獨立的中文單詞/片語

**關鍵：提取所有中文詞彙，但只從實際詞彙內容提取。不要把純上下文行當成詞彙。**

* 專有名詞 (地名、人名、品牌) → **包含** (例如：大阪, 時代廣場, 環球影城)
* 片語/慣用語 → **包含** (例如：做中學, 先睡著)
* 複合詞條 (A/B 或 A、B) → 視為**分開**的單詞，每個都要做卡片
* 俚語/口語 → **包含**
* 相鄰訊息中的英文 gloss、圖片連結、URL、或補充說明 → 可作為**相鄰上下文**，用來幫助判斷詞義、選擇搜尋關鍵字、或 disambiguate 詞語；**但除非該行本身包含要學的中文詞語，否則不要把它列為主要詞彙**
* 僅排除 context-only 行：純網址、純英文 gloss、代號/縮寫、時間戳、說話者 header 等不是詞彙目標

在建立表格前，先對每個詞做**輕量正規化**並記錄搜尋別名：

* 保留**原始詞形**作為卡片答案
* 另外記錄 1-4 個**搜尋別名/常見寫法**，供後續搜尋使用
* 常見情況：繁簡差異、異體字、台灣常用寫法、去除語氣尾碼、改成更可搜尋的技術詞

例：

* `檯燈` → 搜尋別名可含 `台燈`
* `可調亮度的～` → 搜尋別名可含 `可調光`、`可調亮度`、`可調光的`
* `排水孔蓋` → 搜尋別名可含 `排水蓋`、`地漏蓋`
* `疏通蛇` → 搜尋別名可含 `管道疏通器`
* `內襯管` → 搜尋別名可含 `管道內襯`、`CIPP 內襯管`（若相鄰上下文支持）

建立一個編號表格。這是你的**約束性契約 (binding contract)** —— 每一行都**必須**產生至少一張卡片。

| # | 詞語 | 備註 |
| --- | --- | --- |
| 1 | ... |  |
| 2 | ... |  |

**主要詞彙計數 = N** (請明確指出此數字)

### 2. 規劃相關詞彙 & 建立目標列表

對於每個主要單詞，找出 1-3 個相關詞 (同義詞、反義詞、相關詞、搭配詞)。

**關鍵：在開始搜尋之前，先建立完整的目標列表。**

步驟 1 中的每個主要單詞**必須**出現在此表中。然後添加相關詞，直到總數 ≥ 2×N。

指派來源輪替以確保多樣性：

| # | 目標詞 | 類型 | 語域 | 來源 | 輪替 |
|---|--------|------|------|------|------|
| 1 | 主題 | main | 書面 | news | cna |
| 2 | 議題 | related | 書面 | news | udn |
| 3 | 分析 | main | 書面 | news | ltn |
| 4 | 解析 | related | 書面 | news | pts |
| 5 | 阿伯 | main | 口語 | forum | gamer |
| 6 | 大叔 | related | 口語 | forum | ptt-snippet |
| 7 | 實作 | main | 技術 | tech | techbang |
| 8 | 大阪 | main | 專有名詞 | news/wiki | cna |
| ... |  |  |  |  |  |

**語域 (Register) 分類：**

* **書面/正式** → cna, udn, ltn, pts (輪替)
* **口語/日常** → gamer, ptt-snippet, dcard-snippet (輪替)
* **技術/專業** → techbang, ithome-snippet (輪替)
* **專有名詞** → 新聞網站、維基百科、旅遊網站

**硬性要求：在繼續之前，目標列表計數 ≥ 2×N。**

請聲明："目標列表：M 個單詞 (M ≥ 2×N = 2×__ = __) ✓"

### 3. 搜尋例句 (直接用當前 harness 的搜尋/擷取工具)

使用當前執行環境可用的搜尋與擷取工具直接搜尋例句。**優先使用搜尋引擎做 discovery**，再抓命中的原文；網站內搜尋頁或直接已知來源 URL 是 fallback。**不要使用 Agent/Task 子代理**——直接呼叫工具更快、更可靠。

* Claude Code harness：使用 `WebSearch` + `WebFetch`
* OpenCode harness：優先使用 `webfetch` 擷取搜尋引擎結果頁；若沒有專用搜尋工具或被擋，再用網站內搜尋頁或直接已知來源 URL

在第一輪搜尋前，先做一個**preflight 預檢**：

* 測試當前 harness 是否真的能穩定使用搜尋引擎結果頁
* 測試 2-3 個目標來源網站是否可直接擷取內文
* 若搜尋引擎結果頁被 challenge / 403 / 空白頁，**立刻切換**到站內搜尋頁與直接來源導覽，不要硬耗回合
* 為每個詞建立一個**搜尋封包 (search packet)**：`原始詞`、`搜尋別名`、`相鄰上下文`、`相鄰英文 gloss`、`主題群組`、`優先來源家族`
* 預檢後先聲明可用路徑，例如：`search_engine_ok` / `site_search_ok` / `direct_fetch_ok`

#### 3a. 將目標詞按主題分組

將目標列表中的詞語按主題分組（例如：食物保存、排水管道、居家裝修、照明、商業經濟等）。一篇綜合性文章通常能涵蓋同主題的多個詞語。

#### 3b. 批次搜尋 (每批 10 個搜尋呼叫並行；優先搜尋引擎)

每批發送 10 個並行的搜尋呼叫。搜尋策略：

```
搜尋查詢格式（依 harness 調整）：
- 查詢："目標詞" 相關關鍵字
- allowed_domains: ["cna.com.tw", "udn.com", "ltn.com.tw"] （依輪替指定）

Claude Code：直接用 WebSearch
OpenCode：優先用 webfetch 擷取搜尋引擎結果頁；若沒有專用 WebSearch 或被擋，再用目標網站搜尋頁，再挑選文章 URL
```

**查詢階梯 (QUERY LADDER)：不要在第一個弱查詢失敗後就放棄**

對每個詞，至少依序嘗試：

1. 原始詞精確查詢：`"原始詞"`
2. 原始詞 + 相鄰上下文關鍵字
3. 搜尋別名 / 正規化寫法
4. 中文詞 + 相鄰英文 gloss / 產品英文名 / 工法英文名
5. 同義詞、上位概念、或更常見的台灣用語
6. `site:domain` 站點限制查詢
7. 目標網站站內搜尋頁

**不要在完成 query ladder 之前就把某詞標成 `✗ uncovered`。**

**可靠的台灣來源（優先使用）：**

| 來源 | 網域 | 類型 | 備註 |
|------|------|------|------|
| 中央社 | cna.com.tw | 新聞 | 穩定可擷取 |
| 自由時報 | ltn.com.tw, food.ltn.com.tw, estate.ltn.com.tw | 新聞 | 穩定可擷取 |
| 聯合報 | udn.com, health.udn.com, house.udn.com | 新聞 | 穩定可擷取 |
| 公視 | pts.org.tw, news.pts.org.tw | 新聞 | 穩定可擷取 |
| T客邦 | techbang.com | 科技 | 穩定可擷取 |
| 經濟日報 | money.udn.com | 財經 | 穩定可擷取 |

**可直接呼叫的站內搜尋 URL 範本（把 `{query}` 換成 URL-encoded 查詢詞）：**

* 中央社全文檢索：`https://www.cna.com.tw/search/hysearchws.aspx?q={query}`
* 自由時報全域查詢：`https://search.ltn.com.tw/list?keyword={query}`
* 自由時報健康：`https://search.ltn.com.tw/list?keyword={query}&type=health`
* 自由時報財經：`https://search.ltn.com.tw/list?keyword={query}&type=business`
* 自由時報地產：`https://search.ltn.com.tw/list?keyword={query}&type=estate`
* 聯合新聞網：`https://udn.com/search/word/2/{query}`
* T客邦：`https://www.techbang.com/search?q={query}`

**來源專用搜尋用法：**

* 要找 `health.udn.com` / `money.udn.com` / `house.udn.com` 內容時，先走 `udn.com/search/word/2/{query}`，再**優先挑選目標子網域**的結果
* 要找自由系子站內容時，先走 `search.ltn.com.tw/list?keyword={query}`，再依結果頁上的分類或子站網域挑選 `health.ltn.com.tw` / `ec.ltn.com.tw` / `estate.ltn.com.tw`
* 若某來源沒有已驗證的穩定站內搜尋範本，**不要猜 hidden endpoint**；改用該來源首頁/分類頁直接導覽，或用 `site:domain` 查詢作為 fallback

**較不穩定的來源（某些 harness / request patterns 可能被擋、導向告警頁、或需額外處理）：**
- dcard.tw — 常直接回傳 403
- forum.gamer.com.tw — 可能導向登入或兒少保護頁面
- ptt.cc — 常可擷取，但某些板面、頁面或請求方式可能需要 cookie 或特殊處理
- udn 部落格 (blog.udn.com) — 某些請求方式可抓到，某些會被擋；可作為備用來源但不要當主力

**來源家族優先順序（依主題選來源，不要所有詞都先塞到泛新聞）：**

* **食物 / 健康 / 睡眠** → 生活新聞、健康新聞、醫療衛教、百科/字典（僅輔助）
* **排水 / 管道 / 裝修 / 工程** → 居家裝修、工程說明、產品/工法介紹、政府工程頁面、百科/字典（僅輔助）
* **照明 / 家電 / 消費產品** → 品牌產品頁、照明教學、家居媒體、百科/字典（僅輔助）
* **財經 / 商業 / 市場術語** → 財經新聞、分析評論、產業解說、百科/字典（僅輔助）
* **抽象書面詞 / 成語 / 慣用語** → 新聞評論、專欄、百科、字典

**百科/字典的用途：**

* 注音、釋義、術語 disambiguation → 很適合
* 例句素材 → 可用，但**優先度低於真實文章/報導/說明頁**
* 若已有可用文章來源，**不要讓百科/字典成為主要例句來源**，避免單一來源壟斷

#### 3c. 批次擷取 (每批 10 個擷取呼叫並行)

從搜尋結果中挑選最有可能的文章 URL，每批發送 10 個並行的擷取呼叫。

**關鍵：使用多詞提取提示**——一次擷取可涵蓋多個目標詞：

```
擷取格式（依 harness 調整）：
url: https://article-url

Claude Code WebFetch prompt:
從這篇文章中，找出包含以下任何詞語的段落：詞A、詞B、詞C。
對於每個找到的詞語，提取該段落中 2-3 個包含或圍繞該詞的連續句子。
請標明每組句子對應的詞語。保留繁體中文原文。

OpenCode webfetch:
直接抓文章內容，然後在回傳內容中手動找出包含詞A、詞B、詞C的段落。
對於每個找到的詞語，提取同段落中 2-3 個連續句子。保留繁體中文原文。
```

這樣一篇文章就能為同主題的 3-5 個詞語提供例句。

#### 3d. 迭代補齊

搜尋和擷取的節奏：
1. **第一輪**：按主題分組搜尋 → 擷取 → 清點已覆蓋的詞語
2. **第二輪**：針對未覆蓋的詞語重新搜尋（換網站/換查詢詞）→ 擷取
3. **第三輪**（如需要）：放寬搜尋條件（移除 `allowed_domains` 限制）

**LOW-HIT PROTOCOL（低命中詞強制流程）**

若某詞在前兩輪仍無穩定命中，必須依序做：

1. 檢查是否需要正規化、異體字、台灣常用寫法、或更常見別名
2. 重新利用相鄰上下文：英文 gloss、圖片 URL、主題群組、相鄰詞對
3. 改搜更可搜尋的上位概念、產品類型、工法名稱、或職稱
4. 改用更符合主題的來源家族，而不是持續硬搜泛新聞
5. 只有在以上都做過後，才用百科/字典補強注音/釋義與暫時性例句來源

每輪結束後，更新追蹤表格：

| # | 目標詞 | 狀態 | 來源 | 網域 |
|---|--------|------|------|------|
| 1 | 冷藏 | ✓ | 中央社 | cna.com.tw |
| 2 | 冷凍 | ✓ | 元氣網 | health.udn.com |
| 3 | 疏通蛇 | ✗ 待重試 | | |

**同段落上下文要求 (SAME-PARAGRAPH CONTEXT)：**

從 WebFetch 結果中提取例句時，所有 2-3 句必須來自同一篇文章的同一段落或連續段落。

❌ 錯誤：從不同文章各取一句拼湊
✓ 正確：從同一篇文章的同一段落提取 2-3 個連續句子

### 4. 組裝卡片 & 驗證完整性

從 WebFetch 結果中組裝所有卡片。每張卡片格式：

- **front（文字）**：2-3 個句子，目標詞替換為 `{{c1::目標詞}}`
- **back（註記）**：`來源：網站名 domain\n注音：ㄅㄆㄇ\n釋義：中文定義`

**最終驗證：**

| 檢查項目 | 要求 |
|----------|------|
| 收集的卡片數 | ≥ 2×N |
| 每個主要詞彙至少 1 張卡片 | 35/35 |
| 每張卡片 2-3 句 | ✓ |
| 同段落語境連貫 | ✓ |
| 無單一網域 >40% | ✓ |

**若有目標詞仍未覆蓋：** 回到步驟 3d 重試。

---

## 若 DRY_RUN=true：預覽卡片

在終端機顯示每張卡片：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Card 1/36: 主題 (main) [書面 → 中央社]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

文字:
Google表示，Android 10特色主要圍繞在創新、安全與隱私、數位健康等3大{{c1::主題}}。
其中安全與隱私{{c1::主題}}涵蓋了多項重要更新，包括限制應用程式存取裝置位置的權限。
數位健康{{c1::主題}}則新增了專注模式，幫助用戶減少手機使用時間。

註記:
來源：中央社
注音：ㄓㄨˇ ㄊㄧˊ
釋義：文章或談話的中心內容

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Card 2/36: 議題 (related) [書面 → 聯合報]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
...
```

顯示所有卡片後，顯示摘要：

```
═══════════════════════════════════════════════════════
DRY RUN 摘要
═══════════════════════════════════════════════════════
總卡片數：36
主要詞彙：18
比例：2.0× ✓

來源分布：
  cna.com.tw:     8 張卡片 (22%) ✓
  udn.com:        6 張卡片 (17%) ✓
  ltn.com.tw:     5 張卡片 (14%) ✓
  pts.org.tw:     4 張卡片 (11%) ✓
  gamer.com.tw:   5 張卡片 (14%) ✓
  techbang.com:   3 張卡片 (8%) ✓
  snippets:       5 張卡片 (14%) ✓

所有品質閘門通過 ✓
執行時不加 --dry-run 即可將卡片加入 Anki。
═══════════════════════════════════════════════════════
```

**若為 dry run，在此停止。不要加入 Anki。**

---

## 若 DRY_RUN=false：加入 Anki

需求：Anki 正在執行，並安裝了 AnkiConnect 附加元件 (代碼：2055492159)

```python
#!/usr/bin/env python3
"""Uses only stdlib (no pip dependencies required)."""
import json
import urllib.request

CARDS = [
    # 從搜尋結果填充
    # ("front_with_cloze", "back_notes"),
]

def anki_request(action, **params):
    payload = json.dumps({"action": action, "version": 6, "params": params})
    req = urllib.request.Request("http://localhost:8765", data=payload.encode())
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    if result.get("error"):
        raise Exception(f"{action}: {result['error']}")
    return result["result"]

added = errors = 0
for i, (front, back) in enumerate(CARDS, 1):
    try:
        nid = anki_request("addNote", note={
            "deckName": "hanzi", "modelName": "克漏題",
            "fields": {"文字": front, "註記": back},
            "options": {"allowDuplicate": False},
            "tags": ["claude-vocab"]
        })
        print(f"[{i}/{len(CARDS)}] Added (id={nid})")
        added += 1
    except Exception as e:
        print(f"[{i}/{len(CARDS)}] ERROR: {e}")
        errors += 1

print(f"\n✓ Added {added} cards to hanzi deck ({errors} errors)")
```

---

## 品質閘門 (強制性 MANDATORY)

**完整性 (不可協商)：**

* 輸入文件中的每個中文詞彙至少得到 1 張卡片（不可排除；但純上下文行不算詞彙）
* 專有名詞、地名、片語 → 全部都要做卡片
* 總卡片數 ≥ 2× 主要詞彙計數

**卡片品質：**

* 全中文：卡片上沒有英文
* 每張卡片 2-3 個句子 (不是 1 句)
* **同段落要求**：所有句子必須來自同一個段落或連續段落，保持語境連貫
* 具備出處的真實來源

**來源多樣性：**

* 無單一網域 >40% 的卡片
* 每個語域類別使用 ≥2 個不同來源
* 口語詞彙來自論壇/摘要，而非新聞網站

## 應避免的失敗模式
- ❌ 「排除專有名詞」- 不允許
- ❌ 「跳過片語」- 不允許
- ❌ 「從 18 個詞彙只建立了 21 張卡片」- 未達 2× 要求
- ❌ 搜尋了某個詞但沒有為它建立卡片
- ❌ 在所有目標都有例句之前就進入卡片建立階段
- ❌ 使用 Agent/Task 子代理搜尋例句（直接用當前 harness 的搜尋/擷取工具更快更可靠）
- ❌ 逐詞逐篇搜尋——應按主題分組，一篇文章擷取多個詞語
- ❌ 把純上下文行（URL、英文 gloss、代號、header）當成主要詞彙
- ❌ 對較不穩定來源不加判斷地硬抓到底（dcard 常 403；gamer 可能跳保護頁；ptt / blog.udn 在不同 harness 可能表現不一）
- ❌ 只試一種拼法或一個查詢就放棄——必須走完 query ladder
- ❌ 忽略相鄰上下文，導致技術詞或產品詞搜錯方向
- ❌ 讓百科/字典在有其他可用來源時壟斷大部分例句
- ❌ **從不同文章拼湊句子** - 卡片的 2-3 句必須來自同一段落，不可從多篇文章各取一句
