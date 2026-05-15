# failures.md — Ratchet 規則庫

這個檔案記錄每次踩過的坑，以及由此產生的永久規則。
教練每次新對話會檢查這份清單，遇到對應失敗訊號會自動擋下。

格式：每條規則包含
- **失敗訊號**：這次發生什麼，用使用者自己的話
- **Harness 層**：屬於哪一層（規則 / 工具 / 執行 / 約束 / 協調 / 觀測）
- **永久規則**：未來教練要做什麼
- **日期**：第一次寫下的日期

---

## R001 — 新專案 kickoff 前必須有可驗證的目標檔案

**失敗訊號**（2026-05-13）
> Balian 要求「規劃一套專案開發分析平台」，但目標（Plan）完全沒寫下來，只在腦袋裡。
> 對應 PDCA 的 P 缺席，整套平台失去檢核基準。

**Harness 層**：規則層（AGENTS.md / CLAUDE.md 沒有強制 kickoff 前要有目標檔案）

**永久規則**
- 當 Balian 提出「規劃 / 建立 / 做一套 XX 系統」這類請求時，教練必須先檢查：
  1. 是否有對應的 `目標.md` / `spec.md` / `done-condition.md` 等文件
  2. 如果沒有，**拒絕進入實作**，先進 Phase 0 目標出土
- 目標檔案必須包含「可驗證的完成條件」，不接受抽象詞（賺錢、變強、上線、完整版）
- 「完整版」「全功能」「做好」這類詞屬於空話，要拆成具體可數的子條件才算數

**第一次寫下**：2026-05-13

---

## R002 — Binary 字串證據不等於行為證據，不准用片段字串推論功能

**失敗訊號**（2026-05-14）
> Balian 問「Claude Code 貼上長內容會折疊成 `[Pasted text #1 +5 lines]`，可以解嗎？」
> 我從 binary 撈到 `Please double press esc to edit your message` 這串字，**沒驗證實際行為**，就斷言「連按兩下 ESC 會把訊息丟到外部編輯器」。
> 為此叫使用者改 `~/.zshrc` 的 `EDITOR`、開 macOS Automation 權限、重啟 Claude Code，結果 ESC 兩次的真實行為是「清空輸入欄 / 倒回上一則對話」，完全沒解原本的問題。

**Harness 層**：觀測層 + 約束層
- 觀測層失敗：靠 `strings` 看到一段 hint 就當作功能規格，沒有交叉比對 keybinding table、setting schema、實際操作驗證
- 約束層失敗：沒有「未經驗證就不准對使用者下指令動 zshrc / 改系統設定」的擋線

**永久規則**

當教練要建議使用者「按某個快捷鍵 / 改某個設定 / 跑某個指令」時，必須先過這三關，缺一不可：

1. **不靠單一字串推論行為**：binary `strings` 撈到的 user-facing 訊息只能當「這個功能存在」的弱證據，不能當「按 X 鍵會做 Y」的強證據。要找到 keybinding 註冊表 / setting schema / 對應 handler 邏輯才算成立。
2. **建議「動系統狀態」（zshrc、設定面板、權限）前，先用副作用最小的方式試一次**：能跑乾測就跑乾測（例如直接 `EDITOR=... cot -w /tmp/test`），不要叫使用者重啟才驗證。
3. **猜測時要說「我猜」**：如果只有 binary 字串證據沒有實測，明說「我推測是這樣，可能要實測才能確定」，不要用肯定句。

當 Balian 回報「按了沒反應 / 跑了沒效果」時：
- 不准繼續加碼（「再裝一個權限」「再重啟一次」）來救前一個猜測
- 立刻退回去查證最初的假設，承認猜錯比讓他繼續浪費時間重要

**第一次寫下**：2026-05-14

---

## R003 — 推薦外部資源 / 跨機器指令前，必須 probe 過實際存在性

**失敗訊號**（2026-05-14）

同一個 session 重複犯兩次，模式相同：

**事件 A**：Balian 要在 High Sierra 上裝 VPN，我說「Tailscale 1.40 系列是最後支援 High Sierra 的版本，到 `https://pkgs.tailscale.com/stable/#macos` 抓 1.40 的 pkg」。實際 `curl -I` 驗證後，`pkgs.tailscale.com/stable/Tailscale-1.40.x-macos.pkg` 全部 404，這個 URL pattern 不存在。我把他指向不存在的東西，浪費他半小時。

