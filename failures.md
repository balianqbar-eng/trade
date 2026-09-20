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

## R008 — R004 升級：教練自己讀任何 secret-pattern 檔名前，必須先過硬擋，不准反射 cat

**失敗訊號**（2026-05-15，寫下 R004 的隔天，教練自己再犯同一模式）
> 教練為了查 DMR log 格式，反射性跑 `cat dmr/token_dmr.json`，沒先看檔名 pattern、沒先驗證是不是 secret 檔。
> 一整包 Google OAuth 憑證（access token / **refresh_token** / **client_id** / **client_secret** / scopes）被印進 conversation log。
> R004 已經白紙黑字寫過「probe 含 secret 的檔案前必須先驗證 key 結構」，但 R004 的措辭是「教練 probe 使用者的 secret 檔」的情境，
> 沒有綁住「教練為了別的目的（查格式）順手 cat 到一個剛好是 secret 的檔」這個反射動作。規則存在，照樣踩。

**Harness 層**：約束層（R004 的擋線範圍不夠，沒涵蓋教練自己的 reflexive read）+ 觀測層（檔名 `*token*` 是強訊號，沒在讀之前 pattern-match）

**永久規則（綁住教練自己的工具呼叫，不只是給 Balian 的建議）**

1. **任何 `cat` / `head` / `tail` / `Read` / `sed` / `grep` 一個檔之前，先看檔名**。命中下列 pattern 之一就進 R004 強制流程（先 `ls -la` + `wc -l`，再 `awk -F= 'NR==1{print $1}'` 只看 key，**絕不直接印內容**）：
   - `*token*` `*secret*` `*credential*` `*.pem` `*.key` `id_rsa*` `.env*` `*.p12` `*.keystore`
   - `*.json` 且路徑含 `auth` / `oauth` / `credential` / `token`（如本次 `dmr/token_dmr.json`）
   - `~/.aws/*` `~/.ssh/*` `~/.config/gcloud/*` `*service-account*`
2. **「我只是要查格式 / 查結構」不是跳過理由**。要查格式就 `awk -F'[:=,]' 'NR==1{print $1}'` 或先 `python -c "import json,sys;print(list(json.load(open(sys.argv[1])).keys()))" FILE`（只印 key 名，不印 value），不要 `cat` 全檔。
3. **R004#5 對教練自己同樣適用**：secret 進 log = 完全洩漏，不准用「access token 過期了」「沒進 git」當安慰收尾——持久憑證（refresh_token / client_secret / private key）即使 access token 死了仍要求 revoke + rotate。
4. **規則已存在卻再犯 = 約束層擋線設計失敗，不是「不小心」**。依 R003#4 立刻升級擋線範圍（這就是本條），不准記成「下次注意」。下次同類再犯要再升級成 hook 強制（pre-read filename guard），不再靠自律。

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


---

## R009 — 「已驗證交付」只認 mark-done 蓋章；上工必讀效益儀表板

**失敗訊號**（2026-05-16）
> 使用者連三問都在回顧（今天做啥/昨天花多久/用幾天），盤點出 15 天投入 40.7h，
> 但同期通過驗證閘的交付 = 0。投入時數漂亮、已驗證交付掛零 = 效益假象：
> 用「我花了幾小時」自我感覺良好，卻沒有任何指標逼出「這些小時換到幾個真的驗過的成果」。
> 根因：DMR 的 status=completed 可由自己 `log --status completed` 直接宣告，
> 「自報完成」與「真的過驗證閘」長得一模一樣，PDCA 的 Check 失去區分能力。

**Harness 層**：觀測層（沒有可信的效益指標，無法判斷是否真進步）+ 約束層（completed 可自宣告，指標可灌水）

**永久規則**

1. **「已驗證交付」嚴格定義 = DMR `status=completed` 且 `verified_at` 非空**。`verified_at` 只由 `dmr.py mark-done` 蓋章；直接 `log --status completed` 不算交付，只算「自報」
2. **效益指標看 `效益儀表板.md`，不看投入時數**。該檔由 `python dmr/dmr.py scoreboard` 全自動產生，禁止手改；任何 DMR 異動後重跑 scoreboard
3. **上工 / SU briefing 必須讀 `效益儀表板.md` 並回報「已驗證交付數」與「交付/h」**，不准只報「昨天花了幾小時、做了幾項」——時數不是效益，過閘的交付才是
4. **教練看到使用者用「我花了 X 小時」自我評估進度，要立刻擋下並改問「過 mark-done 的有幾筆」**。回顧不等於進步；沒過驗證閘的工作在效益上等於沒發生
5. **DMR 上線前（< 2026-05-14）無資料 → 標「—」不標 0**：不可量測與量測為零必須可區分，否則又是另一種假象

**第一次寫下**：2026-05-16


---

## R010 — Telegram bridge 必須 launchd 託管，禁止手動起；上工 SU 先跑 healthcheck

**失敗訊號**（2026-05-18）
> 使用者在 Telegram 送「上工」，雙勾送達卻無任何回覆。排查發現 bridge **整個沒在跑**：
> 無 `claude --channels` session、無 `bun server.ts` poller、無 `bot.pid`，
> `getWebhookInfo` 顯示 `pending_update_count=1`——訊息卡在 Telegram server 沒人領。
> 這是第二次踩「bridge 沒跑」：之前的記憶（[[telegram-bridge-setup]]）只解了
> 「怎麼正確啟動（缺 --channels flag）」，沒解「怎麼確保它一直在跑 / 重開機後自動拉起」。
> 根因：bridge 靠人記得在普通 Terminal 手動 `claude --channels` 並讓它閒置；
> Terminal 一關、機器一重開、session 一掉就靜默死亡，沒有任何訊號。

**Harness 層**：約束層（啟動靠人記憶，無強制持久化）+ 觀測層（死掉完全無聲，要靠使用者發現沒回覆才知道）

**永久規則**

1. **Telegram bridge 由 launchd 託管，不准手動起**。Agent = `com.balian.telegram-bridge`
   （`~/Library/LaunchAgents/com.balian.telegram-bridge.plist`），`RunAtLoad`+`KeepAlive`：
   登入自動拉起、掛掉自動重啟。啟動腳本 `~/telegram-bridge/bridge-daemon.sh`
2. **絕不從 cmux / Terminal 再手動 `claude --channels` 起第二個**：兩個 getUpdates poller
   搶同一 token 會互踢。要重啟用 `launchctl kickstart -k gui/$(id -u)/com.balian.telegram-bridge`，
   不是開新 Terminal
3. **互動式 session 當 daemon 必須配 pty**：`claude --channels` 無 TTY 會 stdin EOF 秒退，
   plist 內用 `script -q /dev/null claude ...` 包起來。改 daemon 啟動方式時這條不准拿掉
4. **無人值守 bridge 用 `--permission-mode bypassPermissions`**：否則卡工具權限提示永遠不回。
   風險邊界靠 Telegram `access.json` allowlist（只本人 ID 能 driver）——
   若改 policy 成 pairing 或放寬 allowlist，這條 bypassPermissions 的風險假設就失效，要重新評估
5. **上工 / SU briefing 必須先跑 `~/telegram-bridge/healthcheck.sh`**：驗 launchd 載入 +
   claude/bun 進程在 + `getWebhookInfo` 的 `url:""` 且 `pending_update_count:0`。
   沒綠燈不准回報「bridge 正常」。教練看到使用者假設 bridge 在跑而沒驗，立刻擋下
6. **接第三方 plugin/工具，先讀它的架構與生命週期再設計持久化**：這次先搞清楚
   `.mcp.json`（bun server.ts 是 claude 的 MCP 子程序、隨 claude 生死）才寫得出對的 plist。
   延續 [[telegram-bridge-setup]] 教訓——不要先假設是環境問題

**第一次寫下**：2026-05-18


---

## R011 — 約束檔與觀測檔必須分離；觀測層只能在失敗前建立、且放在該專案目錄

**失敗訊號**（2026-05-18）
> 使用者問「觀測層+約束層的邏輯架構」，連續把兩層誤解成願望（約束層=目標、觀測層=改善生活）。
> 被要求指出美容業 SaaS 的觀測檔時，指了 `nail_eye_content_pilot/專案章程.md`——
> 那是強約束檔（紅線 + 每階段 done-condition），不是觀測檔。實查：該專案目錄下零觀測檔，
> 全專案的「觀測」混在 repo 根目錄 `工作日誌.md`（1024 行，video2slides/美睫/美容/美甲/股票/錢哨
> 六視窗混檔），且使用者自承「只記做什麼、流水帳、查帳用」= 狀態 log 非行為+失敗軌跡。
> 並提「有遇到再新增」= 反應式建觀測層。違反其自身章程 `:84`「與各視窗區隔」。

**Harness 層**：觀測層（專案無獨立觀測檔、流水帳當觀測、反應式才建）+ 約束層（沒有規則強制約束檔／觀測檔分離）

**永久規則**

1. **每個長期任務視窗，約束檔（章程/done-condition）與觀測檔（行為+失敗軌跡）必須是兩個分開的檔**。把章程的進度區當觀測層 = 自動觸發本條
2. **觀測檔必須可追加、不可覆寫**，每筆記「試了什麼 / 預期 vs 實際 / 斷哪層 / 轉成哪條規則」，不是只記「做了什麼」。狀態流水帳不算觀測層
3. **觀測檔放在該專案目錄下**，不准混進跨視窗共用總表。共用總表只能當索引，不能當單一專案的觀測來源（自包含原則）
4. **觀測層只能在失敗發生前建立**，不准「遇到再補」——失敗後無軌跡 = 重建不能 = ratchet 不能。教練看到使用者說「之後再優化觀測／遇到再新增」立刻擋下
5. **教練看到使用者被要求給「約束 / 觀測 / done-condition」時改回一個「目標 / 願望 / 實作指令」，立刻點名這是同一個替換 pattern，不准放行**

**第一次寫下**：2026-05-18


---

## R012 — 設計 launchd / cron 自動化前，必須先套用 R003 的 TCC 陷阱：daemon 觸及路徑不准在 ~/Downloads|Desktop|Documents

**失敗訊號**（2026-05-18）
> 做「Benjamin 首頁上工區塊」的定時推送，建了 LaunchAgent `com.balian.briefing-push`，
> ProgramArguments 指向 `~/Downloads/balian/dmr/push_briefing.sh`。手動跑該腳本 `POST 200` 完全正常，
> 但 launchd 每次觸發都 `zsh: can't open input file: .../push_briefing.sh`、exit 127。
> 根因：macOS TCC 擋 LaunchAgent（/bin/zsh）讀 `~/Downloads`，沙箱化的程序根本看不到該路徑。
> **R003 的「已驗證環境陷阱」早就白紙黑字寫過「macOS TCC 會擋跑在受限情境的程序讀 ~/Downloads」**，
> 但設計新 daemon 時沒回查 R003，直接把腳本＋資料（dmr.py / .briefing_token / venv）全擺 ~/Downloads。

**Harness 層**：約束層（有既存規則 R003 卻沒在設計新元件時套用）+ 觀測層（launchd 靜默失敗，靠使用者看到空頁才發現；deploy 腳本的「驗收」印了 `generated_at: ?` 但沒 hard-fail 擋下）

**永久規則**

1. **任何 launchd / cron / 背景 daemon 設計時，第一步先回查 R003 的 TCC 陷阱清單**。daemon 會「開啟 / 讀 / exec」的所有路徑（腳本本身、資料、venv、secret）只要落在 `~/Downloads`、`~/Desktop`、`~/Documents` → 預設失敗，必須先解 TCC 才能上
2. **解 TCC 兩條路，設計時就要選定，不准事後才發現**：(a) daemon 觸及路徑全移出受保護目錄；(b) 對 launchd 實際執行的 binary（如 `/bin/zsh`）授 Full Disk Access（GUI 手動、且範圍涵蓋所有該 binary 的執行，安全要評估）
3. **本機 `~/Downloads/balian` 已知有此陷阱**：此專案任何新 daemon 不准假設「手動跑得起來 = launchd 跑得起來」。驗收必須包含「`launchctl kickstart -k` 後讀該 agent 的 log 確認 exit 0」，不是只手動跑一次就算過
4. **部署 / 驗收腳本遇到關鍵步驟失敗必須 hard-fail（exit 非 0 + 大聲）**，不准印個 `generated_at: ?` 就繼續往下印「完成」。成功安靜、失敗大聲——失敗的驗收不准長得像成功
5. **教練看到要建「定時 / 背景 / 自動」任何東西，主動問「它要碰的路徑在不在 ~/Downloads|Desktop|Documents？TCC 怎麼解？」**，沒答案不准進實作。這是 R003 的 ratchet 升級：R003 記了事實，R012 強制在設計階段就套用，不准重新踩

**已驗證事實（這次確認）**
- LaunchAgent 跑 `/bin/zsh <script>`，script 在 `~/Downloads` → `zsh: can't open input file`、`last exit code = 127`，手動同指令正常
- `~/telegram-bridge`（R010 的 bridge daemon 所在）不在 TCC 保護目錄，所以那個 LaunchAgent 沒踩到——不是運氣，是路徑選對
- 修法採「授 /bin/zsh FDA」（使用者 2026-05-18 決定）；FDA 為 GUI-only，無 CLI，授後需 `launchctl kickstart -k` 重觸發

**第一次寫下**：2026-05-18


---

## R013 — 密鑰一律不進 repo；從 git「移除」不等於修復，必先輪換再清歷史；無認證的對外 listener 等同公開後門

**失敗訊號**（2026-05-19）
> 安全稽核發現：真實永豐券商 API key/secret（`SINOPAC_API_KEY`/`SINOPAC_SECRET_KEY`，可下單）
> 連同 `trade.env` 被 commit 進 git 歷史（commit `4d2116a init`），且 repo
> `github.com/balianqbar-eng/trade` 為 **public** 已 push。後續 commit `e9ac756`
> commit message 寫「remove sensitive files and binaries from tracking」——當時已知有 sensitive
> files，卻只 `git rm` 移出追蹤，沒輪換 key、沒清歷史。任何人 `git show 4d2116a:trade.env`
> 即取得可下單金鑰 = 進行式金錢風險。同時 ttyd `:7681` 綁 `*`（所有介面）、`-W` 可寫、
> 無 `-c` basic auth、無 SSL，等於同網段任一裝置開瀏覽器即得無密碼完整 shell（tmux `cc`）。

**Harness 層**：約束層（無規則強制密鑰永不進 repo、新 repo 第一個 commit 前先 .gitignore）+ Hooks 強制執行層（無 pre-commit/pre-push secret 掃描擋下含密鑰的 commit）+ 觀測層（洩漏靜默——稽核才發現，無對外 listener 告警；e9ac756 顯示對 git 分散式歷史模型的誤解，以為 git rm = 安全）

**永久規則**

1. **密鑰一律不進 repo。任何 `git init` / 新專案 / 第一個 commit 前，先建 `.gitignore` 涵蓋 `.env`、`*.env`、`*.key`、`*.pem`、`credentials*`、`*secret*`、`trade.env`，且只 commit `.env.example`**。教練看到要 push 新 repo 或 git init，主動問「.gitignore 有了嗎？有沒有 .env / 券商 / API key 會被帶進去？」沒答案不准 push
2. **從 git 移除敏感檔 ≠ 修復**。一旦 secret 進過任何 commit（即使後續 git rm），必須假設已外洩，強制順序：(a) 立刻到該服務後台 revoke + 輪換 key；(b) 才做 git 歷史 rewrite（filter-repo/BFG）。先清歷史不輪換 = 只是拖延，教練必須擋下這個順序顛倒
3. **public repo 的洩漏假設最壞**：不只輪換，還要查該服務（券商/雲端）近期有無未授權操作紀錄
4. **對外服務（綁非 `127.0.0.1` 的 listener）必須有認證**。無認證且可寫的 shell（如 ttyd `-W` 無 `-c`）等同公開 RCE，設計時就要決定綁 loopback 或加 auth，不准「先跑起來再說」
5. **Hooks 層應升級**：加 pre-commit/pre-push secret 掃描，擋 `sk-ant-`、`AIza`、`AKIA`、`SINOPAC_*=` 有值、Telegram bot token 樣式進版控。成功安靜、失敗大聲擋下
6. **對外開放服務是觀測項**：上工 briefing 或定期掃 `lsof -nP -iTCP -sTCP:LISTEN` 中綁非 loopback 且無認證者，列為待處理，不准靜默

**已驗證事實（這次確認）**
- `trade.env` 在 commit `4d2116a (init)` 含真值 `SINOPAC_API_KEY`/`SECRET`，`e9ac756` 才移出追蹤，歷史仍可 `git show 4d2116a:trade.env` 取回
- `git remote` = `https://github.com/balianqbar-eng/trade.git`，使用者確認 **public**
- ttyd pid 1396 綁 `*:7681`、參數無 `-c`、無 SSL、`-W` 可寫；本機 `192.168.68.107`，無 Tailscale CLI
- `CC_instructions_balian_railway.md:406` 的 `sk-ant-xxxxxxxx` 為文件佔位符（誤報，非洩漏）——稽核要區分佔位符與真值，不可一律報警造成狼來了

**第一次寫下**：2026-05-19


---

## R014 — `mktemp` BSD/GNU 範本差異把 KeepAlive 腳本鎖死 + 共用欄位多寫入者導致自癒同步被靜默覆寫（v2s-tunnel ↔ Benjamin `app_url` 斷鏈）

