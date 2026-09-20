#!/usr/bin/env python3
"""版本號同步 bump — 一個專案的版本字串散在多個檔案，這裡一次改完並檢查一致性。

用法：
    python3 scripts/bump_version.py xiaoji --show          看目前各處版本、標出不一致
    python3 scripts/bump_version.py xiaoji patch           修訂號 +1      1.9.1 -> 1.9.2
    python3 scripts/bump_version.py xiaoji minor           次版本 +1      1.9.2 -> 1.10.1
    python3 scripts/bump_version.py xiaoji major           主版本 +1      1.10.1 -> 2.1.1
    python3 scripts/bump_version.py xiaoji set 2.0.1       直接指定
    python3 scripts/bump_version.py --list                 列出有設定的專案

新增專案：編輯 scripts/version_targets.json，pattern 用三個 group
（前綴 / 版本數字 / 後綴），版本數字那組不含開頭的 v。
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "scripts" / "version_targets.json"


def load_config():
    with CONFIG.open(encoding="utf-8") as fh:
        return json.load(fh)


def find_versions(project):
    """回傳 [(target, 檔案路徑, [找到的版本字串])]"""
    out = []
    for target in project["targets"]:
        path = ROOT / target["file"]
        if not path.exists():
            out.append((target, path, None))
            continue
        text = path.read_text(encoding="utf-8")
        hits = [m.group(2) for m in re.finditer(target["pattern"], text)]
        out.append((target, path, hits))
    return out


def vkey(v):
    """字串排序會把 1.10.1 排在 1.5.2 前面，一律轉成 tuple 比。"""
    return tuple(int(x) for x in v.split("."))


def next_version(cur, level):
    major, minor, patch = (int(x) for x in cur.split("."))
    if level == "patch":
        patch += 1
    elif level == "minor":
        minor, patch = minor + 1, 1
    elif level == "major":
        major, minor, patch = major + 1, 1, 1
    return f"{major}.{minor}.{patch}"


def show(name, project):
    print(f"\n{name} — {project['label']}")
    print(f"  規則：{project['rule']}")
    found = find_versions(project)
    all_versions = set()
    missing = []
    for target, path, hits in found:
        if hits is None:
            print(f"  ✗ {target['file']}  檔案不存在")
            missing.append(target["file"])
            continue
        if not hits:
            print(f"  ✗ {target['file']}  pattern 沒對到任何版本字串")
            missing.append(target["file"])
            continue
        all_versions.update(hits)
        joined = "、".join(f"v{h}" for h in hits)
        print(f"  · {target['file']:<34} {joined}  （{len(hits)} 處｜{target['desc']}）")

    if missing:
        return None
    if len(all_versions) == 1:
        cur = all_versions.pop()
        print(f"  → 目前版本 v{cur}（全部一致）")
        return cur
    ordered = sorted(all_versions, key=vkey)
    print(f"  ⚠ 版本不一致：{'、'.join('v' + v for v in ordered)}")
    print(f"     下一次 bump 會以最高的 v{ordered[-1]} 為基準，把所有位置統一。")
    return ordered[-1]


def apply(project, new_version):
    total = 0
    for target in project["targets"]:
        path = ROOT / target["file"]
        if not path.exists():
            print(f"  ✗ {target['file']} 不存在，中止")
            return False
        text = path.read_text(encoding="utf-8")
        text, n = re.subn(
            target["pattern"],
            lambda m: f"{m.group(1)}v{new_version}{m.group(3)}",
            text,
        )
        if n == 0:
            print(f"  ✗ {target['file']} 沒對到 pattern，中止（未寫入任何檔案）")
            return False
        path.write_text(text, encoding="utf-8")
        print(f"  ✓ {target['file']}  {n} 處")
        total += n
    print(f"→ v{new_version}（共 {total} 處）")
    return True


def main():
    config = load_config()
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0

    if args[0] == "--list":
        for name, project in config.items():
            print(f"  {name:<10} {project['label']}（{len(project['targets'])} 個檔案）")
        return 0

    name = args[0]
    if name not in config:
        print(f"沒有這個專案：{name}")
        print(f"可用：{'、'.join(config)}")
        return 1
    project = config[name]

    if len(args) == 1 or args[1] == "--show":
        return 0 if show(name, project) else 1

    cur = show(name, project)
    if cur is None:
        print("\n有檔案對不到 pattern，先修好 version_targets.json 再 bump。")
        return 1

    action = args[1]
    if action == "set":
        if len(args) < 3:
            print("set 要帶版本號，例如：set 2.0.1")
            return 1
        new_version = args[2].lstrip("v")
        if not re.fullmatch(r"\d+\.\d+\.\d+", new_version):
            print(f"版本格式要是 主.次.修，收到：{new_version}")
            return 1
    elif action in ("patch", "minor", "major"):
        new_version = next_version(cur, action)
    else:
        print(f"不認得的動作：{action}（可用 patch / minor / major / set / --show）")
        return 1

    print(f"\nbump v{cur} → v{new_version}")
    if not apply(project, new_version):
        return 1
    if name == "xiaoji":
        print("\n記得部署：cd xiaoji-checkin && ./scripts/deploy.sh staging")
    else:
        print("\n記得部署（部署方式依專案，不要一律 wrangler deploy）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