**事件 B**：要他在 Claude Code 對話框用 `! sudo installer ...` 開頭跑 sudo 命令，我斷言「`!` prefix 會讓 sudo 拿到 tty，密碼 prompt 正常出現」。實際他跑了之後直接撞 `sudo: a terminal is required to read the password`——`!` prefix 跑的是 non-interactive shell，沒 tty。我沒驗證過 `!` 的執行模型就叫他用。

**Harness 層**：觀測層（用模糊記憶當定論）+ 約束層（沒擋「未 probe 就推薦外部資源／跨機器指令」）

**永久規則**

當教練要建議使用者去抓某個 URL、跑某個指令、或仰賴某個外部資源時：

1. **URL 推薦前必須 probe**：用 `curl -sI -o /dev/null -w "%{http_code}"` 或 WebFetch 確認 URL 真的回 200，再貼給使用者。不准只靠「我記得官網有放歷史版本」這種模糊印象。

2. **跨機器 / 跨工具的執行模型不靠記憶**：`!` prefix 在 Claude Code、`do shell script` 在 osascript、`sudo -A` 的 askpass、`launchctl bootstrap` 在不同 macOS 版本——這些行為要先用一個 `echo $$ && tty` 之類的 0 風險命令乾測過，再要求使用者跑會改系統的命令。

3. **舊軟體 / 舊 OS 的支援度不靠記憶**：「X 軟體哪個版本是最後支援 Y 系統」這類資訊半年就會過時。如果要推薦，先去官網 changelog / 歷史版本頁實際確認，找不到就誠實說「找不到，建議改另一條路」，不准腦補。

4. **重複的失敗模式要追加規則，不准把它當「下次注意」**：同一個 session 內兩次「未驗證就推薦」算嚴重，要立刻 ratchet，不能等使用者下次又踩才寫。

**已驗證的環境陷阱（這次踩到的具體事實）**

- macOS 26 (Tahoe) 的 TCC 會擋 `with administrator privileges` 跑的 root 程序讀 `~/Downloads`，要先 `cp` 到 `/tmp` 才能 `installer -pkg`
- macOS 26 的 `systemsetup -setremotelogin` 需要終端機（或呼叫程序）有 Full Disk Access 權限，CLI 無法繞，必須用 GUI 在「系統設定 → 一般 → 共享 → 遠端登入」開
- macOS 26 上「分享 / 共享」在「一般」底下，不是左側獨立項目
- ZeroTier 1.16 在 macOS High Sierra 上會用 feth driver，可能耗盡 kernel mbuf 池，徵兆是 `ping: sendto: Cannot allocate memory`。重開機可清空 buffer
- ZeroTier 的「設備 ID」= Node ID（10 位十六進位），不是 Network ID（16 位十六進位）
- macOS ZeroTier authtoken 在 `/Library/Application Support/ZeroTier/One/authtoken.secret`，user 想跑 `zerotier-cli` 要 cp 到 `~/Library/Application Support/ZeroTier/One/` 並 chown
- 在 Claude Code 環境跑需要 sudo 的指令，正解是 `osascript -e 'do shell script "..." with administrator privileges'` 觸發 GUI 密碼 dialog，不是 `!` prefix

**第一次寫下**：2026-05-14

---

## R004 — Probe 含 secret 的檔案前，必須先驗證 key 結構，再決定能不能印任何 byte

**失敗訊號**（2026-05-15）
> 安裝 Claude Code Channels Telegram plugin，Balian 把 BotFather token 寫進 `~/.claude/channels/telegram/.env`。教練要驗證 .env 格式，跑 `head -1 "$F" | cut -c1-20` 想印 key 部分（預期 `TELEGRAM_BOT_TOKEN=` 19 字 + `=` 1 字 = 20 字，剛好遮住 token）。
> 但 Balian 只貼了 token 本身、沒寫 key 前綴，於是 `cut -c1-20` 把 **token 前 20 字**（含 bot_id `8821446350:` 和 secret 開頭 `AAFEjZSZs`）整段印進 conversation tool result。
> 等於教練親手把使用者的 secret 寫進對話 log。Balian 要立刻去 BotFather `/revoke` 重新生 token 才安全。