**失敗訊號**（2026-05-19）
> 使用者打開 Benjamin → 影音轉學習簡報 → 操作介面 = 灰白空白 + 紅燈，但
> 本機 `video2slides :8001` 健康、`cloudflared` 活的 quick tunnel 也健康。追到兩個獨立根因連鎖：
> (a) `tunnel_v2s.sh` 用 `mktemp /tmp/cf_v2s.XXXXXX.log` —— macOS BSD `mktemp` 只
> 替換**結尾**連續 `X`，這個範本 `X` 後接 `.log` 不被替換，首次建出字面檔名
> `/tmp/cf_v2s.XXXXXX.log`；trap 沒清掉（或前次未走 EXIT），之後每次 launchd
> kickstart 都 `mkstemp failed: File exists` → `CFLOG=` 空 → `cloudflared` 重導空字串
> → tunnel 永遠起不來。KeepAlive 不停重啟，失敗只在 `/tmp/com.balian.v2s-tunnel.log`
> 累積，無人通知。
> (b) Benjamin `/api/projects/{id}` PUT 接受前端整包物件、白名單裡含 `app_url`/
> `health_url`。tunnel 腳本同步成功後，使用者瀏覽器分頁裡的舊 state（早上載入時
> 的過時 `engaged-inspection-recruitment-loops...`）被任意 PUT 觸發（例如按「編輯名稱」）
> 整包送回，把腳本剛寫的 fresh URL 靜默蓋掉 → Benjamin 指回死網址、iframe 灰白。

**Harness 層**：
- 工具層（mktemp 範本非可攜，BSD/GNU 行為差異未驗證就上線；R012 是 launchd 端的同類「跨環境假設未驗」）
- 觀測層（KeepAlive 啟動失敗只在 /tmp log 累積，無 push 告警；上游 Benjamin 紅燈只有開分頁才看到；fresh 同步被覆寫亦無記錄）
- 約束層 / 多 agent 協作（共用欄位 `app_url`/`health_url` 無 owner 規則；tunnel 腳本與瀏覽器同時是寫入者、無協調，整物件 PUT 是 footgun）

**永久規則**

1. **macOS `mktemp` 範本只能在結尾連續 `X` 處替換**。禁止寫 `mktemp PREFIX.XXXXXX.SUFFIX`（X 後接副檔名）。要副檔名用 `mktemp -t prefix` 或建完後 `mv`。新腳本 review 時 grep `mktemp.*X+\.\w+` 模式擋下
2. **跨環境的命令必須在目標 OS 驗證一次再上線**：`mktemp`、`date`、`sed -i`、`readlink` 在 BSD/GNU 差異多。R012 是 launchd-shell-vs-interactive、R014 是 BSD-mktemp-vs-GNU，同一類根因
3. **任何 `KeepAlive=true` 的 launchd 服務，啟動失敗必須有 log 以外的告警通道**（HTTP push、briefing 顯示、Telegram bridge），否則會無限 reboot loop 直到使用者偶遇。「成功安靜、失敗大聲」對 KeepAlive 尤其要強制
4. **共用狀態的每個欄位必須有唯一寫入者**。`app_url`/`health_url` 為「tunnel 腳本 owned」；Benjamin 後端 PUT **必須在 server 端把這些欄位從前端 payload 移除**（前端可以送，後端忽略），不靠前端自律。否則任何長開的瀏覽器分頁都是覆寫炸彈
5. **「整包物件 PUT」是 footgun**：前端載入時的 state 在按下儲存時可能已過期數小時。改用 PATCH/partial update，或 PUT 前重抓最新版做 diff。R011（balian-quant PUT 白名單）的延伸：白名單還不夠，要分「使用者可寫」vs「系統 owned」
6. **多寫入者欄位被覆寫要可追溯**：log 寫入者來源（user-agent / `X-Writer` 標頭），「腳本剛寫又被前端寫回舊值」自動告警
7. **教練看到「同個欄位有多個來源會寫」立刻問：誰是 owner？非 owner 寫入怎麼擋？** 沒答案不准上線

**已驗證事實（這次確認）**
- 修為 `mktemp /tmp/cf_v2s.XXXXXX`（X 在尾），`launchctl kickstart -k gui/$(id -u)/com.balian.v2s-tunnel` 後 log 出現 `tunnel up: https://radical-airfare-angels-row.trycloudflare.com`、`PUT /api/projects/video2slides -> 200`、`Benjamin app_url 已同步`
- 同步後 `/api/projects` 中 video2slides 的 `app_url` 與 tunnel URL 一致比對 `True`，新 URL `/health` `/ui` 皆 200
- 殘留的字面檔 `/tmp/cf_v2s.XXXXXX.log` 在修法後不再撞名（pattern 不同），可不刪
- 規則 4/5 未實作：Benjamin 後端 PUT 仍接受 `app_url`/`health_url`，舊瀏覽器分頁覆寫風險仍在；只要使用者下次在舊分頁按編輯名稱就會復發

**第一次寫下**：2026-05-19


## R015 — 教練 ON 動工前必須 grep memory + failures.md 找已存在 ratchet（特別 plist/launchd/TCC/~/Downloads/Supabase/DB-migration 範疇）

**失敗訊號**（2026-05-25）
> 使用者要求把家庭財務 UI server 改 launchd 自啟動。教練 ON 第一回，按既有 plist 直接 `launchctl load` → python 撞 `PermissionError: [Errno 1] Operation not permitted`（TCC 擋）。memory 早有 R012「launchd 跑 ~/Downloads 需 /bin/zsh wrapper」記錄，但教練 ON 動工前**沒 cross-check**，吃了一次失敗後才用 zsh wrapper 修好。違反 R012 第一句「設計 launchd / cron 自動化前」（不是「失敗後補」）。

**Harness 層**：
- 指令層（教練人格）：有「先查 memory」精神但沒明文強制
- Memory + Search：memory 有 R012 但不會主動跳出，要教練主動 grep 才 hit
- 觀測層（部分）：launchd KeepAlive=true 撞 TCC 會無限 retry，靜默累積到 /tmp log，無人通知（R014 規則 3 同類根因）

**永久規則**

1. **教練 ON 動工前**，若任務涉及以下範疇，必須先 `grep -i` memory + failures.md：
   - launchd / plist / cron / Schedule / KeepAlive
   - macOS TCC / FDA / `~/Downloads` `~/Desktop` `~/Documents`
   - Supabase auth / RLS / magic link / token refresh / Site URL
   - DB migration / schema 變更（alter table / drop / index）
   - `mktemp` / `sed -i` / `readlink` / `date -u` 等 BSD vs GNU 跨平台命令
   - 前一次踩過坑的工具（git / brew / pip / npm / pyenv）
   - **寫新 ratchet 條目分配 R 編號前**：先 `grep "^## R" failures.md | tail` 找最大編號 + 1（自 R017 後補強，第一次寫 R017 就因沒查直接用 R016 撞既有編號）

2. grep 結果**有 hit** → 必須在「執行計畫」階段**明文引用該 R 編號** + 說明這次怎麼套用；
   grep 結果**無 hit** → 計畫中明文宣告「memory + failures.md 無相關 ratchet」，確認是新領域。

3. **失敗後才 fallback** 等於 ratchet 沒被執行。要 ratchet 的不是「失敗時的修法」，而是「教練在計畫階段就引用」這個前置動作。這次規則要求把第 1 點寫進「執行計畫」模板的固定欄位（不能省略）。

4. 對使用者：教練若違反第 1 點（沒先 grep 就動工撞既有 ratchet），使用者有權說「教練扣分，這次失敗不算 user 問題」——這是教練的「鎖鍊測試」。R017 編號衝突就是教練自爆案例。

**已驗證事實**：本次最終用 `<string>/bin/zsh</string><string>-c</string><string>cd ... && exec /usr/bin/python3 -m http.server 8123</string>` wrapper 過 TCC，`launchctl list` 顯示 PID 65151（KeepAlive 殺一次後新號），HTTP 200，log 看到 GET 紀錄；殺 PID 5 秒內 launchd 自動拉回新 PID。**但這是吃失敗才繞的**——教練在 R015 寫下後，下次同類動作不准再吃這個失敗。

**第一次寫下**：2026-05-25

---

## R016 — LLM 推理輸入必須是真實資料；無資料源的評分項刪除，不准 hardcode 假數據蒙混

**失敗訊號**（2026-05-25，戰情室規劃決策 6/6）
> 雙團隊戰情室的選股 SOP（Agent B-1 量化篩選官）有 4 個評分欄位（`top5_branch_ratio` / `director_ratio` / `revenue_yoy` / `has_catalyst`）**全部 hardcode 假數據**。
> L4/L5 評分基於這 4 個假欄位，shortlist 看起來有「分數」但根本沒接資料源。
> 在 B 接口下（量化 shortlist + LLM 題材辯論並行交集 → 訊號），這個 shortlist 會被當作辯論的「事實輸入」。
> = LLM 基於假事實推理 → garbage in garbage out → 你看到的訊號全是裝出來的。
> 這比「功能缺失」更危險，因為系統看起來在動，使用者會誤信輸出。

**Harness 層**：約束層 + 觀測層
- 約束層：缺一條「凡 LLM 推理輸入欄位，必須有真實 source 或砍除，禁止 hardcode default 蒙混」的硬擋
- 觀測層：缺一條「LLM prompt 拼裝前 log 所有輸入欄位的來源（real / hardcoded / fallback），任何 hardcoded source 必須在報告中標紅」的告示

**永久規則**

當教練看到任何「LLM agent 接收結構化資料做推理」（不限戰情室）的場景時，必須擋下並驗證：

1. **資料來源宣告**：每個欄位必須明示三選一
   - `real`：接到實際資料源（API / DB / file），驗證過至少跑得通
   - `n/a`：本次無資料 → 該欄位**從 prompt 與評分中移除**，不留任何 placeholder 0 / "未知" / TODO 進入推理
   - `hardcoded_for_dev`：開發階段暫填，必須在 module level 標 `# WARNING: hardcoded, DO NOT ship`，且 production 啟動時要有 assertion 擋下整個系統

2. **禁止「placeholder + TODO」這種混合**：常見壞 pattern 是 `revenue_yoy = 0  # TODO: 接 FinMind`，這在 demo 看起來像 0% 成長，LLM 會基於 0% 推「業績平平不推薦」，但實情可能是 +50%——比 crash 還可怕。要嘛真接資料，要嘛刪欄位，不准 placeholder。

3. **shortlist / signal 之類「結構化結果」進入 LLM prompt 前必須打 trace log**：標每筆紀錄每欄位的來源旗標，輸出報告必須在欄位旁標 `(real)` / `(hardcoded)`；使用者讀報告看得到資料品質。

4. **教練自查**：當使用者描述「我想把 X 系統的輸出餵給 Y agent 做決策 / 寫報告」時，教練必須反問「X 系統的所有欄位都接到真實資料了嗎？跑一次 list 給我看」，沒過這關不准動 prompt / pipeline。

**對應觸發場景**：選股 SOP → 戰情室辯論、財務 UI 七模組評分 → 醫生模式 LLM、video2slides 投影片大綱 → 簡報生成、任何「先量化 / 結構化，再 LLM 推理」的 pipeline。

**第一次寫下**：2026-05-25


## R017 — 同一 UX pattern 散落多處：refactor 一處時必須 grep 同類 pattern 全改或標 TODO

> **編號衝突教訓**：本條第一次寫成 R016 但 failures.md 既有 R016（LLM 推理真實資料）。教練 R015 剛寫完就違反 R015 精神（沒 grep 既有編號），自爆案例 → 補強進 R015 規則 1。

**失敗訊號**（2026-05-25）
> 使用者第二天 dogfooding 「新增金融帳號沒反應」。診斷：addAccount 還是用 `prompt()` 連跳 3 次，但 Chrome 把這個 origin 的對話方塊靜默封掉（使用者前一輪可能不小心勾過「停用此網頁上的其他對話方塊」），整個 onclick → prompt → 沒回應，**沒任何 error、沒 toast、卡片沒更新、Supabase 沒新筆**。
>
> 上一輪（同一週前）使用者抱怨「addFixed 連跳 prompt 太煩」，已改成 modal 化。**addAccount 同樣 prompt 連跳的 pattern 漏改**，等於同一個 UX 病灶醫了一隻腳沒醫另一隻。第二隻腳一週後撞 Chrome prompt 鎖才被發現。

**Harness 層**：
- 工具層（瀏覽器原生 `prompt()` `alert()` `confirm()` 在 Chrome 是「使用者可關閉」的，封鎖時靜默失敗，**沒可靠錯誤通道**）
- 觀測層（Supabase 沒新筆 + 卡片沒更新 + 無 toast = 失敗訊號完整但只在使用者親自驗證才發現）
- 約束層（沒有「同 pattern 全 codebase 統一」的機制）

**永久規則**

1. **禁止用 `window.prompt()` `window.alert()` `window.confirm()` 做 UX 主流程**。它們在 Chrome 是 user-killable，封鎖時靜默 return null/false，**沒辦法 distinguish「使用者取消」vs「對話框被封鎖」**。
   - 例外：開發期 debug 一次性的可以用 confirm
   - 替代：用既有 modal pattern（`fixedItemModal` / `accountItemModal` 同款）

2. **refactor 一個 UX flow 時，必須 grep 整 repo 找同 pattern 的兄弟**。例如：
   - 改 addFixed 從 prompt → modal → 必須 grep `prompt(` 看其他地方還有沒有
   - 找到的 sibling 兩條路：(a) 一起改、(b) 留 `// TODO: R016 prompt → modal` 標記但**必須在當下 commit 訊息明文**
   - 不能「忘了」— 漏改就是 R016 復發

3. **教練 ON 看到 `prompt|alert|confirm` 出現在主 UX flow，先扣分再讓動工**。

4. 廣義版：**同 codebase 內「同名 helper / 同類 modal / 同類驗證流程」散落多處時，改一處要列出兄弟清單**，明文 commit 哪些一起改、哪些 TODO。
   - 對應 R011（PUT 白名單）+ R014 規則 4（共用欄位 owner）的更高層原則：「**沒有單一 source of truth 的東西，第一優先建立 source of truth**」

**已驗證事實**：本次把 addAccount 改成 modal 流程（共用 fixedItemModal 同款 pattern），新建 `accountItemModal` + `ACC_LABELS` config + `commitAccount` async 函式。整個 codebase 還剩多少 `prompt(` 待掃需要再 grep 確認；本次 ratchet 後下次任何使用者「點 X 沒反應」要先反射性懷疑「是不是又有 prompt() 漏改的 pattern」。

**第一次寫下**：2026-05-25

---

**R017 v2 補強 case study**（2026-05-25 當天再次自爆）

R017 寫完幾個鐘頭後同一天，使用者撞 accounts card 沒有 ✎ 編輯按鈕（bank/name 不能改）。這正是 fixed_expenses 有 ✎ 但 accounts 沒 ✎ 的「同類兄弟漏列」——R017 規則 4 明寫「列兄弟清單」我**沒做**，只列了 line 4639 `addCustomSub`（另一個 prompt 漏改點），**沒注意到「能編輯」這個更高層的兄弟關係**。

**規則 4 強化**：列兄弟時，不能只 grep 同字面（如 `prompt(`），還要 grep **概念相同的 UI 元素**：
- 「能 inline 編輯的欄位」→ grep `<input type="text"` `onchange=` `updateXxx`
- 「能整筆編輯的 card」→ grep `openXxxEdit` `data-id` `✎`
- 「能新增的列表」→ grep `addXxx` `+ 新增`
- 「能刪除的 row」→ grep `removeXxx` `deleteXxx` `×` icon button

**動工前的兄弟搜尋 SOP**：教練改任一 CRUD UI 前，先用三個維度 grep：
1. 字面：函式名 / 樣式 class
2. 概念：list-items / edit-modal / row-actions
3. 對應 table：DB 表內每個被 UI 操作的 table，都要過一遍「新增 / 編輯 / 刪除」三 verb 是否一致

漏哪個就在計畫階段標 TODO，不能等使用者撞才修。

**第二次自爆案例（這次）**：R017 v1 vs v2 同一天差距幾小時，證明「ratchet 寫下不代表執行」——規則的價值在每次動工真的 grep，不在文字 elegant。

**v2 補強寫下**：2026-05-25


## R018 — 面向使用者的 default 值不准 hardcode 過去時間 / 過期數字 / 截止值；要嘛動態算，要嘛從 source of truth 讀

**失敗訊號**（2026-05-25）
> 兩起同類事件當天接連發生：
> (a) `<input type="date" id="qt-date" value="2026-05-22">`：seed 那天的日期被寫死當預設值。三天後使用者打開頁面 → 日期欄顯示 5/22（過去日期）→ 若不手動改，每筆記帳都被誤記到 5/22 → 月明細 / KPI 全錯。
> (b) DMR 寫「PID 75051」、「11 帳戶」這類「**寫稿當下的快照數字**」當文字陳述。一週後重開機 PID 變、accounts 數字變，DMR 變成假資訊。

**Harness 層**：
- 工具層（HTML input value 屬性是「初始字面值」，沒「現在時間」概念；要動態填要 JS init）
- 約束層（沒有「default 值不准寫死 timestamp / counter / fast-changing literal」的規則）
- 觀測層（壞掉時靜默；不會跳 error，使用者自己看到才知道）

