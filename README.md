# SUSFS LKM BTF-relax 编译工具流（交接文档）

## 1. 背景：这套工具流解决什么

上游 `inforcqb/susfs4ksu-for-lkm` 从 **r18.2** 起在 `susfs_watch_abi()` 里加了 BTF 签名强校验。手机这颗第三方内核的 BTF 没有为若干**导出函数**生成 FUNC 条目（`fsnotify_alloc_group` 等），校验第一步就返回 `-ENOENT(-2)`，`sus_path` 初始化中止，ko 加载失败。

官方 Google GKI 5.15.194 的 BTF 完整，14 项全过——问题在第三方内核的 BTF，不在 r18.9 本身。

补丁的做法：**只在 `-ENOENT` 时按 5.15 已知签名放行**，`-EINVAL(-22，真签名不符)` 仍然拒绝，数据结构/枚举/回调偏移校验（01–08）一个没动。写死的值来自实测：`alloc_group` 用 1 参、`add_mark` 用 5 参、`super_block.s_fsnotify_marks` 偏移 1008（官方与手机 BTF 都是 1008、super_block 都是 1600）。

## 2. 目录资产

| 文件 | 用途 |
|---|---|
| `README.md` | 本交接文档 |
| `tool.py` | 辅助脚本：`fetch` / `patch` / `verify`，无第三方依赖 |
| `fsnotify_lifetime.patch` | 核心补丁（3 个 hunk），改 `susfs_watch_abi()` |
| `fsnotify_lifetime.c` | 已打补丁的完整源文件，**网页编辑器粘贴用这个**（不是 patch） |

工具包本地位置：`D:/workbuddy/.workbuddy/2026-11-11-15-45-16/susfs-build/`

配套产物（本次实测，在 `E:/Users/29827/Downloads/`）：

| 文件 | 说明 |
|---|---|
| `ReSuSFS-v26.10.23-a13.5.15-r18.9-btfrelax.zip` | 可刷模块包，内置新 ko |
| `susfs_guard_lkm.ko-android13-5.15.zip` | 编译出的 ko artifact |
| `susfs_insmod.zip` | 配套 insmod helper |

## 3. 环境依赖与约束

- **Python 3**：`tool.py` 用它，标准库够，不用装包。
- **代理** `http://127.0.0.1:7897`：拉 GitHub raw 需要；脚本默认走它，传 `--proxy none` 可禁用。
- **Edge + 浏览器扩展**，登录态为 `kiyonoRin`：写操作（fork/push/触发 Actions/下载 artifact）**必须走浏览器 UI**。
- **不能用 GitHub MCP 做写操作**：当前连接是 App integration token，只有读权限，fork/create/push 都返回 `403 Resource not accessible by integration`。换脚本无效，卡在凭据类型。
- **本机编译不可行**：Docker 装了但 daemon 没起（连不上 `dockerDesktopLinuxEngine`），WSL 在本会话起不来。所以编译走 GitHub Actions。

## 4. 版本更新适配流程

上游出新 tag（如 `v2.3.0-r18.10`）后，按下面走。

### 4.1 离线准备（先确认补丁还能套上）

```bash
cd D:/workbuddy/.workbuddy/2026-11-11-15-45-16/susfs-build

# 1. 拉新版本源码
python tool.py fetch v2.3.0-r18.10 -o new_base.c

# 2. 试套补丁（会逐 hunk 校验上下文，必须精确匹配 1 次）
python tool.py patch new_base.c -o new_patched.c
```

- **两条命令都成功**：说明新版本的 `susfs_watch_abi()` 结构与 r18.9-1 一致，补丁可直接用。`new_patched.c` 就是后面要粘到网页编辑器的文件。
- **`patch` 报 `上下文匹配 0 次（期望 1）...需人工适配`**：上游改了这段结构。先备份现有补丁（`cp fsnotify_lifetime.patch fsnotify_lifetime.patch.bak`），再打开 `new_base.c` 对照补丁，看是哪几行变了，手动改补丁的 old 块（`fsnotify_lifetime.patch`），重跑 patch。**不要硬套**——硬套会把新逻辑覆盖掉。改完确认无误后再决定是否替换基准补丁。
- 若上游干脆删掉了 `kernel/fsnotify_lifetime.c`（退回无 BTF 校验的机制），则本补丁不再需要，直接编译原版即可。