**Harness 層**：工具層 + 約束層
- 工具層失敗：probe 指令的設計假設「key 一定存在 + key 在前面」，這個假設破掉時直接把 secret 印出來，沒有 fail-safe
- 約束層失敗：對「會碰 secret 檔的命令」沒有強制走「先看結構再看內容」的順序

**永久規則**

當教練要 probe 任何可能含 secret 的檔案（`.env`、`~/.aws/credentials`、`~/.ssh/*`、token 檔、API key 檔），必須照以下順序，不准跳：

1. **第一輪：只看 metadata，不看任何 byte**
   - `ls -la`（權限、大小）
   - `wc -l`（行數）
   - `file`（編碼、換行格式）
   - 大小異常（太短 / 太長）就停下來問使用者，不要往下印

2. **第二輪：只看 key 結構，不印 value**
   - `grep -c '^[A-Z_]*='`：算有幾行符合 `KEY=value` 格式
   - `awk -F= '{print $1}'`：只印 `=` 左邊的 key 名稱
   - 如果 `=` 不存在 → 直接報「格式錯誤，使用者沒寫 key=value」，不要 fallback 印任何位置的字元

3. **第三輪：要 print value 才能診斷時，必須遮罩**
   - 只印長度（`${#VAL}`）
   - 要看內容只印前 3 + 後 3，中間 `...`
   - **不准用「印前 N 字」的方式來「順便驗證 key 在不在」**，這是這次出事的反模式

4. **任何 cut / head -c / sed 切片印出來前，先檢查切片區間絕對不會落在 `=` 右邊**
   - 不能寫 `cut -c1-20` 然後祈禱 key 剛好 20 字
   - 要寫 `awk -F= 'NR==1 {print $1}'` 這種 **語義切片**（切 key/value 分隔符），不要寫位置切片

5. **Token / secret 一旦進 conversation log，視為完全洩漏**
   - 不論只印了前段、後段、或一半，都要使用者去重新生
   - 不要安慰「應該還好」「沒印全」，secret 結構部分可猜，安全假設就是洩光
   - 立刻給出 revoke / regenerate 流程，越快越好

**第一次寫下**：2026-05-15

---

## R005 — Context 壓縮後必須先 TaskList 對帳，才能繼續做事或回報完成

**失敗訊號**（2026-05-15）
> Balian 給 7 個 PDF 要整理成給家人看的 HTML。處理到一半 context 滿被壓縮（recap / Crunched）。壓縮前我建了 8 項任務、把「閱卷6」標 in_progress。
> 壓縮後我繼續把閱卷6、閱卷7 讀完、HTML 也寫出來了，**卻沒有回頭呼叫 TaskUpdate 把 #6 #7 #8 標 completed**。
> 我跟使用者說「完成了」，但畫面上 task widget 還停在壓縮前快照 `5 done, 1 in progress, 2 open`。使用者看到「我說完成 vs. 進度顯示沒完成」直接產生認知衝突，反問「這是什麼狀況」。

**Harness 層**：觀測層 + 協調層
- 觀測層失敗：進度追蹤（task tracker）沒反映真實狀態，使用者無法靠 widget 重建「到底做完沒」
- 協調層失敗：context 壓縮是一個 handoff 邊界，handoff 後沒有「對帳」步驟，舊狀態被當成現狀

**永久規則**

當看到 context 壓縮訊號（recap / Crunched / "This session is being continued"）時，**恢復工作的第一個動作**不是繼續做事，是對帳：

1. **先 `TaskList`，逐項比對「任務狀態 vs. 實際完成度」**
   - 壓縮摘要說做完的、檔案已存在的、工具回報 success 的 → 對應任務若還是 pending/in_progress，立刻 `TaskUpdate` 補成 completed
   - 補完狀態再繼續下一步工作

2. **回報「完成」前，task widget 必須先跟事實一致**
   - 不准在 #N 還掛 in_progress / pending 的情況下對使用者說「全部完成了」
   - 說「完成」之前先掃一次 TaskList，確認沒有殘留未更新的狀態

3. **工作做完當下就 TaskUpdate，不要積到最後**
   - 每完成一個可驗證的子項（檔案寫出、PDF 讀完）就即時更新對應任務，降低被壓縮截斷時的狀態落差