**永久規則**

1. **任何使用者會看到的 default 值，若會隨時間 / 環境變動，禁止寫死字面值**。違禁清單：
   - `<input type="date" value="YYYY-MM-DD">` 寫死過去日期（除非真的要鎖那天）
   - `<input type="number" value="N">` 寫死「當下計數」（如 PID、帳戶數、未讀數）
   - HTML / config 文字寫死「最新 deploy URL」「最新 commit hash」
   - email 範本寫死「親愛的 [name]」沒帶入機制

2. **正確做法**：
   - 日期 / 時間 → JS 在 init 用 `new Date().toISOString().slice(0,10)` 填
   - 計數 / 狀態 → 從 single source of truth 動態查（API / DB / file）
   - URL / hash → 部署 pipeline 動態注入
   - 範本變數 → 走 template engine

3. **DMR / SOP 寫作規則**：
   - **快照數字一定要標日期**（「accounts 11 筆 @ 2026-05-22」）
   - **PID / port / URL** 寫「最後一次驗證時」+「怎麼重查」（`launchctl list \| grep family-finance`）
   - **「現在狀態」陳述**改寫成「**這樣查可知**」的指令

4. 教練 ON 看到 HTML / config / SOP 出現「過去日期 / 寫死計數」立刻問：
   「這是動態的還是靜態的？是動態的為何寫死？是靜態的，那 1 年後還對嗎？」
   答不出來就要改成動態。

**已驗證事實**：本次 qt-date 改用 `setQtDateToToday()` 三點 trigger（init / showPage('quick') / recordTransaction 後）；DMR 已有部分採「快照 + 怎麼重查」格式（如「PID 75051 跑著」明天就過期，已標「2026-05-22」）。

**第一次寫下**：2026-05-25


## R019 — 部署到公開 URL 前必須 audit「新瀏覽器首訪」行為：無 localStorage / 無 cookie / 無 cache 的 cold start 流程不能爛

**失敗訊號**（2026-05-25）
> 家庭財務 UI 從 localhost 部署到 Cloudflare Pages。本機 Mac 開沒問題（localStorage 已存 `sb_config`）。**手機 Safari 第一次開 pages.dev → 跳「雲端同步設定」modal 要使用者填 Project URL + Publishable key**。使用者誤以為要再註冊一次 Supabase（看到 step1 文字「到 supabase.com 註冊免費帳號」），實際只是 localStorage 空。
>
> R015 grep 沒抓到這個「跨裝置 cold start」類型，因為這是「部署 + UX」交界，不在傳統 ratchet 範圍。

**Harness 層**：
- 工具層（localStorage / cookie 是 client-side，部署不會同步；單機 dogfooding 跟公開部署是兩個 UX）
- 觀測層（dev 自己一直用同個 browser 看不到 cold start UX，bug 累積到陌生人 / 新裝置才暴露）
- 約束層（沒有「部署前必跑 cold start checklist」規則）

**永久規則**

1. **部署到公開 URL 前**（不論 first deploy 或 redeploy 改 UX），必須跑以下 cold start audit：
   - **無痕模式打開** URL 看首訪流程（沒 localStorage / cookie / cache）
   - **不同 device** 測（手機 Safari / 朋友的電腦 / iPhone Simulator）
   - 確認所有「必要設定」走 hardcode default + 環境變數注入，**不能依賴使用者本機 localStorage**
   - 確認 modal / setup wizard 只在「**真的需要使用者輸入**」時跳，不該為「設定值空」就跳

2. **常見要 audit 的 cold start 來源**：
   - 後端 API URL / key → hardcode default 進前端（public 的 OK，secret 走後端 proxy）
   - 使用者偏好（dark mode、語言）→ 用 prefers-color-scheme / browser language fallback
   - 上次選擇（filter、tab）→ default 要合理，不假設使用者「上次有選過」
   - Onboarding 進度 → 第一次來預期看到什麼，不能假設「他已經做過 step 1」

3. **R013 對應**：cold start hardcode default 要區分「**設計上可公開**」vs「**secret**」。前者 hardcode、後者用環境變數 / 後端 proxy。
   - Supabase publishable key / anon key → 可 hardcode（RLS 保護）
   - Supabase service_role / secret key → 絕不 hardcode

4. **dogfooding 階段防禦法**：每週固定 1 次用「新無痕 window」開自己 app，模擬陌生人 cold start。

**已驗證事實**：本次把 SB.DEFAULT_CONFIG hardcode `vbhfonambtsnfzitquai.supabase.co` + `sb_publishable_Kdto8oPwoYq4KkIs98LtWg_AdAm0Ykk` 進 HTML，commit e71e749 推到 Cloudflare Pages → 手機 cold start 不再跳設定 modal，直接看到登入按鈕。

**第一次寫下**：2026-05-25


## R020 — 第三方服務 SOP 寫「目標狀態」+「視覺特徵」，不寫死「按鈕第幾個」「Step 2 點藍色」

**失敗訊號**（2026-05-25）
> 給 Balian 寫 `SOP_Cloudflare_Pages_部署_2026-05-25.md`，照 2026 年 5 月當下 Cloudflare Dashboard UI 寫「Create application → Pages tab → ...」。**使用者操作時 Cloudflare 已改版**：主入口從「Create application」變成「Create a Worker / Ship something new」（Workers 為主），Pages 變成下方小字 link「Looking to deploy Pages? Get started」。使用者照 SOP 找不到「Pages tab」卡住。
>
> 同類事件第 2 起：Cloudflare 把建 Pages 流程隱藏在 Workers 介面下方 link，新使用者點 Workers 入口會撞到付費 Containers 等不相關功能（截圖確認使用者誤點到 Containers 看到「Purchase Workers Paid」）。

**Harness 層**：
- 工具層（第三方 Web Dashboard UI 經常改版，沒 stable API；SOP 寫死按鈕路徑會過期）
- 約束層（沒有「SOP 寫法防腐」規則）
- 觀測層（SOP 過期沒人主動發現，要等使用者撞到才被動修）

**永久規則**

1. **第三方 SOP 必寫的 3 件事**（依序）：
   - **(a) 目標狀態**：完成後應該看到 / 拿到什麼（URL、token、settings 狀態）— 這是不變的
   - **(b) 視覺特徵**：關鍵頁面的識別特徵（「綠色 Create 按鈕」「左側 nav 含 Workers & Pages」），不寫「上方第 3 個 tab」這種位置依賴
   - **(c) Fallback 路徑**：「如果找不到 X，嘗試搜尋框打 'pages' / 點下方 'Get started' link / 開 https://dash.xxx.com/?to=...」

2. **禁止寫法**：
   - ❌「點上方 Create application 按鈕」（位置不穩 + 名字改了）
   - ❌「Step 2 點藍色繼續」（顏色 / 順序都會變）
   - ❌「左側 nav 第 3 項」（順序隨產品更動）

3. **建議寫法**：
   - ✓「找名稱含 'Pages' / 'Create' 的入口」
   - ✓「上 URL 直達：https://dash.cloudflare.com/?to=/:account/workers-and-pages/create/pages」
   - ✓「目標：拿到 \*.pages.dev URL；無論你走 Web UI 哪條路徑，看到 URL 就成功」

4. **SOP 標頭加版本警語**：「Cloudflare UI 經常改版，本 SOP 寫於 YYYY-MM-DD，按鈕名稱可能變。認結果不認名稱。」

5. 教練 ON 看到 SOP 寫「點上方 X」「Step N 紅色按鈕」之類「位置 / 顏色 / 序號」依賴的指令，立刻問「6 個月後這 SOP 還對嗎？」答不出來就改寫。

**已驗證事實**：本次 SOP 已過期被撞 2 次（Step 2 卡關 + 誤點 Containers）。後續 deploy 完成是靠教練即時手把手帶 + 拿到截圖才能繼續，**SOP 本身價值打 5 折**。下次寫類似 SOP 套 R020 規則。

**第一次寫下**：2026-05-25


---

## R021 — Web-facing endpoint 密碼必須無語意、20+ 字元；教練擋 3 次後強制二選一

**失敗訊號**（2026-05-26，五金通 ERP 部署 Step 3）
> 設 Apps Script Web App 的 DASHBOARD_KEY 時，Balian 連續 3 次手打弱密碼：
> 1. `benjamin2713`（12 字、含 Benjamin 系統公開暱稱、可能生日）
> 2. `Benny172713`（11 字、含「Benny」暱稱+疑似日期）
> 3. `BennyCenny771122`（16 字、雙暱稱+疑似日期）
> 而他本來選了 (1)「接收教練產的 32 字元亂碼」，但每次都自己手打覆寫。直到第三次強制「二選一」（接受教練產的 / 簽切結書承擔風險）才接受 `vkpHbAyauCW5NpEqKtzm1vp543MWwafj`。

**Harness 層**：約束層 + 規則層
- 約束層：沒有「弱密碼擋線」規則，使用者反覆繞過
- 規則層：教練接受「我自己想一個」就放行，沒有自動強度檢查

**永久規則**

當任務涉及「對外端點 / Sheets key / API token / DASHBOARD_KEY / Admin password」密碼設定時：

1. **教練預設要求**：
   - ≥20 字元
   - 含大小寫+數字（特殊字元 optional，避 URL escape 風險）
   - 來自密碼產生器（`openssl rand -base64 24 | tr -d '=' | tr '/+' 'Xx'`）

2. **黑名單**（包含任一即拒）：
   - 本人姓名/暱稱：balian, benjamin, benny, bw, qbar, 彥皓, 小九
   - 已知品牌名：五金通, hardware-erp, family-finance, war-room, qianshao, video2slides
   - 生日/紀念日格式：yymmdd, yyyymmdd, mmdd, yyyy 連續 4 位
   - 鍵盤連續：123456, qwerty, password

3. **升級流程**：
   - 第 1 次擋：「不及格、原因 + 建議改」
   - 第 2 次擋（含同樣黑名單元素）：「我擋。給你兩條路：A 接受亂碼 / B 自己用密碼產生器」
   - 第 3 次違反：**不再給第四次**，強制 AskUserQuestion 二選一「接受亂碼 / 簽切結書（寫入 failures 待補 SaaS 上線前必補清單）」

4. **密碼產出後強制順序**：
   - **先存密碼管理器**（1Password / Bitwarden / Keychain）
   - 確認存好（口頭或截圖確認）
   - **才**貼到目標系統的指令碼屬性 / 環境變數欄位
   - 紀錄文件**禁止寫明碼**，寫「已存密碼管理器，名稱 XXX」

5. **教練回應模板**：
   > 「不接受。`Benny172713` 含你暱稱 + 疑似生日。任何看過你 Benjamin 系統公開資訊的人字典攻擊前 10 組就破。要嘛接受我產的 `<亂碼>`、要嘛簽切結書。」

**第一次寫下**：2026-05-26

---

## R022 — 教練給「留空 / 暫空」指令必須具體化、避免被誤填字面

**失敗訊號**（2026-05-26，五金通 ERP 部署 Step 3）
> 教練寫「ADMIN_UID 留空（Step 5 才填，但 key 先建好）」
> Balian 把「留空」**兩個中文字當 value 填進指令碼屬性**。三個 key 都填了字面「留空」。
> 結果：
> - `CONFIG.ADMIN_LINE_UID = "留空"`（truthy 字串、推訊息給 UID="留空" 會 LINE API 400）
> - `CONFIG.LIFF_ORDER_URL = "留空"`（客戶點下單會跳 URL "留空" 404）
> - `CONFIG.DRIVE_FOLDER_ID = "留空"`（dailyBackup throw exception）
>
> 而且後來才發現 Apps Script GUI **不允許空字串 value**（會跳「這是必填欄位」紅字），所以「留空」的標準動作不該是「填空字串」，而是「不建這個 key」。

**Harness 層**：規則層（教練語言模糊）+ 觀測層（沒有跨平台 GUI 行為知識庫）

**永久規則**

教練給「value 留空 / 暫空 / 預設 / TBD」這類指令時：

1. **禁用模糊詞**：「(留空)」「(暫空)」「(TBD)」「(預設)」「(可選)」這 5 個詞**禁止單獨出現**作為 value 指示
2. **必須改寫為其中之一**：
   - 「**這欄完全不打字，欄位保持空白**」（適用允許空字串的系統）
   - 「**先不建這個 key**，Step N 拿到值再新增」（適用 Apps Script 這類禁空字串系統）
   - 「**填佔位符 `pending`**，Step N 改值」（適用允許更新但禁空的系統）
3. **平台特性必註明**：「Apps Script 指令碼屬性 / GitHub Secrets / Vercel env vars」這類強制 non-empty 的系統，第一次教學時就標註「禁空字串、用『不建 key』策略」
4. **拷問句**：教練生成「留空」指令前，內檢：「**這欄真的接受空字串嗎？我有驗證過嗎？**」沒驗證過就先說「不確定是否允許空、請看 UI 行為」

**通用法則**：
- 對 GUI 操作的指令必須「畫面文字級別精確」，不可用人類速記
- 「留空 = ?」是教練心智模型，但對使用者來說是 user-facing 訊息，必須翻譯成具體動作

**第一次寫下**：2026-05-26

---

## R023 — Apps Script + LINE Bot 整合：「LINE Verify 失敗」≠「Bot 壞」；真實流量為唯一驗證標準

**失敗訊號**（2026-05-26，五金通 ERP 部署 Step 3.5）
> 部署 Apps Script Web App 為 LINE Webhook、LINE Developers Console 點 Verify 連續失敗：
> - 第 1 次：HTTP 302 Found（誤判為「具有存取權的使用者」設定錯）
> - 第 2 次（v2 升版後）：A timeout occurred when sending a webhook event object
> - 第 3 次（重 Verify）：又 302
>
> 用 curl 直接打才發現：**Apps Script Web App `/exec` 對外 POST 強制 302 redirect 到 `script.googleusercontent.com/macros/echo?user_content_key=...`**，這是 Apps Script sandboxed cross-origin 標準行為、無法繞過。LINE Verify 不 follow redirect 所以永遠 fail。
>
> 但**LINE 真實 webhook delivery（用戶傳訊息 / 加好友）會 follow redirect**，Bot 仍正常運作——Step 5 用手機 LINE 傳「選單」立即收到 Flex 主選單，全鏈通。

**Harness 層**：觀測層（依賴 LINE Verify UI 給的訊號做決策、訊號本身誤導）

**永久規則**

部署 Apps Script Web App 接 LINE Webhook 時：

1. **Verify 按鈕視為「lag indicator」不是「pass indicator」**：
   - Verify 通 → ✅ webhook 一定通（強訊號）
   - Verify 不通 → ⚠️ 可能 webhook 還是通（弱訊號，需真實流量驗證）
   - **永遠不要因為 Verify 失敗就否定整套部署**

2. **真實流量驗證 = done-condition**：
   - 部署 done-condition 必須是「**手機 LINE 傳訊息收到 Bot 回應**」，不是「Verify 通過」
   - 沒做真實流量驗證 = Step 3 不算完成

3. **遇到 302 必跑診斷腳本**（curl 直接打、看 follow redirect 後是不是 200）：
   ```bash
   curl -L -X POST "<WEBHOOK_URL>" -H "Content-Type: application/json" \
     -d '{"events":[]}' --max-time 30 \
     -w "FINAL=%{http_code}\nREDIRECTS=%{num_redirects}\n"
   ```
   - 看到 302 → 405「找不到網頁」是預期 Apps Script 行為，**不是部署 bug**
   - LINE 真實 delivery 用不同 HTTP client 邏輯，不適用 curl 結果

4. **「具有存取權的使用者」鐵則**：
   - 必須選「**任何人 / Anyone**」
   - **絕對不要**選「任何具有 Google 帳號的使用者 / Anyone with Google account」（這才是真的 302 元兇，跟標準 302 redirect 混在一起難分）

5. **替代架構候選**（when Apps Script 真的不能用）：
   - Cloudflare Worker / Pages Functions（無 redirect）
   - Vercel Serverless Function
   - Google Cloud Run / Cloud Functions
   - 但**先不要 over-engineer 跳架構**，Apps Script + LINE 是社群實證的標準組合，先做真實流量驗證

**教練動作**：使用者反覆抱怨「LINE Verify 不通」時，先 curl 看 final code、用真實 LINE 訊息測，再決定是否診斷 Apps Script 設定。**不要因為 Verify 失敗就要求他刪 deployment 重來**。

**第一次寫下**：2026-05-26

---

## R024 — Webhook / API / LIFF 整合的 done-condition 必須涵蓋「真實送出」不只「載入」

**失敗訊號**（2026-05-26，五金通 ERP 部署 Step 6）
> Step 6 5 項驗收清單寫的是：
> - #1 LINE 傳「選單」收到 Flex
> - #2 操作中心新增商品 → 儀表板 +1
> - #3 LIFF 開啟看到商品
> - #4 LINE `/今日業績` 收到統計
> - #5 設定畫面持久化
>
> 5 項**全通**、Step 6 收工。但 Balian 在 LIFF 嘗試「送出訂單」時跳 `user doesn't grant required permissions yet`——**整套 ERP 客戶下單功能壞掉**，這是 SaaS 化 blocking issue，但**沒在 done-condition 內**所以沒被擋。
>
> 驗收清單只測「讀」沒測「寫」。

**Harness 層**：規則層（done-condition 不完整）

**永久規則**

