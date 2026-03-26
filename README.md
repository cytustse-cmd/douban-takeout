<div align="center">

# douban-takeout

**Export your Douban data. All of it.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB.svg)](https://www.python.org)

[English](#english) | [中文](#中文)

</div>

---

<a id="english"></a>

## What is this

Douban has no official data export. Browser extensions like Tofu are abandoned.

**douban-takeout** uses a dual-engine approach — Rexxar API for structured data (ratings, reviews) and HTML scraping for statuses/posts — to fully export your Douban profile: ratings, reviews, statuses, notes, and images.

## Supported Data

| Type | Content | Engine |
|------|---------|--------|
| Movies / TV / Drama | Watched, Wishlist, Watching + Ratings + Comments | API |
| Books | Read, Wishlist, Reading + Ratings + Comments | API |
| Games | Played, Wishlist, Playing + Ratings + Comments | API |
| Music | Listened, Wishlist, Listening + Ratings + Comments | API |
| Original Posts | Full timeline + image download | Web |
| Activity Marks | Watched/Want to Watch records | Web |
| Long Reviews | Movie, book, music, game reviews | API |
| Notes | Reading notes, etc. | API |

## Quick Start

```bash
git clone https://github.com/cytustse-cmd/douban-takeout.git
cd douban-takeout
pip install requests browser-cookie3  # browser-cookie3 is optional

# 1. Ratings + reviews + notes
python3 douban_export.py --no-statuses

# 2. Statuses + images (web scraping bypasses API pagination limits)
python3 export_statuses_web.py
```

> **Requirements:** Python 3.10+, logged into Douban in your browser

<details>
<summary><b>More options</b></summary>

```bash
# Manual cookie input
python3 douban_export.py --cookie 'dbcl2="uid:xxx";ck=xxx'

# Export only movies
python3 douban_export.py --type movie

# Resume from checkpoint
python3 douban_export.py --resume

# Increase request interval (default 3s)
python3 douban_export.py --interval 5

# Custom output directory
python3 export_statuses_web.py --output ~/douban-backup

# Skip image download
python3 export_statuses_web.py --no-images
```

</details>

## Output Structure

```
output/
├── raw/                    # Raw JSON (full fields, ready for downstream use)
├── csv/                    # CSV summaries (sorted by date, newest first)
├── markdown/
│   ├── my_statuses.md      # Original posts only
│   ├── all_statuses.md     # All statuses including activity marks
│   └── reviews_*.md        # Long reviews by category
└── images/
    └── statuses/           # Status images (largest available size)
```

## Architecture

```
                    ┌─────────────────────┐
                    │   douban_export.py   │
                    │   (Rexxar API)       │
                    └────────┬────────────┘
                             │
  Cookie ──────┐             │  Ratings / Reviews / Notes
  (Safari →    │             ▼
   Chrome      │    ┌─────────────────────┐
   auto-detect)├───▶│   JSON / CSV /       │──▶  output/
               │    │   Markdown output    │
               │    └─────────────────────┘
               │             ▲
               │             │  Statuses / Posts / Images
               │    ┌────────┴────────────┐
               └───▶│export_statuses_web.py│
                    │   (HTML scraping)    │
                    └─────────────────────┘
```

Two scripts, one for each engine:

| | `douban_export.py` | `export_statuses_web.py` |
|:--|:--|:--|
| **Source** | Rexxar API (`m.douban.com`) | HTML (`www.douban.com`) |
| **Ratings** | Yes | — |
| **Reviews / Notes** | Yes | — |
| **Statuses** | Limited by API pagination | Full history |
| **Images** | — | Yes |

The Rexxar API returns structured JSON but hard-limits status pagination (~10 items for some accounts). The web scraper has no such limit.

**Recommended workflow:** `douban_export.py --no-statuses` then `export_statuses_web.py`

## Design

- **Resumable** — Progress checkpointed to `progress.json` per page/batch
- **Rate-limited** — 3s base interval ± 1s random jitter
- **Auto-retry** — Exponential backoff on 429/403
- **Recoverable images** — Failed downloads logged and retried on rerun
- **Portable output** — Markdown uses relative image paths; copy `output/` anywhere
- **Normalized dates** — All timestamps standardized to `YYYY-MM-DD`
- **Unified cookies** — Both scripts auto-detect Safari → Chrome

## Benchmarks

> From a real export of a heavy Douban user:

| Data | Count | Time |
|:-----|------:|-----:|
| Movies | 4,094 | ~9 min |
| Games | 565 | ~2 min |
| Books | 262 | ~1 min |
| Music | 18 | <1 min |
| Statuses | 763 | ~3 min |
| Images | 728 | ~6 min |
| **Total** | **~5,700 + 728 imgs** | **~22 min** |

## Changelog

### v0.3.1 (2026-03-25)

- **fix:** Use relative image paths in Markdown for portability
- **fix:** Retry failed image downloads on rerun
- **fix:** Normalize date formats to `YYYY-MM-DD` for stable sorting
- **fix:** Unify cookie extraction (Safari → Chrome) across both scripts
- **fix:** Deduplicate API status export, document Rexxar pagination limits

### v0.3.0 (2026-03-25)

- **feat:** Add `export_statuses_web.py` — HTML scraping engine for statuses
- **feat:** Separate original posts into `my_statuses.md`
- **feat:** Auto-download status images (largest size, with retry)
- **fix:** Sort CSV by date (newest first)

### v0.2.0 (2026-03-24)

- **fix:** Filter empty statuses

### v0.1.0 (2026-03-24)

- Initial release

## Acknowledgments

- [Tofu (doufen-org/tofu)](https://github.com/doufen-org/tofu) — Rexxar API reverse engineering reference
- [RSSHub](https://github.com/DIYgod/RSSHub) — Douban status route reference

## License

[MIT](LICENSE)

---

<a id="中文"></a>

<div align="center">

## 中文

</div>

## 简介

douban-takeout 是一个**豆瓣个人数据全量导出工具**。

豆瓣至今没有官方导出功能；豆伴等第三方扩展早已停更失效。本工具采用 Rexxar API + 网页抓取双引擎，一键导出书影音标记、广播说说、长评、日记及配图，输出为 JSON / CSV / Markdown 三种格式。

### 现有方案的问题

| 方案 | 缺陷 |
|------|------|
| 豆伴 (Tofu) | 已停更，Chrome Manifest V3 后彻底不可用 |
| 豆坟 (doufen) | 只能导出书影音，不支持广播和图片 |
| Rexxar API 直连 | 广播接口存在分页硬限制，部分账号仅返回 10 条 |

本工具以 API 处理结构化数据（书影音），以网页抓取覆盖广播全量历史，两套引擎互补，不留死角。

## 功能

| 类型 | 导出内容 | 引擎 |
|------|----------|------|
| 电影 / 剧集 / 舞台剧 | 看过、想看、在看 + 评分 + 短评 | API |
| 书籍 | 读过、想读、在读 + 评分 + 短评 | API |
| 游戏 | 玩过、想玩、在玩 + 评分 + 短评 | API |
| 音乐 | 听过、想听、在听 + 评分 + 短评 | API |
| 原创广播 | 全部历史动态 + 配图下载 | Web |
| 标记动态 | 看过 / 想看等标记记录 | Web |
| 长评 | 影评、书评、乐评、游戏评论 | API |
| 日记 | 读书笔记等 | API |

## 安装

```bash
git clone https://github.com/cytustse-cmd/douban-takeout.git
cd douban-takeout
pip install requests browser-cookie3  # browser-cookie3 可选，用于自动读取浏览器 Cookie
```

> **环境要求：** Python 3.10+；浏览器需已登录豆瓣

## 使用

```bash
# 导出书影音标记 + 长评 + 日记
python3 douban_export.py --no-statuses

# 导出广播动态 + 图片（网页抓取，无分页限制）
python3 export_statuses_web.py
```

<details>
<summary><b>高级选项</b></summary>

```bash
# 手动传入 Cookie（F12 → Application → Cookies → douban.com）
python3 douban_export.py --cookie 'dbcl2="uid:xxx";ck=xxx'

# 仅导出电影
python3 douban_export.py --type movie

# 断点续传
python3 douban_export.py --resume

# 调大请求间隔（默认 3s，被限速时建议 5–10s）
python3 douban_export.py --interval 5

# 指定输出目录
python3 export_statuses_web.py --output ~/douban-backup

# 跳过图片下载
python3 export_statuses_web.py --no-images
```

</details>

## 输出目录

```
output/
├── raw/                    # 原始 JSON，保留完整字段
│   ├── movie_done.json
│   ├── statuses_web.json
│   └── ...
├── csv/                    # CSV 汇总，按标记时间倒序
│   ├── movie_done.csv
│   └── ...
├── markdown/
│   ├── my_statuses.md      # 仅原创广播
│   ├── all_statuses.md     # 全部动态（含标记活动）
│   └── reviews_movie.md
└── images/
    └── statuses/           # 广播配图，自动选取最大尺寸
```

## 双引擎架构

```
                    ┌─────────────────────┐
                    │   douban_export.py   │
                    │     Rexxar API       │
                    └────────┬────────────┘
                             │
  Cookie ──────┐             │  书影音 / 长评 / 日记
  (自动检测    │             ▼
   Safari →    │    ┌─────────────────────┐
   Chrome)     ├───▶│   JSON / CSV /       │──▶  output/
               │    │     Markdown         │
               │    └─────────────────────┘
               │             ▲
               │             │  广播 / 说说 / 配图
               │    ┌────────┴────────────┐
               └───▶│export_statuses_web.py│
                    │     HTML 抓取        │
                    └─────────────────────┘
```

| | `douban_export.py` | `export_statuses_web.py` |
|:--|:--|:--|
| **数据源** | Rexxar API (`m.douban.com`) | HTML (`www.douban.com`) |
| **书影音标记** | ✓ | — |
| **长评 / 日记** | ✓ | — |
| **广播动态** | 受 API 分页限制 | 完整历史 |
| **图片下载** | — | ✓ |

Rexxar API 返回结构化 JSON，适合处理书影音标记；但其广播接口存在分页硬限制，部分账号仅返回约 10 条。网页抓取不受此限制，可导出完整广播历史。

**推荐用法：** 先 `douban_export.py --no-statuses` 导出书影音，再 `export_statuses_web.py` 导出广播和图片。

## 特性

- **断点续传** — 逐页保存进度，中断后 `--resume` 接续运行
- **智能限速** — 3s 基础间隔 ± 1s 随机抖动，降低触发风控的概率
- **失败重试** — 遇到 429 / 403 自动退避重试，不丢数据
- **图片恢复** — 下载失败记录至 `failed_images.json`，重跑时自动重试
- **可移植输出** — Markdown 内图片引用为相对路径，整目录拷贝即可渲染
- **时间归一** — 统一为 `YYYY-MM-DD` 格式，排序不受中文日期干扰
- **Cookie 统一** — 两个脚本均自动检测 Safari → Chrome，行为一致

## 实测

> 数据来自一个标记 5,000+ 条目的重度用户账号：

| 类型 | 数量 | 耗时 |
|:-----|-----:|-----:|
| 电影 | 4,094 | ~9 min |
| 游戏 | 565 | ~2 min |
| 书籍 | 262 | ~1 min |
| 音乐 | 18 | <1 min |
| 广播 | 763 | ~3 min |
| 图片 | 728 张 | ~6 min |
| **合计** | **~5,700 + 728 图** | **~22 min** |

## 注意

- 仅用于导出**本人**的豆瓣数据，请勿用于批量采集他人信息
- 控制请求频率，建议间隔不低于 3 秒
- Cookie 存在有效期，过期后需重新登录浏览器获取

## 更新日志

<details>
<summary><b>展开查看</b></summary>

#### v0.3.1 (2026-03-25)

- **fix:** Markdown 图片路径改用相对路径，支持整目录迁移
- **fix:** 图片下载失败后重跑自动重试，不再永久跳过
- **fix:** 时间格式归一为 `YYYY-MM-DD`，修复中文日期导致的排序异常
- **fix:** Cookie 检测逻辑统一为 Safari → Chrome，两脚本行为一致
- **fix:** API 广播导出增加去重逻辑及分页限制说明

#### v0.3.0 (2026-03-25)

- **feat:** 新增 `export_statuses_web.py`，通过网页抓取绕过 API 分页限制
- **feat:** 原创广播单独导出至 `my_statuses.md`
- **feat:** 支持广播配图自动下载（优先大图，失败自动重试）
- **fix:** CSV 按标记时间倒序排列

#### v0.2.0 (2026-03-24)

- **fix:** 过滤空白广播条目

#### v0.1.0 (2026-03-24)

- 首次发布

</details>

## 致谢

- [豆伴 / tofu](https://github.com/doufen-org/tofu) — Rexxar API 逆向参考
- [RSSHub](https://github.com/DIYgod/RSSHub) — 豆瓣广播路由参考

## 许可

[MIT](LICENSE)
