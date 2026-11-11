# tvbox · 自用影视仓/TVBox 多仓接口（GitHub Actions 全自动维护）

> 参照 [Lightconer/tvbox-ysc-config](https://github.com/Lightconer/tvbox-ysc-config) 的自动化模式搭建：
> **每天**自动复测全部线路并自动剔除连挂 3 天的死源，**每周**自动扫描 GitHub 收录实测合格的新源，
> 结果自动提交回本仓库。初始 25 条线路全部经过 2026-11-11 实测验证。
>
> **文件名保持 `tvbox_config.json` / `tvbox_config_lite.json` 不变，电视盒里已填的地址无需任何修改。**

![每日复测](https://github.com/Kwei168/tvbox/actions/workflows/daily-check.yml/badge.svg)
![每周扫描](https://github.com/Kwei168/tvbox/actions/workflows/weekly-scan.yml/badge.svg)

## 接口地址（与原来完全相同，直接覆盖）

```
完整版: https://raw.githubusercontent.com/Kwei168/tvbox/main/tvbox_config.json
精简版: https://raw.githubusercontent.com/Kwei168/tvbox/main/tvbox_config_lite.json
```

备用线路（内容相同，任选）：

```
https://cdn.jsdelivr.net/gh/Kwei168/tvbox@main/tvbox_config.json
https://gh-proxy.com/https://raw.githubusercontent.com/Kwei168/tvbox/main/tvbox_config.json
```

## 两个文件的区别

| 文件 | 格式 | 内容 |
|---|---|---|
| `tvbox_config.json` | storeHouse + urls **双格式** | 全量 25 条（urls 24 条给 OK影视/FongMi 读，storeHouse 22 条给影视仓/TVBox 读，互不干扰） |
| `tvbox_config_lite.json` | 纯 urls（与原文件格式一致） | 精简 10 条主力大库（高天流云 298 源、老六杯 234 源、流光 234 源等），启动快、切换少 |

## 自动化任务（全部跑在 GitHub 服务器上）

| Workflow | 时间 | 做什么 |
|---|---|---|
| daily-check | 每天 UTC 01:00（北京 09:00） | 实测全部线路 → 写 reports/ 与 reports/status.json → 连续 3 天失效的线路自动移除 → 重新生成两个 config → 自动提交推送 |
| weekly-scan | 每周一 UTC 02:00（北京 10:00） | 搜索 GitHub 近 30 天活跃的 tvbox/影视仓仓库 → 抓 README 提取新接口 → 实测（门槛：单仓 ≥30 源 / 直播 ≥10 / 多仓 ≥3 线路）→ 按评分收录最多 5 条 → 自动提交推送 |

- 都支持在 **Actions 页面手动触发**（Run workflow 按钮）
- 修改 `config/**` 或 `scripts/**` 后 push 会立刻自动复测一次
- 无需配置任何密钥：GITHUB_TOKEN 自动注入，workflow 已声明 `permissions: contents: write`
- 运行日志看 **Actions** 标签页；每日/每周报告与状态看 **reports/** 目录
- 线路清单实时版见 [SOURCES.md](SOURCES.md)（自动生成）

## 部署（本仓库已存在，直接覆盖上传即可）

1. 打开仓库 → **Add file → Upload files**
2. 把本地 `tvbox-source` 文件夹里的**全部内容**（含 `.github`、`config`、`scripts`、`reports` 文件夹和根目录的 `tvbox_config.json`、`tvbox_config_lite.json`、`README.md` 等）拖入 → **Commit changes**（同名文件自动覆盖）
3. **Actions** 页面 → 选「每日复测线路」→ **Run workflow** 手动跑一次验证（绿灯即成功）

git 方式（可选）：

```powershell
cd tvbox-source
git init -b main
git add .
git commit -m "init: 多仓接口 + GitHub Actions 自动维护"
git remote add origin https://github.com/Kwei168/tvbox.git
git push -u origin main --force   # 以本地整理版为准覆盖远端
```

## 目录结构

```
├── .github/workflows/
│   ├── daily-check.yml      # 每天 09:00(北京) 复测
│   └── weekly-scan.yml      # 每周一 10:00(北京) 扫描收录
├── config/
│   └── sources.json         # 线路清单（唯一需要手工编辑的文件）
├── scripts/
│   ├── common.py            # 抓取 / 宽容解析(BOM·注释·中文域名) / 可用性判定
│   ├── gen_multistore.py    # 生成根目录两个 config + SOURCES.md
│   ├── check_sources.py     # 每日复测逻辑
│   └── scan_github.py       # 每周扫描收录逻辑
├── reports/                 # 每日 / 每周报告 + status.json
├── check_history.json       # 连续失效计数（自动维护，自动移除线路的依据）
├── tvbox_config.json        # 接口产物：完整版（自动生成，勿手改）
├── tvbox_config_lite.json   # 接口产物：精简版（自动生成，勿手改）
├── SOURCES.md               # 线路清单（自动生成）
└── README.md
```

## 日常维护

- **加 / 删线路**：编辑 [config/sources.json](config/sources.json)（`name` / `url` / `compat` 三字段；`compat` 取值 `tvbox` / `fongmi` / `both`；加 `"lite": true` 可进精简版）→ push 后自动复测并重新生成
- **调整规则**：连续失效移除阈值在 `scripts/check_sources.py` 的 `DEAD_DAYS`；每周收录上限与门槛在 `scripts/scan_github.py` 顶部常量
- **本地手动运行**（可选，纯标准库零依赖）：`python scripts/check_sources.py`、`python scripts/scan_github.py --dry-run`

## 声明

内容均来自互联网公开仓库聚合，仅供个人学习测试自用，请于 24 小时内自行删除；线路随时可能失效，请勿用于任何商业用途。