### 4.2 取新 tag 指向的 commit（建分支要用）

fork **不复制 tag**，只复制 main 分支；但 commit 对象共享，可从 commit 建分支。

```bash
# annotated tag 要先解引用
curl -sS -x http://127.0.0.1:7897 \
  "https://api.github.com/repos/inforcqb/susfs4ksu-for-lkm/git/ref/tags/v2.3.0-r18.10"
# 取返回的 object.sha；若 object.type=tag，再查:
curl -sS -x http://127.0.0.1:7897 \
  "https://api.github.com/repos/inforcqb/susfs4ksu-for-lkm/git/tags/<object.sha>" \
  | python -c "import sys,json;print(json.load(sys.stdin)['object']['sha'])"
```

本次 r18.9-1 的结果是 `8619b6ee0d0629836e9c6ce668e8a785dfd53517`。

## 5. 浏览器编译 SOP（照着点，别跳步）

用已登录 `kiyonoRin` 的 Edge，进入 WorkBuddy 浏览器扩展接管。

1. **Fork（若还没 fork）**：打开 `https://github.com/inforcqb/susfs4ksu-for-lkm` → 点 Fork → owner 选 `kiyonoRin`，保留默认设置创建。结果是 `kiyonoRin/susfs4ksu-for-lkm`。
   - ⚠️ MCP 的 fork API 会 403，只能走网页。

2. **从 commit 建分支**：访问 `https://github.com/kiyonoRin/susfs4ksu-for-lkm/tree/<4.2 拿到的 commit>` → 分支下拉 → "Find or create a branch..." → 输入分支名（本次用 `r189-btf-relax`，新版建议 `rXXX-btf-relax`）→ 点 "Create branch ... from <commit>"。
   - ⚠️ 不要从 main 建：main 领先 tag 几十个 commit，补丁 base 对不上。
   - ⚠️ 网页 DOM 接口偶发超时，超时就 `tab_screenshot` 看页面，再重试 DOM 或用坐标点。

3. **提交补丁文件**：访问 `https://github.com/kiyonoRin/susfs4ksu-for-lkm/edit/<分支>/kernel/fsnotify_lifetime.c` → 点编辑区 → `Ctrl+A` 全选 → 粘贴 4.1 生成的 `new_patched.c` **全文** → 写 commit message → Commit。
   - ⚠️ 粘的是完整文件，不是 diff。
   - ⚠️ `\n` 在源码里是字面两字符，粘贴时别被转义成真换行。
   - 提交后务必回拉校验：`curl .../raw/<分支>/kernel/fsnotify_lifetime.c` 与本地 `new_patched.c` 比对（GitHub 存 LF，本地可能是 CRLF，去 CR 后应逐字节相同）。

4. **启用 Actions**：打开 `https://github.com/kiyonoRin/susfs4ksu-for-lkm/actions` → 点绿色按钮 "I understand my workflows, go ahead and enable them"。
   - ⚠️ fork 默认**禁用** workflows；不启用则第 3 步的 push 不会触发编译。

5. **手动触发编译**：打开 `.../actions/workflows/build-ddk.yml` → "Run workflow" → 分支**必须选第 2 步建的分支**（默认是 main，一定改）→ "Run workflow"。
   - workflow 显示名是 `build-lkm-ddk`，8 个变体 + tools + module-zip，约 20 个 artifact。本次耗时 3 分 5 秒（有缓存；冷启动可能更久）。