部署涉及 Webhook / API / LIFF / Form / Chat Bot 等「雙向互動」系統時，done-condition 必須**對稱涵蓋讀寫**：

1. **讀端驗證**（必須）：
   - 客戶端能載入資料（商品列表、訂單列表、報表）
   - Webhook 接收訊息
   - 設定畫面正確顯示

2. **寫端驗證**（**絕對必須**、之前漏掉）：
   - 客戶端能**送出**請求並收到成功回應（送出訂單、提交表單、回覆訊息）
   - 寫入後驗證資料真的進 sink（Sheets、DB、Log）
   - 客戶收到「送出成功」通知

3. **常見漏掉的「寫端」**：
   - LIFF `sendMessages()` scope 授權（`chat_message.write`）
   - LIFF 從 external browser 開 vs LINE webview 內開的 API 限制
   - Webhook ack 是否真的被處理（不只回 200）

4. **done-condition 範本**（部署涉及訂單 / 表單系統）：
   - [ ] 客戶端載入（讀）
   - [ ] 客戶端送出 + 收到成功回應（寫）
   - [ ] 後端 sink 確認新資料存在
   - [ ] 管理員後台看得到剛送出的資料

5. **教練動作**：使用者報部署 done 時，拷問「**送出測試做了嗎**」「客戶端送的資料在後端找得到嗎」。沒做就不算 done。

**第一次寫下**：2026-05-26



---

## R025 — LIFF / LINE Login channel 必須 publish 才能讓非 developer 使用；deploy 流程必含 publish 步驟

**失敗訊號**（2026-05-27 五金通 ERP 整頓期 Task #8）
> Balian 用副帳號（模擬家人）點 Bot 下單按鈕進 LIFF，被擋 400 Bad Request：
>
> > This channel is now developing status. User need to have developer role.
>
> 原因：LINE Login channel（五金通 LIFF）建立後預設是 Developing status，**只有列為 developer role 的人能用**。所有非 developer 的 LINE 帳號（包含 admin 自己的副帳號 / 家人 / 任何客戶）都被擋。
>
> 昨晚 Step 4b 流程沒包含 publish 動作、5 項 done-condition 全通但**只用 developer 主帳號測試**、沒撞到這個 dev-status 限制。整套 ERP 部署完、家人來用根本不能用。

**Harness 層**：規則層（部署 done-condition 不完整）+ 觀測層（單一用戶測試假過）

**永久規則**

部署涉及 LIFF / LINE Login channel / OAuth 第三方服務時，done-condition 必須含：

1. **「非 developer 用戶實測」**：
   - 用第二個 LINE 帳號（副帳號 / 家人帳號）走完整使用流程
   - 不可只用「開發者 admin 帳號」過 done-condition
2. **「Channel status 已 Published」確認**：
   - 截圖 channel state 顯示 Published、不是 Developing
   - publish 必填欄位（隱私權政策 / 服務條款 URL）有填
3. **multi-user dogfood 是強制標準動作**：
   - 教練看到部署完只測「自己 admin 帳號」要拷問「家人 / 副帳號測過嗎」
   - 「我自己用得起來」≠「家人用得起來」

**通用法則**：所有「需要 OAuth / 用戶授權」的部署都該套同樣規則——admin role 在 dev status 下會「假過」，必須換非 admin 角色實測。

**第一次寫下**：2026-05-27



---

## R026 — Webhook handler silent fail：失敗路徑必須 reply 給用戶、不准只處理 success

**失敗訊號**（2026-05-27 五金通 ERP Task #8）
> Balian 副帳號從 LIFF 送出訂單，LIFF 端 alert「訂單已送出！」、實際後端 createOrder return `{success: false, message: '尚未綁定客戶資料'}`——但 handleTextMessage 第 728 行只 `if (result.success) replyMessage(...)`，**失敗時 user 收不到任何訊息**。
>
> Balian 看到的「找不到 📝 訂單明細...」是 summary 那條訊息（LIFF 送了兩條）的 searchProducts fallback、不是 ORDER_DATA 的回應。導致他誤以為「LIFF 通了、只是 Bot 回應怪怪的」、實際是「訂單根本沒下成」。

**Harness 層**：規則層（程式碼 pattern）+ 觀測層（silent fail）

**永久規則**

所有 webhook / API / event handler 處理「可能失敗」的業務動作（下單 / 寫入 / 付款 / 推播）時：

1. **if-success-only 是 anti-pattern**：
   ```javascript
   // ❌ 錯
   const result = doSomething();
   if (result.success) replyMessage([...]);

   // ✅ 對
   const result = doSomething();
   if (result.success) {
     replyMessage([success msg]);
   } else {
     replyMessage([{ type: 'text', text: `❌ ${result.message || '操作失敗'}` }]);
   }
   ```

2. **try-catch 不准空 catch**：`catch (e) {}` 吃錯誤 = silent fail，**必須**至少 `logError(...)` 跟 `replyMessage([error msg])` 兩件事都做。

3. **每個 user-triggered 動作都要回 ack 訊息**：成功回成功、失敗回失敗、不可不回。「沒回」=「user 不知道發生什麼」= 不可接受的 UX。

4. **dogfood 規則**：multi-user 測試（R025）+ 涵蓋失敗 case：庫存不足 / 客戶未綁定 / 庫存負數 / API quota 用完，都要實測 reply 訊息正確。

5. **教練拷問模板**：審 webhook 程式碼看到「if (result.success)」沒對應 else 分支 → 立刻擋下要求補 fail 分支。

**通用法則**：「失敗的可見性」比「成功的優雅」更重要。Silent fail 在 dogfood 階段可能假過 1 個 user、SaaS 後是大量客訴。

**第一次寫下**：2026-05-27



---

## R027 — 密碼存進密碼管理器後必須驗證「能取回」、不只「有存」

**失敗訊號**（2026-05-27 五金通 ERP Task #8 後）
> 昨晚 R021 強制 Balian 把 DASHBOARD_KEY `vkpHbAyauCW5NpEqKtzm1vp543MWwafj` 存進密碼管理器、他口頭確認「OK 存了」。但今早需要重連操作中心時、他「太長記不住」、要求教練「例外貼明碼」——意思是**存了沒驗證、實際取回的 friction 比預期高**。
>
> R021 規則只 cover「先存、後貼系統」、沒 cover「之後 1 分鐘內能取回」。執行 gap 暴露。

**Harness 層**：規則層（R021 不完整）+ 觀測層（教練口頭確認「有存」沒實測「能取回」）

**永久規則**

R021 第 4 條（密碼產出後強制順序）擴充：

5. **存好後立刻 dogfood 取回一次**：
   - 關閉密碼管理器
   - **重新打開、搜尋名稱、複製密碼、再次貼回系統欄位確認一致**
   - 這個 round-trip 確認「**密碼管理器條目可被你的 muscle memory 找到**」
   - 不做 round-trip = 沒存

6. **教練動作**：產密碼給 Balian 後、不只要他「貼進系統」+「存進管理器」、必須要他**重新開管理器找回密碼貼一次**。三步走才算 R021 完成。

7. **「例外貼明碼」永遠不准**：
   - 教練不接受「今次例外、之後我再存」
   - Friction 是規則設計的一部分、繞過 = 規則崩壞
   - 替代：提供「1 分鐘以內找回密碼的 3 條 path」（Keychain Access / 1Password app / 瀏覽器密碼）

**Why 這條重要**：R013 (密鑰不入 repo) + R021 (對外端點密碼必強) 都建立後、實際使用 friction 才是真正考驗。每次「例外」都會變下次的常態。一次例外 = 規則白寫。

**第一次寫下**：2026-05-27



---

## R028 — 主目標逃避偵測：連續多日鑽 internal tool / SaaS 幻想、主目標零進度 = 教練強制拉回

**失敗訊號**（2026-05-29）
> Balian 主目標是「股票戰情室 V1」（目標.md、期限 6/13）。但 5/26-5/29 **連 4 天**全在五金通 ERP（internal tool、給家人用）：
> - 5/26 部署
> - 5/27 整頓 + 3 件衍生產出（skill / 心智圖 / PPT）
> - 5/29 又要「拆 UI/後台/Bot 3 個 skill」
>
> 動機自述「為 SaaS 化、未來不同人維護不同層」——但：(1) 他是單人、(2) SaaS 0 市場驗證、(3) 家人 demo 過但沒下第一筆真實訂單（R024 未完成）。M1 半自動下單系統 4 天零進度、期限剩 15 天。
>
> 這是「鑽舒適區（技術熟、成果可見、家人稱讚、不會失敗）逃避困難主目標（永豐 API 真實下單、會失敗、有金錢風險）」的 pattern。

**Harness 層**：規則層（沒有「主目標偏離偵測」擋線）+ 觀測層（沒人追蹤主目標 vs 實際工時分配）

**重複 pattern 證據**：memory 裡 `project_beauty_saas`（美容業 SaaS）+ `finance_family_ui`（家庭財務 SaaS）+ 五金通 ERP（五金 SaaS）= **三個 SaaS 幻想、零個市場驗證**。Balian 有「想像 SaaS 商品化、逃避收斂單一主目標」的反覆 pattern。

**永久規則**

1. **每次 SU briefing 強制報「主目標 vs 實際工時對齊度」**：
   - 主目標期限剩幾天、近 N 天工時花在主目標 vs 其他
   - 主目標**連續 2 天零進度** → 教練紅字警告「你在逃避主目標嗎」

2. **新「SaaS 化 / 模組化 / 重構」需求出現時、教練先問三題**：
   - 真實用戶在哪？（不是「未來可能有人」）
   - 市場驗證過嗎？（付費意願、訪談數據）
   - 主目標進度如何？（落後就不准開新衍生工程）
   - 三題答不出 → 判定過早優化、擋下、寫進「XX 上線必補清單」延後

3. **internal tool 的 SaaS 化幻想**：
   - internal tool（給家人/自己用）的 R024 真實使用沒達成前、**禁止**跳 SaaS 模組化
   - 「給家人用」≠「賣給市場」、兩者 done-condition 天差地別

4. **舒適區 vs 困難區辨識**：
   - 當 Balian 反覆做「技術熟 + 成果可見 + 不會失敗」的事、迴避「難 + 會失敗 + 有風險」的主目標
   - 教練直接點破「這讓你舒服、不代表它重要」

5. **教練台詞**：「你連 N 天零進度的主目標、跟你正在鑽的舒適區工程，哪個是你 3 個月前訂目標時真正想要的？」

6. **「知情延後」必須當場綁硬停損（2026-05-29 補）**：
   - Balian 選擇「明知偏離仍做衍生工程」時、教練不再無限擋同一決定，但**強制當場設停損**：(a) 主目標何時回來；(b) 多久零進度就自動觸發重寫目標.md
   - 停損寫進 `目標.md` + 本規則、由 **SU briefing 強制追蹤**，不准放記憶裡讓逃生口安靜溜走
   - 觸發條件到了就**自動執行**（重寫目標.md、承認主目標已變），不再問第 N+1 次

**追蹤中的硬停損**：
- 2026-05-29：第 4 次知情延後做 T.beauty 階段 B。**5/30 SU 必須做 M1**；若 5/30 又跳開 → 強制重寫目標.md。SU briefing 必查此條。

**第一次寫下**：2026-05-29（rule #6 同日補）

---

## R029 — Google Sheet 資料是 untrusted 邊界：餵 render 引擎前的「修前端 vs 修資料」判準

**失敗訊號**（2026-05-29，T.beauty 動態引擎階段 B）
> intake Sheet 餵官網渲染引擎，一個 session 連踩 **3 個資料品質坑**：
> - 電話 `0919...` 被 Sheet 當數字吃掉前導 0（型別，R007 同類）
> - 韋韋老師「7年」填進 cert 欄、years 空（人為填錯位）
> - 店名想改大寫，Balian 第一次改成全形 `Ｔ.beauty`（U+FF34，輸入法全形）、第二次才半形 `T.beauty`
>
> 引擎照單全收渲染 = garbage in garbage out。三個坑都靠**人肉 curl** 才發現，引擎自己沒有任何資料品質訊號。

**Harness 層**：約束層（intake doPost 寫入端零 normalize/validation）+ 觀測層（doGet 回傳無品質自檢、靠人眼）

**永久規則**

1. **Sheet/外部表單資料 = untrusted 邊界**，餵任何 render 引擎前都要當 untrusted 處理，不能假設乾淨。

2. **「修前端 vs 修資料」判準（今天的核心收斂）**：
   - **結構性 / 會反覆的格式問題**（型別吃 0、全形↔半形、前後空白、大小寫慣例）→ 在 **intake 寫入端（doPost）normalize**。單點修、所有租戶受惠、SaaS-correct。
   - **一次性人為錯字 / 欄位錯位** → **修資料（Sheet）**，不碰引擎。引擎不該替租戶猜意圖（例：別自動「首字大寫」，會錯殺真的想小寫的品牌）。
   - 渲染端 normalize 只用在「結構性且暫時沒接 doPost normalize」的過渡（如本次電話補 0）。

3. **動態引擎上線必補（延後清單）**：
   - intake doPost 寫入時 normalize：手機存文字/補 0、全形→半形、trim
   - 渲染引擎加資料自檢：fetch 後關鍵欄位空/格式異常 → `console.warn` + 該欄保留佔位不渲染（別靜默吃 garbage）

**第一次寫下**：2026-05-29

---

## R030 — 資料驅動渲染 SOP：欄位全覆蓋 + 驗證 cache-buster

**失敗訊號**（2026-05-29，T.beauty 階段 B/C）
> 1. **欄位漏接**：階段 B 把「基本資訊」自己框成 5 欄（店名/LINE/電話/IG/FB），但 doGet payload 還有 `address/hours/closedDay/transport` 有真實資料、被靜默漏掉。Balian 後來才發現「地址有誤、沒填入」。
> 2. **驗證假象**：改完用瀏覽器驗證，第一次全 null + 佔位還在，差點誤判「壞掉」去重 debug——其實是**瀏覽器快取**拿到舊 HTML（新 id 不在 DOM）。加 `?v=N` cache-buster 後才正確。

**Harness 層**：規則層（沒有「payload 欄位全覆蓋」檢查）+ 觀測層（本地驗證沒防快取、結果失真）

**永久規則**

1. **接資料源前先列舉 payload 全欄位、逐欄標 render / skip(原因)**：
   - 不准「我覺得基本資訊是這幾欄」就動手。先 `curl` 看完整 JSON、把每個 key 列出來。
   - 每個欄位明確歸類：已渲染 / 故意跳過(空或不展示，註明) / 待做。**有資料卻沒歸類 = 漏接**。
   - 這樣才不會出現「某欄有值但網頁沒顯示」的 silent drop。

2. **本地瀏覽器驗證一律 cache-buster**：
   - 改完 HTML 用 Playwright/瀏覽器驗證時，URL 加 `?v=<timestamp>`（或 hard reload），否則快取讓「壞的看起來好、好的看起來壞」。
   - 驗證得到「全空/全舊」的反常結果，**先懷疑快取**再懷疑程式。

**第一次寫下**：2026-05-29

---

## R031 — 同一交付物多個產生器、底稿分叉：覆蓋式工具是隱形回滾炸彈

**失敗訊號**（2026-05-29，T.beauty）
> 官網 `tbeauty-website.html` 有**兩個來源**：(1) 手動編輯的 `tbeauty-website_1.html`（今天加了動態 fetch 引擎）；(2) `gallery-editor.html` 這支「挑照片→產生網站→覆蓋舊檔」工具，內嵌一份 **base64 底稿（SITE_B64）**。
> 解碼 SITE_B64 發現它是**今天引擎之前的舊快照**（含 @yourid、○○路、寫死假團隊、無 INTAKE_URL）。Balian 差點按「產生並覆蓋」，會把今天整段資料驅動引擎**靜默洗掉**、網站倒退。
> 危險點：base64 編碼讓人**肉眼/grep 看不出底稿版本**，分叉完全隱形。

**Harness 層**：Filesystem/Git 層（同一產物多源、無單一真實來源、無版控可回溯）+ 觀測層（底稿編碼後不可見、分叉無告警）

**永久規則**

1. **一個交付物只能有一個權威來源**。任何「產生 X → 覆蓋舊檔」的工具，其內嵌底稿一旦和手改檔分叉，就是回滾炸彈。
2. **覆蓋式產生器用前先驗底稿版本**：產出前 diff 底稿 vs 現行檔（編碼底稿先解碼再比）。底稿落後就**先更新底稿、再產生**，否則禁用。
3. **這類「散落檔 + 多產生器」正是 Task #17 git 版控要解的**：產物進 git，產生器改的是「會 commit、能 diff、能 revert」的檔，分叉立刻看得到。
4. **編輯器/產生器內嵌底稿 = 技術債**：理想是產生器吃「當前權威檔」當輸入（或共用同一 source），而不是抱一份會過期的 base64 拷貝。

**第一次寫下**：2026-05-29

## R032 — RWD/UI 驗收：「不破版」≠「可用」，且必過真機 + 多狀態

