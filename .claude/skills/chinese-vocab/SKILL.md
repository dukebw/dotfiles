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

### 1. 提取詞彙（不可排除）

讀取詞彙檔案並提取中文詞彙。尋找：

* 聊天格式：`從 Name 對 所有人: 詞語`
* 獨立的中文單詞/片語

**關鍵：提取所有詞彙。不允許排除任何內容 (NO EXCLUSIONS ALLOWED)。**

* 專有名詞 (地名、人名、品牌) → **包含** (例如：大阪, 時代廣場, 環球影城)
* 片語/慣用語 → **包含** (例如：做中學, 先睡著)
* 複合詞條 (A/B 或 A、B) → 視為**分開**的單詞，每個都要做卡片
* 俚語/口語 → **包含**

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

### 3. 搜尋例句 (直接 WebSearch + WebFetch)

使用 WebSearch 和 WebFetch 工具直接搜尋例句。**不要使用 Agent/Task 子代理**——直接呼叫工具更快、更可靠。

#### 3a. 將目標詞按主題分組

將目標列表中的詞語按主題分組（例如：食物保存、排水管道、居家裝修、照明、商業經濟等）。一篇綜合性文章通常能涵蓋同主題的多個詞語。

#### 3b. 批次搜尋 (每批 10 個 WebSearch 並行)

每批發送 10 個並行的 WebSearch 呼叫。搜尋策略：

```
WebSearch 查詢格式：
- 查詢："目標詞" 相關關鍵字
- allowed_domains: ["cna.com.tw", "udn.com", "ltn.com.tw"] （依輪替指定）
```

**可靠的台灣來源（優先使用）：**

| 來源 | 網域 | 類型 | 備註 |
|------|------|------|------|
| 中央社 | cna.com.tw | 新聞 | 穩定可擷取 |
| 自由時報 | ltn.com.tw, food.ltn.com.tw, estate.ltn.com.tw | 新聞 | 穩定可擷取 |
| 聯合報 | udn.com, health.udn.com, house.udn.com | 新聞 | 穩定可擷取 |
| 公視 | pts.org.tw, news.pts.org.tw | 新聞 | 穩定可擷取 |
| T客邦 | techbang.com | 科技 | 穩定可擷取 |
| 經濟日報 | money.udn.com | 財經 | 穩定可擷取 |

**不可靠的來源（避免直接擷取）：**
- ptt.cc — 常回傳 403/socket error
- dcard.tw — 常回傳 403
- udn 部落格 (blog.udn.com) — 常回傳 403
- forum.gamer.com.tw — 偶爾可擷取但不穩定

#### 3c. 批次擷取 (每批 10 個 WebFetch 並行)

從搜尋結果中挑選最有可能的文章 URL，每批發送 10 個並行的 WebFetch 呼叫。

**關鍵：使用多詞提取提示**——一次擷取可涵蓋多個目標詞：

```
WebFetch 提示格式：
url: https://article-url
prompt: 從這篇文章中，找出包含以下任何詞語的段落：詞A、詞B、詞C。
對於每個找到的詞語，提取該段落中 2-3 個包含或圍繞該詞的連續句子。
請標明每組句子對應的詞語。保留繁體中文原文。
```

這樣一篇文章就能為同主題的 3-5 個詞語提供例句。

#### 3d. 迭代補齊

搜尋和擷取的節奏：
1. **第一輪**：按主題分組搜尋 → 擷取 → 清點已覆蓋的詞語
2. **第二輪**：針對未覆蓋的詞語重新搜尋（換網站/換查詢詞）→ 擷取
3. **第三輪**（如需要）：放寬搜尋條件（移除 `allowed_domains` 限制）

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

* 輸入文件中的每個單詞至少得到 1 張卡片 (不可排除)
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
- ❌ 使用 Agent/Task 子代理搜尋例句（直接用 WebSearch + WebFetch 更快更可靠）
- ❌ 逐詞逐篇搜尋——應按主題分組，一篇文章擷取多個詞語
- ❌ 嘗試擷取 ptt.cc / dcard.tw / blog.udn.com（這些網站常封鎖自動擷取）
- ❌ **從不同文章拼湊句子** - 卡片的 2-3 句必須來自同一段落，不可從多篇文章各取一句