6. **看结果**：回到 run 页面（URL 形如 `.../actions/runs/<run_id>`），确认所有 job 全绿。annotations 里的 Node.js 20 弃用警告、android13-5.10 的 "no symbol CRCs" 都无害。

## 6. 下载与校验

1. 在 run 页面点 artifacts 数量 → 找 `susfs_guard_lkm.ko-<KMI>`（手机是 `susfs_guard_lkm.ko-android13-5.15`），点下载图标；同样下载 `susfs_insmod`。浏览器登录态会自动下载到 `E:/Users/29827/Downloads/`。

2. 校验（脚本会查 ELF、KMI、两条补丁字符串、vermagic，并算 zip 的 sha256）：

```bash
cd D:/workbuddy/.workbuddy/2026-11-11-15-45-16/susfs-build
python tool.py verify ../ko_r189/susfs_guard_lkm.ko \
  --zip "e:/Users/29827/Downloads/susfs_guard_lkm.ko-android13-5.15.zip"
```

3. 把打出的 sha256 与 GitHub artifact 页面显示的 digest 比对，一致才算可信。本次是 `92031fd940080edfbd3edcf0167a0c9cdd1e39db2f370f17a98f88a85641ed7e`。

4. ⚠️ artifact 里 ko 的文件名是 `susfs_guard_lkm.ko`，**打包进模块时要重命名**为 `susfs_guard_lkm-<KMI>.ko`（如 `susfs_guard_lkm-android13-5.15.ko`）。

## 7. 打包模块（需要刷机时）

基于手机原包 `../phone-a13-5.15/ReSuSFS-v26.10.23-a13.5.15-r18.zip`：

1. 解包 → 用新 ko 覆盖 `lkm/susfs_guard_lkm-android13-5.15.ko`，用新 `susfs_insmod` 覆盖 `lkm/susfs_insmod`。
2. `module.prop` 版本号 +1、description 标注版本（本次 `v26.10.23-r18.9-btfrelax` / `versionCode=23`），保留 author 与 updateJson。
3. 重新打包 zip，放到 `E:/Users/29827/Downloads/`。
4. `customize.sh` 会把内置 `lkm/*` 复制到 `/data/adb/ReSuSFS_LKM/`，之后 `download_susfs_guard_lkm` 因文件已存在而跳过下载——所以内置 ko 会真正生效。

## 8. 已知风险（刷机前必读）

- **未做真机验证**。补丁把 BTF FUNC 校验的 `-ENOENT` 放行、写死 `susfs_add_with_object=5参`；依据是官方 5.15 GKI 实测为 5 参且手机数据结构逐字节一致。判断错会在 `susfs_add_mark()` 参数错位时 **kernel panic**。
- 刷后先看 `dmesg`：有 `sus_path: add_mark FUNC absent in BTF, assuming 5-arg` 说明补丁分支走到了；若有 `fsnotify lifetime ABI validation failed` 说明仍有别的项不通过。
- `-EINVAL` 仍拒绝、数据结构校验未动，fail-closed 的大部分保护还在。
- 升级内核/换机后必须重跑第 4 步的适配校验，别拿旧 ko 直接刷。

## 9. 本次实测记录（2026-11-18）

- 上游 tag `v2.3.0-r18.9-1`，commit `8619b6ee`，分支 `r189-btf-relax`，补丁 commit `bb1904e`。
- 浏览器 UI 完成 fork / 建分支 / 粘贴提交 / 启用 Actions / 手动触发；远端 raw 文件与本地补丁逐字节一致（去 CR 后）。
- run `44150079035`，3 分 5 秒全绿，20 artifacts。
- ko：`susfs_guard_lkm.ko` 6,747,560 字节，vermagic `5.15.202-android13-5.15.202_r00-dirty SMP preempt mod_unload modversions aarch64`，KMI `android13-5.15`。
- 两条补丁 pr_info 字符串均在 ko 中，zip digest 与 GitHub 页面一致。
- **全程未操作手机、未刷入**。手机当时已断 adb。