**失敗訊號**（2026-06-08，家庭財務 UI RWD+PWA）
> 我做完手機 RWD，用 Playwright 390px 量每頁 `documentElement.scrollWidth - innerWidth`，八頁全 ≤0 → 宣稱「八分頁不破版」蓋章部署。
> Balian 真機一開就抓到三個我漏掉的：(1) 快速記帳「金額」輸入框被同列日期欄的 min-content 擠成一條（頁面沒橫向溢出，但欄位不可用）；(2) iOS Safari 抽屜 `height:100vh` 被瀏覽器底部工具列蓋住，**捲不到最底的登入/連線狀態區**；(3) 固定收支頁登入資料沒及時 render → **整片空白且無任何提示**，使用者以為「資料不見了」（其實雲端 15 筆都在）。
> 共通病根：我只驗了「頁面層級不橫向破版」這**一個**量化指標，沒驗「每個欄位是否可用」「真機瀏覽器 chrome 行為（100vh/safe-area）」「登入/登出/空資料各狀態」。

**Harness 層**：觀測層（驗收指標太窄、模擬視窗 ≠ 真機）+ 執行層（資料驅動頁無空狀態 fallback，失敗時靜默空白）

**永久規則**

1. **`scrollWidth` 不橫向溢出只是「最低標」，不是「可用」**。每個互動元件還要驗：輸入框寬度夠填、按鈕可點、文字不疊、欄位沒被 sibling 的 min-content 壓扁（grid `1fr` 會縮到 min-content，窄欄+寬欄同列必爆）。
2. **手機驗收必含「真機 or 模擬真機 chrome」**：`100vh` 在 iOS 會被工具列吃掉 → 全螢幕容器一律用 `100dvh` + `padding: env(safe-area-inset-*)`。純 Playwright 視窗測不出這個，交付前要嘛真機過一遍、要嘛明說「此項只模擬、未真機驗」。
3. **資料驅動的頁永遠要有空狀態 / 未連線狀態 fallback**：render 失敗、無資料、未登入都要顯示**文字提示**，禁止靜默空白（空白會被當成「壞了/資料不見」）。靜態 demo 一旦停用，務必補等效的空狀態。
4. **render 時機別只賭「初次連線那一次」**：資料頁改用 render-on-navigate（每次切到該頁重新載入渲染），避免連線時序/單次失敗造成永久空白。
5. **done-condition 寫「不破版」時，要同時寫「可用 + 真機 + 哪些狀態」**，否則驗收會被窄指標蒙混過關。

**第一次寫下**：2026-06-08


## R033 — macOS bash 3.2：`$VAR` 後緊貼全形字元會把變數吃成空字串

**失敗訊號**：deploy_finance.sh 連續 4 次部署的 commit message 全變成亂碼「¼¼」，git 警告 commit message did not conform to UTF-8。中文描述整段消失，只剩全形括號的殘缺 bytes。

**根因（隔離重現驗證）**：macOS 內建 `/bin/bash` 是 3.2.57（2007 年），multibyte 解析有 bug——`"$DESC（$NEW）"` 這種「變數展開後直接緊貼全形字元」的寫法，bash 會把全形字的首 byte 當成變數名一部分，整個變數展開成空、再吃掉一個 byte。`${DESC}` 加大括號或改用 zsh 都正常。

**定位層**：工具層（shell 腳本）。

**永久規則**：
1. macOS shell 腳本內，**變數展開後面接全形/中文字元時一律用 `${VAR}` 大括號**，禁止 `$VAR中文` 裸寫。
2. 新寫部署/自動化腳本，shebang 優先 `#!/bin/zsh`（macOS 預設殼，無此 bug）；要用 bash 就全程 `${VAR}`。
3. 腳本產出的 commit/訊息含中文時，驗收要包含「git log 實際讀回來一次」，不能只看腳本 echo 的成功訊息（echo 那行恰好沒踩到 bug，看起來一切正常）。

**第一次寫下**：2026-06-11

## R034 — 靜態示範資料殘留：空資料 early-return 讓假資料偽裝成真資料

**失敗訊號**：家庭財務 UI「今日交易」永遠顯示 3 筆寫死的示範交易（麵店午餐/7-11/中油加油），與「本月明細」的雲端真資料對不上，使用者以為是同步壞了（「沒有連動？」）。其中一筆時間 18:15 甚至在截圖當下還沒發生。

**根因**：原型期把示範資料寫死在 HTML markup，render 函式開頭 `if (!txs.length) return;`——雲端今天沒交易就直接 return，示範列永遠不被清掉。資料是真的進雲端了，壞的是渲染端的空狀態處理。

**定位層**：執行層（渲染函式的空狀態分支）。

**永久規則**：
1. **原型轉真品時，寫死的示範資料是負債**：要嘛刪掉、要嘛換成明確的空狀態文案，不准留著當「畫面不會空」的遮羞布。
2. **render 函式對「空資料」必須有明確輸出**（清空＋空狀態訊息），禁止 early-return 留下舊畫面。空陣列是合法狀態，不是錯誤。
3. 驗收資料頁時必測「雲端是空的」情境：空帳號登入看到的必須是空狀態提示，不是任何看起來像真資料的東西。

**第一次寫下**：2026-06-11

## R035 — 半接線表單欄位：UI 收了輸入、寫入時靜默丟棄

**失敗訊號**：快速記帳有帳戶下拉選單，使用者選了「零用現金」記支出，但餘額不動。追查發現 `recordTransaction` 讀了 `qt-account` 的值之後組 payload 時根本沒放進去——交易存進雲端永遠沒有 account_id，帳戶欄位是裝飾品。使用者以為是「連動壞了」，實際是資料從來沒存過。

**根因**：原型期先畫 UI、資料層後補，補的時候漏接欄位。沒有「送出後讀回比對」的驗收，半接線狀態存活了一個月。

**定位層**：執行層（表單→payload 接線）＋觀測層（沒有讀回驗證）。

**永久規則**：
1. **表單上每個看得到的輸入欄位，必須能追到資料庫欄位**；接不到的欄位不准上 UI（半接線比沒有更糟——使用者以為存了）。
2. 表單功能驗收必含「送出 → 從 DB 讀回 → 逐欄比對」，不能只看成功 toast。
3. 新增「資料連動」類功能（A 表寫入要動 B 表）時，CRUD 三路徑（新增/編輯/刪除）都要處理反向回沖，缺一路就會漂移。

**第一次寫下**：2026-06-11

## R036 — 雙寫系統靜默降級：次要目的地斷線一個月沒人發現

**失敗訊號**：DMR 雙寫（CSV + Google Sheet）的 OAuth token 約 5 月中失效，之後每筆 log 都印「⚠ Sheet 同步失敗，僅寫本機 CSV」然後照樣回報「已寫入」。13 筆記錄只進 CSV，Sheet 停在一個月前，直到 2026-06-11 重授權比對才發現。

**根因**：降級路徑做得太順——警告印了但沒有人盯 stderr，主訊息「已寫入 row_id=N」看起來像完全成功。沒有未同步計數、沒有例行比對，degraded 狀態就無限期存活。

**定位層**：觀測層（降級無累積追蹤）＋ Memory 層（跨 session 沒有「Sheet 斷線中」的狀態傳遞）。

**永久規則**：
1. **雙寫失敗不是警告是欠帳**：降級寫入後，每次 SU 上工 briefing 必跑「CSV 列數 vs Sheet 列數」比對，不一致立即補同步（比對腳本見本條附錄）。
2. Google OAuth refresh token（測試模式 7 天）/PAT 這類會過期的憑證，失效當下就重授權，不准「先 CSV 擋著」跨 session。
3. 任何「主成功＋副失敗」的混合結果，回報時失敗要放最前面，不准埋在成功訊息後面。

**附錄**：補同步 one-liner——讀 Sheet A 欄 row_id 集合，diff CSV，缺的 `dmr.append_sheet()` 補上（2026-06-11 實際用過，13 筆一次補齊）。

**第一次寫下**：2026-06-11

## R037 — UI 選項與 DB CHECK 約束分叉＋前端吞錯＝「畫面說成功、資料沒進去」

**失敗訊號**：帳戶總覽新增「不動產」帳戶，toast 顯示「✓ 已新增」，但列表永遠是「尚無不動產帳戶」。查 DB：`accounts_type_check` 約束只允許 cash/credit/invest/other——UI 後來加了 real_estate 分類，schema 沒跟著遷移，insert 被約束擋掉。而 `saveAccount` 不檢查 error、`commitAccount` 不管結果一律 toast 成功，錯誤被雙層吞掉。

**根因**：(1) 前端加新枚舉值時沒檢查 DB CHECK 約束是否同步（UI 與 schema 兩個真相源分叉）；(2) 寫入函式吞 error ＋呼叫端樂觀回報。

**定位層**：執行層（schema 遷移缺漏）＋觀測層（錯誤靜默）。

**永久規則**：
1. **UI 新增任何枚舉選項（type/category/status）時，必查對應欄位的 DB CHECK 約束**，要加值就出 migration 檔（vN 累計，依 feedback_spec_versioning）。
2. **所有 Supabase 寫入必檢查 `error` 並 alert**；呼叫端必檢查回傳值，存敗不准 toast 成功。本檔已修 saveAccount，其餘寫入函式下次動到該區時逐一補。
3. 驗收新分類功能時，必實際送出一筆＋讀回確認（R035 規則 2 的枚舉版）。

**第一次寫下**：2026-06-11

## R038 — GitHub 使用安全守則（2026-07-06 整理）

**背景**：開始把專案推上 GitHub（tbeauty-mgmt），第一次正式使用 GitHub 管理商業專案，整理必知風險規則。

**永久規則**：

1. **新 repo 預設 Private**：商業邏輯、客戶資料、API 串接、自動化腳本一律建成 Private。只有確認要開源分享才改 Public。

2. **金鑰/密碼絕不寫進 code**：所有 API Key、DB 連線字串、密碼一律放 `.env` 檔，並確認 `.env` 已加進 `.gitignore`。就算 Private repo 也不能 hardcode（日後可能邀請協作者或轉 Public）。

3. **禁止 `git push --force` 未確認**：force push 抹掉雲端歷史，不可逆。教練遇到此指令必擋下確認。（CLAUDE.md 已有此規則，此處雙重保險）

4. **GitHub 帳號開 2FA**：避免帳號被盜後損失程式碼與信譽。

5. **商業專案不混用 GPL 授權的開源程式碼**：GPL 有傳染性，商業專案必須用 MIT/Apache 授權的套件。

6. **每個新專案 `.gitignore` 必覆蓋**：`.env`、`*.db`、`node_modules/`、`.DS_Store`、`prisma/dev.db*`。

**第一次寫下**：2026-07-06

## R039 — 診斷層寫死假數字冒充真實診斷：財務顧問工具的最高風險

**失敗訊號**：家庭財務 UI 記帳/帳戶資料流是真的（連 Supabase、會存會扣），但拿來當賣點的「財務診斷」全是寫死假數字，跨 5 個頁面：(a) 人生財務羅盤——「緊急金 8.2 月/壽險缺口 892 萬/退休金 0」是 `STAGES` 陣列固定字串，不管誰登入都同一組；(b) 理財目標可行性——`actual = name.includes('教育')?14500:0`、`disposable=47350` 寫死，達不達得成用假前提算；(c) 每月儀表板 KPI 卡 + sidebar——`$87,650/$47,350` 寫死，未連線也不清成 ——；(d) 年度體檢報告——整份淨值/缺口寫死，還設計成可列印交客戶；(e) 退休缺口表——壽險 892 萬跟真實計算的退休缺口混同一張表，看起來像算出來的。

**根因**：原型期為了畫面好看，把「診斷結果」寫死當 demo。後續一路補記帳/帳戶的真實資料流，但沒回頭把診斷層接上真資料——診斷層與資料層從沒接通。比 R034 更嚴重：R034 是空狀態殘留假資料，這裡是**運算/建議結果**本身造假，且在會影響財務決策的工具裡。

**定位層**：指令層（產品定義沒把「診斷必須源自真實資料」寫成紅線）+ 執行層（render 直接吐寫死字串）。

**永久規則**：
1. **任何「看起來像算出來的數字」必須真的算出來，否則標「待評估」，禁止填看似合理的假值**。缺口/百分比/月數/淨值這類診斷值尤其危險——使用者與客戶會當真。
2. **算不出來（缺資料源）就顯示「待評估／需先登錄 X」，不編造具體數字**。半接線（給個假值先擋著）＝ R035 的變種，一律禁止。
3. **可列印/可交付客戶的產出（報告、對照表）若含未接真資料的欄位，必須有明顯警示橫幅**「範例格式，勿直接交付」，直到全欄位接真資料才移除。
4. **財務顧問類工具的驗收紅線**：每個顯示給使用者的財務數字，驗收時必問「這數字從哪張表/哪個輸入算出來？」答不出來就是造假，退回。
5. 未連線狀態下所有 KPI 一律 ——，禁止殘留寫死值（承 R034）。

**第一次寫下**：2026-07-07

## R040 — 連續盲修：沒定位「最後寫入者」就改 code，一個 bug 修三輪

**失敗訊號**：固定收支頁登入後永遠顯示「尚未連線雲端」。第一輪猜「init timing」加 post-init 重刷（v26.19）、第二輪猜「初始化中」加輪詢（v26.20）、第三輪猜「Supabase 冷啟動」放寬 timeout（v26.21）——三輪都沒修好。真因：`refreshFixedList` 用 `window.SB` 判斷連線，但 `SB` 是 `const` 宣告，**`const`/`let` 不掛 `window`，`window.SB` 永遠 undefined**，條件永遠走 else。同 bug 也存在保險矩陣 `refreshInsurance`。

**根因**（兩層）：
1. 技術層：`window.X` guard 只對 `var` / 明確 `window.X =` 賦值有效。對 `const X` 要用 `typeof X !== 'undefined'`。
2. 流程層（真正的病）：**症狀是「畫面顯示某訊息」，卻沒先回答「這訊息是誰寫的、什麼條件下寫」就開始改**。三輪修改都在改「別的可能原因」，沒有一輪先 grep 那行錯誤文案、讀它所在的條件分支。

**定位層**：執行層（guard 條件錯）+ 觀測層（debug 沒從最後寫入者回溯）。

**永久規則**：
1. **畫面顯示錯誤訊息 → 第一步永遠是 grep 該文案字串，找出所有寫入點，讀懂每個寫入點的觸發條件**。沒回答「誰寫的、為什麼寫」之前，禁止提出任何修法。
2. **同一個 bug 第二輪還沒修好 = 停止猜測**，強制回到重現/回溯，不准再堆「可能有幫助」的防禦式修改。每輪盲修都在累積雜訊 code（本案的輪詢、post-init hook 都是多餘產物）。
3. `const`/`let` 頂層宣告不掛 window：跨 script 區塊/早於宣告的防禦判斷一律 `typeof X !== 'undefined'`，禁用 `window.X`。**補充（2026-07-29 踩到）**：`typeof X` 只對「完全未宣告」的名字安全；對「在同一 scope 稍後才宣告的 `const`/`let`」，在其 TDZ 期間連 `typeof X` 都會拋 `Cannot access 'X' before initialization`。所以若某函式可能在 `const X` 宣告行之前被同步呼叫（例如載入期就跑的初始化呼叫），不能靠 `typeof X` 擋——要嘛把該同步呼叫移除/延後到宣告之後，要嘛用 `try/catch`。本次 bug：`renderTrend` 的空資料 guard 引用 `SB`，而載入期的 `renderTrend(60)` 早於 `const SB` 宣告 → TDZ 拋錯。修法：刪掉載入期那次無意義呼叫（改由登入後/切頁時才觸發）。
4. 修完必須用「模擬觸發條件」驗證到症狀消失才算修好（本案：mock user/familyId + stub loadFixed 跑 refreshFixedList），不准「理論上應該好了」就部署。

**第一次寫下**：2026-07-09

## R041 — 真資料 + 錯公式：通過「是不是假數字」檢查的錯誤數字；修好「顯示不出來」等於該頁第一次上線

**失敗訊號**：固定收支表頭「固定月支出 $102,696」，但同頁時間軸逐日加總只有 $62,696，差 $40,000。表頭 `記帳整合UI_原型.html:6554` 把所有未到期固定支出**不分繳費頻率一律以面額相加**——一筆「每年繳 40,000」的保費，在標著「**月**支出」的欄位裡就是 40,000。連帶「月度淨流 −90,696」也錯（7 月實際 −50,696）。

**為什麼前面連續 debug 都沒抓到**（這才是重點，四層獨立失效）：
1. **不是同一個 bug**。R040 修的是「頁面根本不渲染」，這是「渲染出來的數字算錯」，不同 code path。
2. **這個 bug 比 debug 更老，且被前一個 bug 遮住**。v26.23 之前固定收支頁永遠顯示「尚未連線雲端」，表頭從沒帶真資料出現過——沒人看得到的數字不會有人質疑。
3. **R039 的驗收問題擋不住它**。R039 問「這數字從哪張表算出來？」——102,696 答得出來（真的來自 fixed_expenses 真實資料），完美通過。R039 只擋**假造**，不擋**真資料配錯公式/錯單位**。後者更危險：它長得像算出來的，因為它真的是算出來的。
4. **它是被意外發現的**。v26.24 加時間軸，第一次讓「本月固定支出」這個量有了**第二條獨立算法**，兩個數字並排才露餡。在那之前沒有任何對照物。而 v26.24 的驗證只驗結構（有沒有時間軸、到期項目有沒有排除、年繳有沒有掛上去），**沒有一條驗數字對不對帳**；更糟的是 mock 測資裡那筆年繳（牌照稅 due_day=715）剛好落在 7 月，等於自己挑了一組不會戳破功能的測資。