4. **使用者指出「你說的跟畫面顯示對不上」時，先認帳是自己沒同步狀態，不要急著解釋工作有做**
   - 真相是「事做了、狀態沒更新」，要直說是觀測層沒收尾，當場修正 widget，再說明

**第一次寫下**：2026-05-15

---

## R006 — 每筆工作強制 DMR，跳過必須留 skipped 痕跡

**失敗訊號**（2026-05-15）
> 建立「上工 / SU」開工 briefing 代碼時發現：2026-05-14 Balian 選擇「不記 PDCA 規劃進 DMR」，
> 導致那段約數小時的規劃工作完全沒進工時統計。「上工」要報「昨天花多少時間、做幾個項目」時，
> 資料源殘缺，報出來的數字必然偏低，使用者無法靠它做真實的 PDCA 檢討。

**Harness 層**：約束層 + 觀測層
- 約束層失敗：沒有「每結束一件工作必須 DMR」的擋線，使用者可以隨意跳過
- 觀測層失敗：工時資料不完整，無法重建完整工作軌跡，PDCA 的 Check 失去依據

**永久規則**

1. **每結束一件可辨識的工作（含規劃、諮詢、debug、寫文件、派工）必須寫一筆 DMR**，不准以「這次不適合 / 純規劃 / 沒程式碼」為由完全跳過
2. **教練在工作收尾時主動觸發 DMR log**，不等使用者開口要求
3. **「上工 / SU」briefing 時，比對工作日誌 vs DMR**：日誌有條目但 DMR 缺對應 → 主動追問補登，不准默默略過
4. **使用者堅持某筆不記 → 必須寫一筆 `status=skipped` + `notes` 註明原因**，不能完全不留痕跡（缺口要可見，才知道工時統計被低估）

**第一次寫下**：2026-05-15

---

## R007 — 渲染端必須涵蓋所有 slide type，未知 type 不准靜默丟內容

**失敗訊號**（2026-05-15）
> Balian 看 video2slides 轉出來的簡報，發現某張只有標題「人才的全新定義：馬斯克的洞見」、body 全空（顯示「按一下即可新增文字」placeholder），問「有點簡陋，原因是？」
> 查證後：`outline.json` 資料完整，那張是 `type: "quote"`，`quote` / `source` 兩個欄位都有正確內容（馬斯克談人才的引言）。
> 但 `slides_generator.py` 的 `_build_body_text()` 只讀 `subtitle` 和 `bullets`，`quote` / `source` 從沒被讀取 → body 渲染成空字串。17 張裡 2 張 quote 型全部空白，使用者只覺得「簡陋」而非「全壞」，差點當品質問題放過。

**Harness 層**：執行層 + 觀測層
- 執行層失敗：LLM 端（analyzer）產出的 slide type 超出渲染端（generator）的處理分支，多出來的內容欄位被靜默丟棄，沒報錯沒 log
- 觀測層失敗：內容遺失完全無聲，要靠人眼逐張看簡報才發現，pipeline 不會告訴你「這張我沒東西可放」

**永久規則**

當生產者（LLM / analyzer）與消費者（renderer / generator）之間用結構化資料（JSON outline、schema）交接時：

1. **消費端的分支必須涵蓋生產端 schema 的所有合法 type**：改 prompt / 模板新增任何 slide type、區塊型別、訊息型別時，同一個 PR 要連消費端的對應渲染分支一起加，不准只改一邊
2. **未知 type / 空 body 不准靜默通過**：渲染端遇到「這個 type 我沒對應分支」或「算出來 body 是空字串但 slide 有內容欄位」時，必須 fallback（把所有文字類欄位倒進 body）或至少 log warning，不可以產出空白 slide 當沒事
3. **跨層欄位對照要列清單**：analyzer 的 prompt JSON 範例只給了 `title`/`content` 兩種，但模板允許更多 type——這種「schema 在 A 處定義、渲染在 B 處實作、兩邊沒對照表」的結構，教練看到要主動指出是 R007 類風險
4. **這次只做最小修（補 quote/source 分支）是 Balian 的決定**，但教練要記得：最小修沒解掉根因（下一個新 type 會再空白），下次再出現同類失敗要升級成防呆 fallback，不准重寫一條新規則假裝沒踩過

**第一次寫下**：2026-05-15

