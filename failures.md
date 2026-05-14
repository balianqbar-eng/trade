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