**定位層**：約束層（R039 驗收準則太窄，只覆蓋造假不覆蓋錯算）+ 觀測層（同一個量的兩條路徑之間沒有對帳不變式，錯了也安靜）。

**永久規則**：
1. **同一個量在畫面上出現兩次以上（表頭總計 vs 明細清單、KPI vs 分頁、摘要 vs 報表）→ 必須對帳**。新增任何彙總或明細視圖時，第一件事是把它跟畫面上既有的同義數字相減，差額不為 0 就是 bug，不准「兩個都留著讓使用者自己判斷」。
2. **R039 驗收問題升級為兩問**：①「這數字從哪張表算出來？」②「**算式的單位/週期跟它的標籤一致嗎？**」標籤寫「月」就不准混入年繳/季繳面額；寫「本月」就不准含跨月項目。單位錯誤是財務工具最隱形的錯。
3. **測資要挑會戳破功能的 case，不是證明功能會動的 case**。年繳項目的測資必須放在**非當月**，季繳放在非當季，到期項目放在剛好過期的邊界。測資選得讓 assertion 全綠 = 沒測。
4. **修好「該頁根本顯示不出來」類 bug 之後，該頁等同第一次上線，必須整頁重新驗收內容正確性**。理由：顯示不出來的期間 = 從沒被任何人驗過。不准因為「這次只是修顯示層」就跳過。

**第一次寫下**：2026-07-22

## R042 — DMR 收尾斷點：log 勤快、mark-done 荒廢，效益儀表板長期空帳

**失敗訊號**：2026-07-23 核對 `dmr.py list-pending`，20 筆 DMR 卡在待確認，最舊 #5（2026-05-14）積到 #39（2026-07-19），橫跨兩個多月。`briefing-json` 顯示整個 DMR 期間 `verified_total` 只有 **5**（log 了近 40 筆）。而這 20 筆裡一大半括號原本就寫「已部署 vXX / Step1-6 全通 / 9人驗證閘 10/10 全過 / Playwright round-trip 過」——**工作做完了,只是沒回來蓋章**。連帶 `last_workday` 卡在 2026-06-07（briefing 抓最後蓋章日),每天上工看到的都是六週前的舊臉,更不想看 → 更不蓋 → 惡性循環。

**定位層**：觀測層 + 約束層。`log`（主動、有成就感）Balian 會做，`mark-done`（收尾、無聊）不做。**成功太安靜**——不蓋章沒有任何提醒或代價，於是永遠不蓋。效益儀表板（R009，只認 mark-done）因此長期空帳，等於兩個月交付在帳面上蒸發。

**harness 修正**：新增 `~/.claude/hooks/su-checkpoint.sh`（掛 UserPromptSubmit，與 coach-mode.sh 並列）。偵測 prompt 以「上工／SU」起頭 → 注入當前 pending 清單 + 硬指令,要求「在使用者開始任何新工作前,先逐筆帶他 mark-done／跳過／砍掉,清到 < 5 才進今天的工作」。把收尾從「靠自律」改成「開工關卡」。

**永久規則**：
1. **上工第一件事是清昨天的帳,不是開今天的工**。教練 ON 時,「上工/SU」被 hook 攔截後,不得略過 pending 逐筆處理直接進新任務。
2. **done-condition（本習慣的驗收）**：pending 佇列維持 < 5；當週 log 的當週蓋掉。「有跑 SU」不算,「佇列清得掉」才算習慣養成。
3. **主動動作有成就感、收尾動作無聊 → 收尾必須用 hook/關卡強制,不能靠意志**。任何「勤於產出、疏於結案」的流程（不只 DMR）都適用:把無聊的收尾綁進一個每次都會經過的關卡。

**第一次寫下**：2026-07-23

---

## R043 — 外部 API 暫時性錯誤（503/429）沒退避重試：一次過載炸掉整條 pipeline，前面幾分鐘白跑

**失敗訊號**：2026-07-25 用 video2slides 轉 nschool 影片。前面「下載影片→抽音訊→語音轉文字」跑了 4m15s 全部成功，卡在「AI 內容分析」步驟直接判死，錯誤 `503 UNAVAILABLE. This model is currently experiencing high demand`。這是 Gemini 伺服器端暫時性過載，非程式 bug，但 `content_analyzer.py` 的兩個 `generate_content` 呼叫**完全沒有 retry**——Gemini 偶發一次 503，整個 job 作廢，使用者要從頭重跑（重下載、重轉錄再 4 分鐘）。

**定位層**：執行層。長 pipeline 依賴外部 API，卻把「暫時性錯誤」當「永久失敗」處理。單點的暫時性抖動被放大成整條鏈的失敗，且成本非線性——越後面的步驟失敗，浪費掉的前置工越多。

**harness 修正**：`content_analyzer.py` + `knowledge_exporter.py` 加 `_generate()` 退避重試 wrapper。捕捉 `google.genai.errors.APIError`，只對暫時性 code `{429, 500, 503}` 退避重試（延遲 `[2, 5, 10]` 秒，共 3 次），非暫時性（如 400）立即拋出不浪費重試。重試時 print 到 stderr（可觀測，不靜默）。knowledge_exporter 保留原本 `try/except` 降級「其他」的既有語意（重試耗盡才降級，不炸 job）。已用 mock 驗證三情境：前兩次 503→第三次成功、一直 503→耗盡後拋出、400→立即拋不重試。

**永久規則**：
1. **任何呼叫外部 API 的步驟,對暫時性錯誤（HTTP 429/500/503、timeout、connection reset）必須退避重試,不得讓單次抖動炸掉整個任務**。尤其在多步驟 pipeline 裡,越後段的呼叫越要有重試,因為失敗成本 = 前面所有已完成步驟的浪費。
2. **重試要能被觀察**：每次重試印一行（哪個 code、等多久、第幾次），不准靜默 sleep。成功安靜、重試留痕、耗盡大聲拋出。
3. **只重試暫時性錯誤**：4xx 用戶端錯誤（400 參數錯、401/403 授權錯、404）立即失敗,重試只會拖延並掩蓋真 bug。區分「該重試的」與「該立刻炸的」。

**第一次寫下**：2026-07-25

---

## R044 — 憑證/服務靜默過期無告警 + 驗收只驗「沒報錯」沒驗「真實使用」：兩個交界洞

**失敗訊號**：2026-07-25~27 修 video2slides + share 一連串失敗，全是同兩類洞的變形：
- **憑證/服務過期沒有任何告警,要用才發現**：Cloudflare quick tunnel URL 過期（video2slides Failed to fetch）、Railway 後端 Application not found（share + tunnel 自癒同時掛）、Google OAuth refresh token 失效（invalid_grant,token.json 停在 5/23 兩個月沒人發現）。一個 session 內三個獨立「token/服務死了但系統一聲不吭」。
- **驗收只驗「沒報錯」**：share_local 第一版我用 curl 抓 body 比對字串就報「驗收 PASS、可用」,但實際 Content-Type 是 text/plain,瀏覽器打開是原始碼不是網頁——**字串比對騙過了驗收,真實使用行為沒驗到**。等於謊報可用。

**定位層**：觀測層（過期無告警、成功太安靜）+ 約束層（沒有「驗收必須驗真實使用行為」的硬規則,讓「curl 200 / 字串命中」冒充「功能真的能用」）。

**harness 修正**：
- `slides_generator._get_credentials`：refresh 失敗（RefreshError）不再直接炸,fallback 重新授權 flow;client secrets 不存在給明確錯誤。
- 重新授權時 token.json 驗證改看**檔案時間戳 + 實際 refresh 成功**,不看「有 refresh_token 就以為活」。
- OAuth app 確認在 production 模式（否則測試模式 refresh token 7 天過期,反覆壞）。

**永久規則**：
1. **部署/整合類驗收必須驗「真實使用行為」,不是「沒報錯」**：部署→驗 `Content-Type` + 實際渲染;API→驗回傳結構正確;授權→驗實際呼叫成功。`curl 200`、字串命中、`exit 0` 都只是「沒爆」,不等於「能用」。**把驗收的斷言對準使用者真正會做的動作**。
2. **凡是有過期日的憑證(OAuth token / PAT / tunnel URL / 部署 token),拿到當下就記過期日並排提醒**;到期靜默失效是反覆坑(見 [[reference_supabase_pat]]、[[reference_netlify_share_tool]])。
3. **外部憑證/依賴失效要「大聲且可行動」**:錯誤訊息要說「怎麼修」(跑哪個 reauth、改哪個設定),不是丟原始 `invalid_grant: Bad Request` 讓人猜。
4. 診斷「服務不能用」先分層:本機服務活嗎→對外通道(tunnel/後端)活嗎→憑證有效嗎。三個獨立點,不要抓到第一個就停。

**第一次寫下**：2026-07-27

---

## R044 — Data-driven 系統除錯先分「程式 vs 資料源」；含外部服務的功能沒用真實裝置端到端跑過 = 沒驗

**失敗訊號**：T.beauty 官網「LINE 預約」按鈕，回報「點了沒反應」，直覺判為官網 bug。`curl` 抓靜態 HTML 看到連結是佔位符 `@yourid`，差點誤判成「範本值沒替換」。但用 Playwright 真實瀏覽器渲染後，12 個連結**全部已正確替換**成 intake 資料裡的值——動態引擎運作正常、程式碼零 bug。真正的錯在**源頭資料**：intake 當初填的 LINE 帳號 `@yxs8627k` 根本不是正確的官方帳號（正解 `@fnt4233f`）。而這個錯從上線起就在，因為**漏斗從沒用手機實跑過一次**，沒人點過所以沒人發現。

**四個差點誤判的點**：
1. **`curl` 對 data-driven 頁面會給假象**。curl 不執行 JS，看到的是替換前的佔位符,會把「資料驅動系統」誤讀成「佔位符沒填」。動態渲染的頁面必須用真實瀏覽器（Playwright）渲染後才能判讀。
2. **程式對、資料錯**是 data-driven 架構最典型的 bug 形態。動態引擎忠實地把錯的來源值渲染出來——邏輯層再怎麼查都乾淨，因為錯不在那裡。
3. **改原始碼是錯的修法**：因為 JS 會用 intake 的值覆蓋寫死的 HTML，改死值會被蓋掉、無效。治本點唯一在資料源（Google Sheet 那一格）。
4. **`line.me/R/ti/p/@ID` 是手機 deep link**，桌機點看似「沒反應」。含外部服務跳轉的功能，測試環境（桌機/curl）與真實環境（手機開 app）行為不同,只有真實裝置才現形。

**定位層**：約束層（沒有「上線前佔位符掃描」與「資料源正確性驗收」）+ 觀測層（整條漏斗無端到端實跑，源頭資料錯了也安靜）。

**永久規則**：
1. **Data-driven 頁面除錯，第一步是分兩層：程式邏輯 vs 來源資料**。先確認「渲染出來的錯值，是引擎算錯，還是忠實渲染了錯的來源資料」。判讀動態頁面一律用真實瀏覽器渲染，禁用 `curl` 靜態抓取當結論——curl 看到的是替換前狀態。
2. **含外部服務／跳轉／deep link 的功能（LINE、金流、簡訊、OAuth），驗收必須用目標真實裝置端到端跑一次**。桌機瀏覽器、curl、`localhost` 都不算數。手機功能用手機驗，app 跳轉用真機驗。
3. **上線前掃描範本佔位符**：`@yourid`、`0900-000-000`、`yourid`、`example.com`、`[YOUR-...]` 這類 scaffold 預設值,部署前 grep 一輪確認全被真值取代（或確認動態引擎會覆蓋且已驗證覆蓋成功）。
4. **資料源正確性要獨立驗收，不能因為「程式正確渲染了」就認定資料對**。source 填錯值時系統一片綠燈。對關鍵欄位（聯絡方式、金流帳號、負責人）填入後要人工核對一次真值。

**第一次寫下**：2026-07-26

## R045 — 「工具還沒準備好」是自我延伸的假標準：dogfooding 必然持續挖出真 bug，等挖完才接客＝永遠不接客

**失敗訊號**：2026-07-19 ~ 2026-08-02（M1「7/31 前簽第一個付費顧問客戶」死線已過期 2 天，付費客戶數 0），連續 4+ 輪對話全花在 finance UI 修復上——固定收支繳費時間軸、儀表板去假資料（甜甜圈/CFP 結構比）、月份選擇器改真、現金流 Sankey 標籤跟著切換。每一輪教練問「找誰、什麼時候開口」，使用者都用新發現的一個 bug 把話題接回工具。逼問到底，Balian 承認：**「覺得自己/工具還沒準備好」**——內心標準是「再完美一點才敢拿出去」，所以永遠有下一個 bug/功能可以先修。

**根因**：這些 bug 全部是真的（時間軸缺失、假數字冒充診斷、月份標籤寫死），修復本身沒有錯，R039/R040/R041 每一條都成立。**問題不在單一次修復，在於「dogfooding 本身結構性地保證工具永遠不會顯得夠格」**——認真用工具做真實記帳，一定會不斷發現新的真實缺陷，這條路沒有終點。「等準備好」把 done-condition 偷偷從「有沒有客戶」換成「工具有沒有挑不出毛病」，而後者是使用者自己隨時可以延後的移動標準。目標.md V3 早就寫死紅線「finance UI 現狀已足以接客，缺客戶不缺功能」，但紅線只在**回顧時**擋得住，擋不住**進行中**——每次要修的 bug 個別看都正當，模式只有連續多輪疊加後才看得出來，而當事人在局內時看不出自己在疊加模式。

**定位層**：指令層（目標.md 紅線存在但沒有「進行中」的觸發器）+ 觀測層（沒有機制計數「連續幾輪是工具修復、零輪是客戶推進」並主動打斷）。

**永久規則**：
1. **「工具還沒準備好」禁止當作暫停找客戶的理由**。dogfooding 期間發現的 bug 永遠修不完，這是工具類產品的本質，不是「客戶還不能用」的證據。真正的 done-condition 是目標.md 已鎖定的三條，跟工具完整度無關。
2. **連續 2 輪以上的請求都是工具修復（新功能/bug fix/優化），零輪是客戶推進 → 教練必須主動打斷**，不等使用者自己發現模式。打斷時不追問「這次是否有必要」（因為在局內時每個 bug 都覺得必要），而是直接問「這個修完，下一步是修工具還是找客戶」，用選項逼二選一，不接受第三個「等一下」。
3. **「先準備好再接客」的真正解法不是把工具修到主觀滿意，是設一個跟工具無關的外部客觀觸發器**——具體一個人的名字 + 今天之內開口的時間點。講不出這兩者，「還沒準備好」就是逃避的委婉語，要當場拆穿。
4. **教練自身的失誤記錄**：本次教練問了同一個開放式問題兩輪都被繞過，第三輪才改用 AskUserQuestion 限定選項逼出答案。**開放式問題連續被迴避一次就該換成限定選項**，不要指望對方在迴避模式中會自己選擇誠實回答一個可以繼續閃躲的問題。

**第一次寫下**：2026-08-02

**追加（同日，寫完 R045 後不到一輪就復發）**：教練逼問「講出具體人名+今天開口時間」後，Balian 立刻換了說法再迴避一次：「我自己在使用都沒很順利，這類商品要給人使用，我自己都需要認同」。這是 R045 同一機制的**第二種話術**——把「工具還沒準備好」包裝成「服務可信度需要自我認同」這個聽起來正當的商業原則。**下次再看到類似句型（"我要先...才能..."、"自己都不...怎麼能..."），先不要當作新的正當考量接受，先檢查是不是 R045 換了說法。** 拆解方法：①分清楚「軟體 bug」vs「你本人的專業判斷力」——客戶買的是後者；②若理由是「自己財務也不健康,沒資格教人」，這其實是資歷不是失格（career_path 記憶：正是踩過痛點才轉職理專）；③逼問「順利」的具體有限驗收標準——講不出來就是移動的靶。

**第三種話術（同日再復發）**：教練追問後 Balian 又換一種說法：「因為我自己都沒很清楚自己的定向，還在做調適平衡」+ 開始討論「架構的連貫性在哪裡」。這是把逃避從「工具/服務不夠好」升級成「連我自己的定位都還不清楚」，而解法仍是回頭想架構——**還是在想工具，只是換成想工具的哲學層而非 bug 層**。正確拆解：定位不清楚不是先解決、再去談客戶的前提，是**先跟真人談，才會知道定位在哪**——單靠自己內省想不出定位，第一個真實客戶對話本身就是釐清定位的方法，不是要等定位清楚才能有第一個對話。若又出現「還在想架構/定位/連貫性」這類語言，直接指出：這是為了不用去跟人講話而製造的下一層抽象緩衝，不是新的正當理由。

**第四種形式（同日，教練問「更深的問題是什麼」後立即出現）**：教練停止逼問日期、改問「需要先處理的別的事是什麼」給出開放空間後，Balian 的回應是「我剛剛提出修改的地方去執行」——完全不回應問題本身，直接切回 UI 功能請求，連話術包裝都省了。前三次還有語句在解釋「為什麼」，這次是**沉默轉題**。教練判斷：這不代表問題解決或不重要，反而是逃避強度最高的訊號——連解釋的力氣都不想花。**下次遇到「開放式深層提問後立即被無關技術請求打斷」，教練必須先指出轉題本身，不能順著新請求做下去，且不必逼問到底，只需給對方一個明確二選一：現在談這個，或明確說「現在不想談」——沉默切換不算選項之一。**

