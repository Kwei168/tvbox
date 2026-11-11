# tvbox · 自用影视仓/TVBox 多仓接口（GitHub Actions 全自动更新）

> 参照 [Lightconer/tvbox-ysc-config](https://github.com/Lightconer/tvbox-ysc-config) 的模式搭建，采用同样的「**内容镜像**」自动更新机制：
> **每天**把 23 个上游源的最新配置内容抓回来存进本仓库 `output/` 快照（接口指向自己的快照，上游改了第二天自动跟上，上游挂了还有历史快照兜底）；
> 连挂 3 天的死源自动移除；**每周**扫描 GitHub 收录实测合格的新源；另生成**聚合单仓**（全部源合并去重）。
> 初始线路全部经过 2026-11-11 实测验证。
>
> **`tvbox_config.json` / `tvbox_config_lite.json` 文件名不变，电视盒里已填的地址无需任何修改。**

![每日复测](https://github.com/Kwei168/tvbox/actions/workflows/daily-check.yml/badge.svg)
![每周扫描](https://github.com/Kwei168/tvbox/actions/workflows/weekly-scan.yml/badge.svg)

## 接口地址

```
完整版（原有，不变）: https://raw.githubusercontent.com/Kwei168/tvbox/main/tvbox_config.json
精简版（原有，不变）: https://raw.githubusercontent.com/Kwei168/tvbox/main/tvbox_config_lite.json
聚合单仓（新增，可选）: https://raw.githubusercontent.com/Kwei168/tvbox/main/tvbox_config_merged.json
```

备用线路（内容相同，任选）：

```
https://cdn.jsdelivr.net/gh/Kwei168/tvbox@main/tvbox_config.json
https://gh-proxy.com/https://raw.githubusercontent.com/Kwei168/tvbox/main/tvbox_config.json
```

## 三个文件的区别

| 文件 | 格式 | 内容 |
|---|---|---|
| `tvbox_config.json` | storeHouse + urls **双格式** | 全量线路，每条指向本仓库 `output/<id>.json` 快照（OK影视/FongMi 读 urls，影视仓/TVBox 读 storeHouse，互不干扰） |
| `tvbox_config_lite.json` | 纯 urls（与原格式一致） | 精简 10 条主力大库（高天流云 298 源、老六杯 234 源、流光 234 源等），同样指向本仓库快照 |
| `tvbox_config_merged.json` | 单仓配置 | **聚合版**：全部单仓源的 sites/lives/parses 合并去重成一个超大配置（约上千源，按 key 去重、自动补各源 jar）；实验性质，个别源异常时请切回多仓线路 |

## 自动更新原理（和 Lightconer 项目相同）

1. 每天 `daily-check` 逐源尝试「主线 + 备用」地址，抓取上游**最新配置内容**
2. 成功的源把内容快照写入 `output/<id>.json` 提交到本仓库（相对路径的 `spider/jar/ext` 自动改写为上游绝对地址，快照可独立使用）
3. 根目录三个接口文件里的线路全部指向**本仓库快照**，而不是上游原始链接——所以上游内容每天自动跟随、上游域名挂了快照仍在
4. 某源连续 3 天抓不到 → 自动从清单移除并删除快照；期间电视盒仍能用最后一次的快照，不会突然黑屏
5. 每周一 `weekly-scan` 扫描 GitHub 新仓库，实测合格的新源自动追加进清单并立即抓取快照

## 自动化任务（全部跑在 GitHub 服务器上）

| Workflow | 时间 | 做什么 |
|---|---|---|
| daily-check | 每天 UTC 01:00（北京 09:00） | 抓取 + 镜像 + 复测全部线路 → 重新生成三个接口文件 → 写 reports/ → 自动提交推送 |
| weekly-scan | 每周一 UTC 02:00（北京 10:00） | 搜索 GitHub 近 30 天活跃仓库 → 提取新接口 → 实测（门槛：单仓 ≥30 源 / 直播 ≥10 / 多仓 ≥3 线路）→ 收录最多 5 条 → 自动提交推送 |

- 都支持在 **Actions 页面手动触发**（Run workflow 按钮）
- 修改 `config/**` 或 `scripts/**` 后 push 会立刻自动复测一次
- 无需配置任何密钥：GITHUB_TOKEN 自动注入，workflow 已声明 `permissions: contents: write`
- 运行日志看 **Actions** 标签页；每日/每周报告与状态看 **reports/** 目录；线路状态总览见 [SOURCES.md](SOURCES.md)

## 部署（本仓库已存在，直接覆盖上传即可）

1. 打开仓库 → **Add file → Upload files**
2. 把本地 `tvbox-source` 文件夹里的**全部内容**（含 `.github`、`config`、`scripts`、`output`、`reports` 文件夹和根目录所有文件）拖入 → **Commit changes**（同名自动覆盖）
3. **Actions** 页面 → 选「每日复测线路」→ **Run workflow** 手动跑一次验证（绿灯即成功）

git 方式（可选）：

```powershell
cd tvbox-source
git init -b main
git add .
git commit -m "init: 多仓接口 + GitHub Actions 自动更新"
git remote add origin https://github.com/Kwei168/tvbox.git
git push -u origin main --force   # 以本地整理版为准覆盖远端
```

## 目录结构

```
├── .github/workflows/
│   ├── daily-check.yml      # 每天 09:00(北京) 抓取镜像+复测
│   └── weekly-scan.yml      # 每周一 10:00(北京) 扫描收录
├── config/
│   └── sources.json         # 线路清单（唯一需要手工编辑的文件）
├── scripts/
│   ├── common.py            # 抓取 / 宽容解析(BOM·注释·中文域名) / 可用性判定
│   ├── gen_multistore.py    # 由快照生成三个接口产物 + SOURCES.md
│   ├── check_sources.py     # 每日抓取镜像 + 复测 + 自动移除死源
│   └── scan_github.py       # 每周扫描收录（新源立即抓快照）
├── output/                  # 各源内容快照 <id>.json（自动更新，接口指向这里）
├── reports/                 # 每日 / 每周报告 + status.json
├── check_history.json       # 连续失效计数（自动维护）
├── tvbox_config.json        # 产物：完整版（自动生成，勿手改）
├── tvbox_config_lite.json   # 产物：精简版（自动生成，勿手改）
├── tvbox_config_merged.json # 产物：聚合单仓（自动生成，勿手改）
├── SOURCES.md               # 线路清单与状态（自动生成）
└── README.md
```

## 日常维护

- **加 / 删线路**：编辑 [config/sources.json](config/sources.json)，字段：`id`（英文标识，快照文件名）、`name`、`urls`（**数组**，第一个是主线其余是备用）、`compat`（`tvbox` / `fongmi` / `both`）、可选 `"lite": true`（进精简版）→ push 后自动复测并重新生成
- **调整规则**：连续失效移除阈值在 `scripts/check_sources.py` 的 `DEAD_DAYS`；每周收录上限与门槛在 `scripts/scan_github.py` 顶部常量
- **本地手动运行**（可选，纯标准库零依赖）：`python scripts/check_sources.py`、`python scripts/scan_github.py --dry-run`

## 声明

内容均来自互联网公开仓库聚合，仅供个人学习测试自用，请于 24 小时内自行删除；线路随时可能失效，请勿用于任何商业用途。