## R029 推播失敗必須大聲 —— 2026-08-24

**失敗訊號**：粘小文傳失物照片，群組收不到、她也沒收到回覆。查了很久才找到原因。

**真因**：`export default { async fetch(request, env) }` 少第三個參數 `ctx`，整支 Worker 無法用 `waitUntil`。
LINE webhook 進來後所有工作都要在它斷線前跑完；照片流程（下載 310KB → 寫 KV → 更新 DB → 推群組 → 回覆）
超時被切斷，`wrangler tail` 顯示 `Canceled`，後面的推播和回覆整段沒跑。文字流程夠快所以一直正常。

**為什麼查很久（真正的問題）**：三個觀測性破洞疊在一起，系統對這件事完全失憶——
1. `pushMessage` 和群組推播的錯誤被 try/catch 吃掉，非 2xx 完全無聲
2. 收件記錄只記文字，圖片訊息在系統裡零痕跡（但客服頁宣稱「所有訊息都記一筆」）
3. 沒有查 LINE 額度／狀態的方式，只能瞎猜是不是超額

**harness 層**：觀測層（Observability）。不是執行層 bug，執行層的錯早就發生了，是「看不見」讓它變成謎。

**永久規則**：
- 外部 API 呼叫一律走統一 wrapper，非 2xx 一定留 log（`lineCall()` 印 `LINE_FAIL`）
- 宣稱「全部記錄」的東西要真的全部記錄，漏一種型別就是未來的盲區
- 每個外部服務都要有 diag 端點查配額／狀態（`/diag/line`）
- **Workers 的 fetch handler 一律寫 `(request, env, ctx)`**，webhook 類端點先回 200 再 `waitUntil` 背景處理
- 除錯順序：先看 `wrangler tail` 的請求狀態（Ok / Canceled / Exception），再看應用層 log。`Canceled` ＝ 超時被切，不是程式邏輯錯

## R046 前端編輯只改 DOM、沒寫回資料庫 —— 2026-09-01

**失敗訊號**：審核班表把員工從 A 場域拖到 B 場域，公布後 B 場域沒有那些人。

**真因（兩層，都要修才會好）**：
1. **拖曳只改 DOM，沒持久化。** 公布當下 payload 從 DOM 取值所以第一次是對的（民權店 V0 寫進 30 筆），
   但公布完 `loadReviewSchedule()` 重新從 `shift_preferences` 讀，那張表沒變過 → 畫面跳回原場域。
   之後任一次再公布同場域（沒重拖）只會送它自己的 8 筆，**覆蓋式公布把先前 30 筆蓋掉**。
   版本序列 30→8→6→8 就是證據。
2. **`applyLockState` 用寫死字串覆蓋 `entry.title`**，把渲染時寫入的「原登記在哪」資訊洗掉（R040 最後寫入者再現）。

**harness 層**：執行層（狀態沒持久化）＋ 觀測層（畫面回退無提示，使用者只能猜）。

**永久規則**：
- **任何「編輯後會重新載入」的介面，編輯動作必須當下就持久化**。DOM 狀態不是狀態。
  判準：問「使用者按 F5 之後這個改動還在嗎？」不在就是 bug。
- **覆蓋式寫入（先刪後插）的來源必須是持久化資料，不能是畫面暫存**。覆蓋式公布 + 畫面暫存 = 靜默資料遺失。
- **審核調整不覆寫原始登記**：原登記是員工意願的法定紀錄，調整存 `assigned_*` 欄位，
  查詢一律回 `COALESCE(assigned_x, x)` 當生效值，原值另外回供顯示。
- 排查順序（這次有效）：① 比對 DB 實際資料 vs 畫面 ② 看版本/稽核紀錄的數量變化找覆蓋點
  ③ 才讀 code。**先看資料再看程式**，30→8 這個序列直接指出是覆蓋而非寫入失敗。

## R047 平行 session 的 migration 帳目漂移 —— 2026-09-01

**失敗訊號**：`wrangler d1 migrations apply` 報 `duplicate column name: note`，所有 migration 都跑不了。

**真因**：另一個 session 用 `d1 execute` 直接下 `ALTER TABLE` 加欄位，沒走 migration 流程。
schema 有了但 `d1_migrations` 沒記錄 → wrangler 想重跑 → 撞已存在的欄位。
同時兩個視窗各自建了 `0020_*.sql`（撞號，與 memory 記載的 0007 同樣問題再現）。

**harness 層**：協調層（多 session 共用同一個正式 DB，無互斥）。

**永久規則**：
- **改 schema 一律走 migration 檔，禁止用 `d1 execute` 直接 ALTER 正式庫**。急也不行，急就寫檔再 apply。
- 開新 migration 前先 `ls migrations | tail` 確認號碼；撞號就往後取，不要覆蓋別人的檔。
- 遇到帳目漂移：先用 `pragma_table_info` 確認欄位是否真的存在、資料是否已補齊，
  確認一致後才補登 `d1_migrations`。**先驗證再補帳，不要盲目 INSERT**。

## R048 在正式資料上做覆寫式測試，沒先留存原值 —— 2026-09-08

**失敗訊號**：為了驗證「場域權限有沒有真的生效」，直接改真實員工（小米）的 `worker_venues` 去測，
測完清空還原成「無限制」。但**她原本就有設定**，原值就這樣消失。

**為什麼沒發現**：測試前跑的盤點查詢只印「1 個場域」，沒印是**哪一個**。
輸出摘要化到看不出原值，等於沒有備份。事後只能靠旁證（三個同期新人都是民權店＋她唯一一筆打卡在民權店）推回去。

**harness 層**：執行層（破壞性測試無備份）＋ 觀測層（查詢輸出摘要掉關鍵資訊）。

**永久規則**：
- **要在正式資料上跑覆寫式測試前，先把原值完整讀出來並印在同一段輸出裡**，不是印筆數、不是印摘要，是印可以直接拿去還原的完整值。
- 更好的做法：**先讀原值 → 存成變數 → 測試 → 用變數還原**，一氣呵成寫在同一個腳本裡，不要分兩次執行靠自己記得。
- 盤點類查詢**不要只印數量**。`1 個場域` 沒有還原價值，`['v-one-minquan']` 才有。
  判準：問「這段輸出能不能拿來還原？」不能就是印錯了。
- 能用測試資料就不要用真實資料。這次其實可以建一個假 worker 來測，成本比誤刪低太多。

## R049 跨檔案借用不存在的輔助函式 —— 2026-09-08

**失敗訊號**：管理看板整頁掛掉，`載入失敗：escapeHtml is not defined`。

**真因**：`escapeHtml()` 定義在 `人員個人資料.html`，但我在 `小雞打卡出勤紀錄.html` 裡直接拿來用。
兩個檔案是各自獨立的單頁 HTML，沒有共用 script。

**為什麼拖了兩天才爆**：2026-09-06 寫備品人工結案時就用了，但那兩處都在
「manual_close_at 有值才會執行」的分支裡，當時沒有任何一筆人工結案，程式碼從沒被執行過。
9/8 把同樣寫法用在曠職異常表的**必經渲染路徑**上，才立刻炸開。

**為什麼檢查沒抓到**：`node --check` 只驗語法，`escapeHtml(x)` 語法完全正確。
ReferenceError 是執行期才會發生的。

**harness 層**：執行層（跨檔案假設共用）＋ 觀測層（靜態檢查抓不到、分支未執行所以測不到）。

**永久規則**：
- **在單頁 HTML 專案裡呼叫任何輔助函式前，先 `grep "function <名稱>" <該檔案>` 確認它在同一個檔案裡**。
  不要因為「另一個頁面有」就假設有。
- 新增的程式碼若落在**條件分支**裡（`x ? A : B` 的少數分支、`if (罕見情況)`），
  `node --check` 過了不代表跑得起來。**要用假資料強制走進那條分支跑一次**
  （scratchpad 的 node harness 就是幹這個用的）。
- 定期跑「呼叫了但沒定義」掃描：抽出所有 `name(` 與 `function name`，比對差集。
  這次掃出來的 4 個誤報（註解、`let x = null`、內建函式）可接受，漏掉真的才致命。

## R050 先刪後插 + 沒鎖的送出鈕 = 資料變兩倍 —— 2026-09-08

**失敗訊號**：員工說只送出一次，系統顯示每天兩筆（粘小文逢甲店九月 20 筆變 38 筆）。

**真因（兩個缺陷疊加，缺一不會發生）**：
1. LIFF 送出鈕**沒有 disabled**，手機上很容易連點兩下 → 送出兩個批次請求
2. 批次端點用「先 DELETE 同人同場域同月，再 INSERT」——兩個請求交錯時：
   A 刪完（0 筆）→ B 也刪（還是 0 筆，因為 A 還沒插完）→ A 插 20 筆 → B 插 20 筆 = 40 筆

證據：兩批的 `submitted_at` 是 08:33:42~45 與 08:33:43~46，**交錯重疊**。

**harness 層**：執行層（無冪等保護）＋ 約束層（DB 沒有唯一約束擋）。

**永久規則**：
- **任何「先刪後插」的整批覆寫都是競態溫床**。只要客戶端可能重送，就一定要有 DB 層的唯一約束兜底，
  應用層邏輯擋不住並發。
- **會寫入的按鈕一律在送出期間 disabled，並在 `finally` 解鎖**。不是為了美觀，是為了防重複寫入。
- 防重複要**三層都做**：前端鎖按鈕 → 後端 `INSERT OR IGNORE` → DB 唯一索引。
  只做前端等於沒做（使用者可以重整、可以並發、可以直接打 API）。
- 排查順序：先看 `submitted_at` 的時間分布。**間隔一秒內、範圍交錯 = 重送競態**，
  不是使用者填兩次，不要去問使用者。

## R051 自動選擇覆蓋使用者的手動選擇 —— 2026-09-08

**失敗訊號**：審核班表的月份選了 9 月，畫面立刻跳回 10 月，怎麼選都回不去。

**真因**：`pickReviewMonth()`（自動挑「需要處理的月份」）被放在 `switchScheduleSubTab()` 裡，
但那個函式**同時也是月份切換、場域篩選變動的入口**。使用者每改一次月份就觸發一次自動挑選，
選擇當場被覆蓋。

**第二個缺陷**：自動挑選只認「有登記且有場域未發布」，全部發布完的月份會被跳過，
結果落到一個完全沒資料的月份，畫面顯示「這個月還沒有人登記」——看起來像資料不見了。

**harness 層**：執行層（自動行為與手動操作共用同一個入口）。

**永久規則**：
- **自動選擇只能在「進入畫面」時發生一次，不能在使用者操作後重跑**。
  作法：把自動行為用參數關掉（`switchTab(sub, autoPick)`），只有分頁按鈕帶 true，
  其餘入口一律 false。判準：問「使用者手動改完之後，這段還會再跑嗎？」會就是 bug。
- **自動導向要有 fallback 階梯，不能只認最理想的條件**。
  這次應該是：有待辦的月 → 有資料的月 → 預設月。只認第一層就會跳到空白畫面。
- 空狀態的文案要能區分「真的沒資料」與「你在錯的月份」。

## R052 寫入 0 筆卻回報成功 —— 2026-09-12

**失敗訊號**：許曉菁把 9/12 民權早班換給倪珊如，雙方都收到「換班成功」的推播，
管理看板也記了一筆「公布後異動」——但班表上那格還是許曉菁，曠職提醒也還是會打給她。

**真因**：核准換班時要 `UPDATE shifts SET worker_id = ? WHERE id = ?`，
而 `shift.id` 來自這段：

```js
const shift = (await ...SELECT * FROM shifts WHERE id = ?...) 
  || { work_date, shift_type, venue_id };   // fallback 沒有 id
```

班表重新公布會刪掉舊 shifts 並把 `requester_shift_id` 設成 NULL（migration 0035 為了避開外鍵錯誤），
於是查詢回 null、走 fallback，`WHERE id = undefined` 更新 0 筆。
**D1 不會報錯**，程式照樣往下把狀態標成 approved、照樣推播成功。

**harness 層**：執行層（寫入結果沒有被驗證）＋ 觀測層（失敗完全沒有訊號）。

**永久規則**：
- **每一個 UPDATE / DELETE 都要檢查 `meta.changes`**。SQL 語法正確但條件沒命中，
  SQLite/D1 一律回成功。`changes === 0` 幾乎都是 bug，不是正常狀況——
  要嘛回錯誤，要嘛至少 `console.log` 留訊號，不准靜默往下走。
- **「通知使用者成功」必須排在「確認寫入成功」之後**。順序錯了，
  使用者會拿著成功通知去相信一個沒發生的事實，而且比沒通知更難查。
- **fallback 物件不可以冒充實體**。只拿來做文案的快照就只給文案用，
  別讓它流進 `WHERE id = ?`。作法：實體變數（`shift`）與文案變數（`info`）分開命名，
  實體是 null 就明確中止。
- 外鍵欄位被設成 NULL 的補償路徑要**反查**（日期＋場域＋班別＋原持有人），
  不是造一個假物件繼續跑。清掉 id 的那個 migration 必須配一條「怎麼找回來」的規則。

## R053 宣稱「已部署」但只驗了讀，沒驗寫 —— 2026-09-12

**失敗訊號**：離職閉環在 9/11 部署後回報「已完成」，實際上按下去就是
`{"error":"伺服器錯誤：existing is not defined"}`。**這個功能從上線那天起一次都沒成功過**，
兩天後建 staging 跑冒煙測試才被抓到。

**真因**：當時的驗證只做了兩件事——`node --check` 過、`GET /board/today` 回 200 且有
`resignations` 欄位。但新功能的寫入路徑是 `PUT /workers/:id`，那條**完全沒被呼叫過**。
`existing` 這個變數在 `handleUpdateWorker` 裡從來沒宣告，語法檢查抓不到
（JS 的未定義變數是 runtime 錯誤），讀端點也碰不到。

**harness 層**：觀測層（驗收項目沒覆蓋到改動的路徑）。

**永久規則**：
- **驗收必須打到「這次改動真正會跑到的那一行」**。改了寫入邏輯就要實際寫一次，
  只驗讀端點回 200 等於沒驗。判準：問「如果我把這次新增的程式碼整段刪掉，
  我的驗收還會通過嗎？」會通過就是驗收無效。
- **語法檢查不是驗收**。`node --check` 只保證解析得過，
  未定義變數、打錯的欄位名、不存在的表名全部要到 runtime 才炸。
- **每加一個功能，就在冒煙測試補一條斷言**，不然下次還是靠手點，而手一定會漏。
- 回報完成時要講清楚「驗了什麼、沒驗什麼」，不要用「已部署」代替「已驗證」。

## R054 wrangler 的 named env 會繼承 triggers —— 2026-09-12

**失敗訊號**：staging 環境的 `wrangler.jsonc` 裡刻意不寫 `triggers`，以為這樣就沒有 cron。
部署時噴錯：「This account has reached the Workers Free limit of 5 cron triggers」——
它其實正在幫 staging 掛上跟正式環境一模一樣的兩個排程。

**差點造成的後果**：staging 的排程會跑曠職偵測、提醒推播。
如果當時沒有先做「staging 一律 dry-run」那層攔截，**真的員工會收到來自測試環境的曠職通知**。

**真因**：wrangler 的 named environment 對部分設定採「繼承」語意，
`triggers` 是其中之一。**沒寫 ≠ 沒有，沒寫 = 跟上面一樣。**

**harness 層**：約束層（設定檔的預設值與直覺相反）。

**永久規則**：
- **設定檔裡「不想要的東西」要明確寫成空值，不能靠不寫**。
  staging 必須寫 `"triggers": { "crons": [] }`。
  同理適用所有有繼承語意的設定（env、profile、extends）。
- **危險能力要兩層獨立防護，不能只靠設定**。這次是
  ① 程式碼層 `ENVIRONMENT=staging` 就不送 LINE ② 憑證層 staging 給假 token。
  設定漏了還有程式碼擋，程式碼漏了還有 401 擋。
- **部署腳本的錯誤輸出要看完**，不要只看最後一行有沒有 URL。
  這次的警告夾在「Deployed successfully」後面，滑過去就錯過了。

## R055 寫進 memory 的「禁止」擋不住部署繞道 —— 2026-09-16

**失敗訊號**：memory `project_xiaoji_staging` 明寫「禁止直接 `npx wrangler deploy`，一律走 deploy.sh」，
但 2026-09-16 13:28 與 15:26 正式環境都是直接 `wrangler deploy` 上去的，staging 最後一次部署停在 9/12。
發現時機：要在 deploy.sh 裡加 AI 審查關卡，查 `wrangler deployments list` 才看到。

**後果**：兩次部署都沒跑 staging 冒煙測試。新做的審查關卡掛在 deploy.sh 裡，對這條路完全無效。
另外 `xiaoji-checkin/` 一直沒進 git，deploy.sh 蓋章記的是母 repo HEAD，是假保護。

**harness 層**：Hooks 強制執行層（規則只存在於 memory／文件，沒有機器擋）＋ Filesystem + Git（無版控）。

**永久規則**：
- **「禁止 X」只寫在 memory 或 CLAUDE.md 不算數**。會造成線上後果的禁令，必須有 PreToolUse hook 或腳本關卡擋。
  已補：`.claude/hooks/block_xiaoji_direct_deploy.sh`，在 xiaoji-checkin 範圍內擋 `wrangler deploy` 與遠端 migration，只放行 deploy.sh
- **加任何「部署前關卡」之前，先查最近幾次部署是不是真的走那條路**（`wrangler deployments list` 對照關卡的蓋章時間）。關卡掛在沒人走的路上等於沒做
- **有真實使用者的專案必須有自己的 git**，蓋章／比對基準要指向該專案自己的版本，不能借母 repo

## R056 LIFF 權限第三次沒在上線前驗 —— enjoyclean `/me` 拿不到 ID token —— 2026-09-17

**失敗訊號**：Balian 照「三帳號實測腳本」用手機 LINE 開 `/me`，畫面顯示「LIFF 沒有開 openid 權限，拿不到登入憑證」。
程式判斷路徑（`src/pages/me.js:142-144`）：`liff.init` 成功、`isLoggedIn()` 為真、`getIDToken()` 回 null。
登入成功但沒有 ID token，只會發生在 LIFF app 的 Scope 沒勾 `openid`，或授權同意時還沒有 openid。

**後果**：客戶端「我的設備」整條閉環無法實測。`/partner` 綁定窗口用同一個 ID token，
而且 `partner.js` 沒有檢查 null，會顯示成「登入逾時」誤導——腳本第 3 段會跟著壞，卻看不出是同一個原因。

**這是重複失敗**：R024（LIFF scope `chat_message.write` 沒驗）、R025（LINE Login channel 沒 publish）是同一類——
**LINE 後台設定只存在人腦與文字規則裡，上線前沒有機器檢查**。兩條 ratchet 寫了，換專案照樣再犯，正是 R055 講的「只寫在文件不算數」。

**harness 層**：約束層（外部平台設定沒有 preflight）＋ 觀測層（31 步實測腳本第 0 步沒有「LINE 後台設定核對」，錯誤訊息沒指出要去哪裡修）。

**永久規則**：
- **任何用 LIFF 的專案，實測腳本第 0 步固定是 LINE 後台核對**，逐項打勾才准開始第 1 步：
  Login channel 已 Published／LIFF Scope 含 `openid`＋`profile`（有傳訊息才加 `chat_message.write`）／Login channel 已連結官方帳號／Messaging API 與 Login 同一個 Provider
- **用 ID token 的每個頁面都要檢查 `getIDToken()` 是否為 null**，而且錯誤訊息要寫「去哪裡修」，不是只寫「失敗」
- **待做（有 done-condition 才准動工）**：寫 LIFF preflight 腳本，用 LINE Login channel 的 channel access token 打 LIFF Server API（`GET /liff/v1/apps`）讀出 scope 自動核對，接進部署與實測流程，取代人工打勾

## R057 客戶綁定沒有「確認是誰」也沒有「反悔」—— 輸錯電話就被鎖成別人 —— 2026-09-17

**失敗訊號**：Balian 實測 `/me`，綁定電話時輸入錯的號碼（輸成測試客戶蔡宛爭的電話），
畫面直接顯示「蔡宛爭，目前還沒有登記的設備」。之後再開 `/me` 不會再出現綁定表單，因為
`bindByPhone` 找到這個 LINE 已綁定就直接回 `already`（`src/services/customer-portal.js`）。D1 查證：`test2_cus_1.line_user_id` 已被寫入。

**後果**：
- 使用者無法自己更正，只能請管理者手動改資料庫
- 正式營運時，這就是「外人看到別人家設備」——R 設計時刻意用完整電話防撞號，但沒防「打錯字剛好是別人的號碼」
- 被綁走的那位真客戶，之後用自己的 LINE 綁定會得到 `taken`，也無法自救

**harness 層**：約束層（寫入身分綁定這種不可逆動作前沒有確認步驟）＋ 執行層（沒有解除綁定的路徑，包含後台）。

**永久規則**：
- **任何「把 LINE 綁到某個身分」的動作，寫入前必須先顯示遮罩後的姓名讓本人確認**（例：「你是 蔡○爭 嗎？」），確認才寫入
- **每一種綁定都要同時設計解除路徑**：本人可自行解除，管理者後台也能解除並留痕。只做綁定不做解除，不算做完
- 實測腳本要包含「故意綁錯 → 自己更正」這一步，不能只測正確路徑（同 R024：只測順向等於沒測）

## R058 `wrangler d1 execute --remote --file` 被 Cloudflare 回驗證錯誤 —— 2026-09-17

**失敗訊號**：部署 enjoyclean 前套 migration 0006，`npx wrangler d1 execute enjoyclean --remote --file=./migrations/0006_binding_event.sql`
回 `Authentication error [code: 10000]`，打的是 `/d1/database/<id>/import`。同一個帳號、同一個資料庫，`--command` 查詢與寫入都正常。

**後果**：差一點照 README 寫的指令重試或直接部署程式。程式會寫 `binding_event`，表不存在時綁定會 500。
這次有「先套 migration、確認成功才部署」的順序，才沒出事。

**harness 層**：工具層（`--file` 走匯入 API，wrangler OAuth 權限不涵蓋；README 的部署指令沒有驗證過就寫進文件）＋ 約束層（部署順序只存在對話裡）。

**永久規則**：
- **套遠端 migration 一律用 `--command`**（把 SQL 檔去掉註解後傳入），不用 `--file`；執行後立刻用 `sqlite_master` 查表確認存在，確認完才准部署程式
- **有 migration 的部署，順序固定：migration → 查表確認 → deploy → 線上冒煙**。任何一步失敗就停，不准跳過去部署
- enjoyclean README 的 `--file` 指令要改掉，文件裡的指令必須是實際跑通過的

## R059 需要使用者先做一步的畫面，空白時沒說下一步 —— 2026-09-17

**失敗訊號**：營運指揮艙一九姨「後台」支線，Balian 回報「指揮艙沒東西」。原因是這台瀏覽器還沒存金鑰，設計上就不載入頁面，
只在右上角放了一個輸入框，畫面主體整片空白。上一則回覆雖然寫了「第一次要貼金鑰」，但畫面本身沒說。

**harness 層**：觀測層（使用者端看不出「為什麼沒東西」，把正常的前置狀態誤判成壞掉）。

**永久規則**：
- **任何要使用者先做一步才會出現內容的畫面（貼金鑰、登入、綁定、選篩選條件），空白狀態必須在主畫面寫出「現在缺什麼、去哪裡做、做完會怎樣」**，不能只靠旁邊一個輸入框或對話裡的說明
- 交付前要看一次「全新使用者、什麼都沒設定」的畫面，不只看「已設定好」的畫面

## R060 測試只驗狀態碼，被別的路由攔走的 API 看起來也「通過」—— 2026-09-17

**失敗訊號**：enjoyclean 本機測試「庫存 API 帶金鑰 → 200」通過，線上冒煙「不帶金鑰 → 401」卻回 200。
查下去是 `/api/qr/stock` 的 GET 先命中公開的「`/api/qr/<碼>`」解析規則，被當成查一個叫 stock 的碼。
庫存 API 從寫好到現在**從來沒被執行過**，QR 標籤產生器的查庫存一直是壞的，沒有人發現。
同一次冒煙還有一項是測試自己寫錯：假設線上 `test11` 已綁定，其實還是空白碼，頁面本來就沒有服務紀錄表單。

**後果**：這次沒有漏資料（被攔走的是無害的解析），但同樣的情況如果發生在寫入類 API，就是「以為有擋、其實走了另一條沒擋的路」。

**harness 層**：觀測層（驗證只看 HTTP 狀態碼，沒驗回應內容是不是那支 API 產生的）＋ 執行層（冒煙測試寫死線上資料狀態）。

**永久規則**：
- **API 測試要驗回應內容的特徵欄位**（例：庫存要有 `remaining`），不能只看 200／401。狀態碼對、內容是別支 API 的，一律算失敗
- **路由用「前綴＋萬用參數」的規則（`/api/qr/<任意>`）要排在具名路由後面，或明確排除具名路徑**；新增具名路由時，測試要涵蓋「沒被萬用規則攔走」
- **線上冒煙不准寫死測試資料的狀態**（哪張碼已綁定），要當下從資料庫查出符合條件的資料再測
- GPC 冒煙有任何一項失敗就停在 push 前，先判斷是程式錯還是測試錯，修完重跑全部冒煙才准 push（這次照做了）

## R061 產實體標籤的工具，碼沒進系統就能印 —— 2026-09-17

**失敗訊號**：Balian 用「QR 標籤產生器」印 A4 測試標籤，掃了全部「查無此標籤」。問「這些條碼已經進系統了嗎」，得知要另外下載 SQL 再匯入後回：「我下載下來還要匯入？？」
工具設計：一打開就在瀏覽器產生隨機碼、**不寫資料庫**；要能掃得「下載 SQL → 匯入」，提醒只有設定區底下一行灰字；**重新整理碼就全部換掉**，已印的紙等於作廢；「線上產碼」從本機開檔打 API 會被跨網域擋，實際不能用。

**後果**：印出一整張系統裡不存在的標籤；如果貼到客戶家機器上，師傅掃了進不去，現場卡死。這次靠 Balian 剛好還留著分頁、下載了 SQL，才把 18 張補進資料庫。

**harness 層**：約束層（「產生」和「生效」拆成兩步，第二步靠人記得）＋ 觀測層（未生效狀態沒有大聲警告）。

**永久規則**：
- **會產生實體或對外東西的工具（標籤、連結、QR、邀請碼），必須先寫進系統、寫入成功才允許輸出／列印**。不准做成「先產出、之後再另外匯入」
- 工具的狀態如果跟系統不一致（本機有、系統沒有），畫面要大聲寫出來並擋住下一步，不能只放一行提示
- 交付工具前，自己走一次「使用者照畫面操作到底」的完整路線（這次只驗了能產碼、能印，沒驗「印出來的掃了會不會通」）

## R062 部署跑到一半憑證過期，錯誤碼把人帶去錯的方向 —— 2026-09-17

**失敗訊號**：小雞打工色塊卡片 `deploy.sh staging` 語法檢查、AI 審查都過了，第三步套 migration 時 Cloudflare 回 `7403 The given account is not valid or is not authorized`。看起來像帳號或資料庫權限問題；接著查 `wrangler whoami`（當下還顯示已登入）、`wrangler.jsonc`、拿 enjoyclean 資料庫做對照，全部正常，第四次查才出現 `You are not authenticated`——wrangler 的 OAuth 授權就在這幾分鐘內過期。
同一輪還有第二個憑證坑：本機 `~/.config/line-checkin-system/credentials.env` 的 LINE token 是 2026-08-22 舊版、早已失效，拿來做卡片格式驗證，21 項全部回 401，差點被當成卡片格式錯誤。

**後果**：多花三輪排查；部署卡在半路（審查過了、還沒上 staging）。如果過期發生在 prod 段，會停在「migration 已套、Worker 還沒部署」的中間狀態。

**harness 層**：執行層（長流程中途才碰到憑證）＋ 觀測層（錯誤碼不指向真因、本機憑證過期沒有任何提示）。

**永久規則**：
- **會碰雲端的長流程，第一步先驗憑證**（`wrangler whoami` 必須顯示已登入），不過就停下並直接講「憑證過期，跑 `wrangler login`」，不讓它跑到一半用別的錯誤碼爆出來
  - 待補：`xiaoji-checkin/scripts/deploy.sh` 開頭加這道檢查（2026-09-17 當時另一個對話正在改 deploy.sh，未動）
- 看到 Cloudflare `7403` 或 `10000`，**先重跑一次 `wrangler whoami`**，再去查權限或設定
- **本機憑證檔不是真相來源**：線上 Worker 的 secret 可能早就換過。拿本機 token 驗證得到 401，先懷疑 token 過期，不要懷疑受測物
  - 已補：`scripts/validate_notice.mjs` 可用 `LINE_VALIDATE_TOKEN` 指定有效 token
  - 待補：更新或刪掉 `credentials.env` 裡失效的 `LINE_MESSAGING_CHANNEL_ACCESS_TOKEN`

## R063 工具的提示文字跟強制規則打架 —— 2026-09-17

**失敗訊號**：`bump_version.py xiaoji patch` 跑完印出「記得部署：cd xiaoji-checkin && npx wrangler deploy」，但 R055 規定小雞打工禁止直接 `wrangler deploy`、一律走 `deploy.sh`（hook 會擋）。
同一輪 `deploy.sh prod` 裡的 `npx wrangler deploy` 沒帶 `--env=""`，wrangler 警告「定義了多個環境但沒指定目標」，這次是靠預設值剛好打到正式環境。

**後果**：這次沒出事（hook 擋在前面、預設值剛好對）。但照工具提示操作的人會撞 hook；環境沒寫死，哪天 wrangler 預設行為一變，就可能部署到錯的環境。

**harness 層**：規則書（工具內嵌的指引沒跟著規則更新）＋ 約束層（部署目標靠預設值）。

**永久規則**：
- **新增強制規則時，同步 grep 所有工具輸出與文件裡的舊指令**，一起改掉，不然工具會持續教人違規
  - 待補：`scripts/bump_version.py` 的部署提示改成 `./scripts/deploy.sh staging`
- **多環境的部署指令一律明寫目標環境**（`--env=""` 或 `--env staging`），不靠預設
  - 待補：`deploy.sh prod` 的 `npx wrangler deploy` 加 `--env=""`

## R064 跨分頁共用的篩選器被 A 頁改掉，B 頁沿用卻沒有重設守衛 —— 2026-09-20

**失敗訊號**：小雞打工後台報表頁顯示「統計區間 2026-10」，打卡明細數、完整班次數、總工時全是 0，看起來像「這個月打卡沒有更新」。實際上後端資料完全正常（`/report?month=2026-09` 查得到小米 17 次／897 分、倪珊如 4 次／80 分，最後打卡 2026-09-20T10:43），查的是**未來月份**所以必然全 0。
原因是 `小雞打卡出勤紀錄.html` 的 `monthEl` 為全部分頁共用的單一月份選擇器。排班分頁有兩處會刻意把它跳到下個月（`:1386` 換班紀錄頁、`:1415` `pickReviewMonth()` 找不到登記資料時），而切回報表時的守衛 `if (tab !== 'report' && !monthEl.value)`（`:1346`）兩個條件都擋不住：`tab !== 'report'` 明文排除報表，`!monthEl.value` 只在空值時才補、現值 `2026-10` 非空。

**後果**：使用者把「查詢條件錯」誤判成「資料沒進來」，先懷疑打卡功能壞掉。排班頁那兩處跳月是刻意設計（註解寫明 2026-09-01 踩過「停在當月什麼都看不到」的坑），所以這不是把跳月改掉就好，是守衛漏了。同檔案還有場域、員工兩個同樣跨分頁共用的篩選器，同型坑可能不只一處。

**harness 層**：約束層（沒有守衛擋住「報表查未來月份」這種不可能有意義的查詢）＋ 觀測層（畫面其實有寫「統計區間 2026-10」，但 0 跟「區間根本還沒到」長得一模一樣，真相在畫面上卻讀不出來）。

**永久規則**：
- **跨分頁共用的可變篩選器，每個分頁都要明確宣告它接受的值域**，切進去時檢查現值是否在值域內，不在就重設。不能只檢查「是否為空」——被別頁改過的值是非空的錯值
- **查詢條件落在不可能有資料的區間時，畫面要講出原因，不要只顯示 0**。「0 筆」與「這個區間還沒到」在視覺上必須不同，否則使用者一定往資料層去猜
- 修這類 bug 時**不要動別頁刻意設定的行為**（這裡是排班頁跳下個月），該補的是接收端的守衛
  - 待補：`小雞打卡出勤紀錄.html:1346` 報表分頁月份守衛改成檢查「是否 > 當月」；報表可看歷史月份，看未來月份永遠是錯的
  - 待補：檢查同檔案的場域、員工篩選器有無同型問題

## R065 外部服務配額用盡，系統安靜地停止工作 —— 2026-09-20

**失敗訊號**：小雞打工 LINE 官方帳號連續數天沒有推播任何訊息。系統各層檢查全部正常——Worker 200、`/health` 回 `ok:true` `cron:true` `db_ms:18`、`line_dry_run:false`、兩組 cron 都在、9/17–9/30 每天都有班表資料。真因要打 `/diag/line` 才看得到：`quota 200 / totalUsage 200`，LINE 輕用量方案每月 200 則主動推播已打滿，push 全被擋在 LINE 端。

**後果**：系統「有發，但出不去」，而健康檢查一路綠燈。沒有 `/diag/line` 這個端點就只能靠猜。若不是主動去查，會一直以為排程壞了或 token 失效。

**harness 層**：觀測層（額度是外部狀態，不在任何健康檢查裡，用盡時沒有任何告警）。

**永久規則**：
- **凡是有配額的外部服務，配額本身要進健康檢查**，接近上限（如 80%）就主動告警，不要等到打滿才從「怎麼沒反應」回頭查
- **「安靜地不工作」是最貴的失敗形態**：功能正常、檢查全綠、就是沒有輸出。設計對外整合時先問一句「它失敗的時候，我會從哪裡知道？」
- 配額型服務要在**規劃階段就算每客戶用量**：小雞打工每天光班表提醒就是「每個有班的人 1 則＋管理者摘要 1 則」，外部業者 20 人規模第 10 天就會打滿 200。這是每客戶的固定成本，必須進報價，不是上線後才發現
  - 待補：`/health` 納入 LINE 額度百分比
  - 待補：管理者每日摘要改走後台 `/board/today`，不佔推播額度（每月省約 30 則）
