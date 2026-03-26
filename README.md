<div align="center">

# douban-takeout

**Export your Douban data. All of it.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB.svg)](https://www.python.org)

[中文](#中文) | [English](#english)

</div>

---

<a id="中文"></a>

## 这是什么

豆瓣没有官方数据导出功能。豆伴（Tofu）等浏览器扩展已年久失修。

**douban-takeout** 通过逆向豆瓣移动端 Rexxar API + 网页抓取双引擎，完整导出你的书影音标记、广播动态、长评、日记和图片。类似 Google Takeout，但给豆瓣用。

### 为什么造这个轮子

| 现有方案 | 问题 |
|----------|------|
| 豆伴 (Tofu) | 停更，Chrome 扩展机制变更后不可用 |
| 豆坟 (doufen) | 仅导出书影音，不支持广播 |
| Rexxar API 直连 | 广播分页有硬限制，部分账号只返回 10 条 |

douban-takeout 用 API 处理结构化数据（书影音），用网页抓取处理广播（绕过 API 分页限制），两者互补。

## 支持的数据类型

| 类型 | 内容 | 引擎 |
|------|------|------|
| 电影 / 剧集 / 舞台剧 | 看过、想看、在看 + 评分 + 短评 | API |
| 书 | 读过、想读、在读 + 评分 + 短评 | API |
| 游戏 | 玩过、想玩、在玩 + 评分 + 短评 | API |
| 音乐 | 听过、想听、在听 + 评分 + 短评 | API |
| 原创广播 / 说说 | 全部历史 + 配图下载 | Web |
| 标记动态 | 看过/想看等活动记录 | Web |
| 长评 | 影评、书评、乐评、游戏评论 | API |
| 日记 / 笔记 | 读书笔记等 | API |

## 快速开始

```bash
git clone https://github.com/cytustse-cmd/douban-takeout.git
cd douban-takeout
pip install requests browser-cookie3  # browser-cookie3 可选，用于自动提取 Cookie
```

> **前提条件：** Python 3.10+，浏览器已登录豆瓣

**一条命令导出全部：**

```bash
# 1. 书影音 + 长评 + 日记
python3 douban_export.py --no-statuses

# 2. 广播 + 图片（推荐用网页版，API 有分页限制）
python3 export_statuses_web.py
```

<details>
<summary><b>更多用法</b></summary>

```bash
# 手动指定 Cookie（浏览器 F12 → Application → Cookies → douban.com）
python3 douban_export.py --cookie 'dbcl2="uid:xxx";ck=xxx'

# 只导出电影
python3 douban_export.py --type movie

# 断点续传
python3 douban_export.py --resume

# 加大请求间隔（默认 3s，建议被限速时调到 5-10s）
python3 douban_export.py --interval 5

# 广播：自定义输出目录
python3 export_statuses_web.py --output ~/douban-backup

# 广播：跳过图片下载
python3 export_statuses_web.py --no-images
```

</details>

## 输出结构

```
output/
├── raw/                    # 原始 JSON（完整字段，可二次开发）
│   ├── movie_done.json
│   ├── statuses_web.json
│   └── ...
├── csv/                    # CSV（按标记时间倒序）
│   ├── movie_done.csv
│   └── ...
├── markdown/
│   ├── my_statuses.md      # 仅原创广播
│   ├── all_statuses.md     # 全部动态
│   └── reviews_movie.md
└── images/
    └── statuses/           # 广播配图（自动选择最大尺寸）
```

## 架构

```
                    ┌─────────────────────┐
                    │   douban_export.py   │
                    │   (Rexxar API 引擎)  │
                    └────────┬────────────┘
                             │
  Cookie ──────┐             │  书影音 / 长评 / 日记
  (Safari →    │             ▼
   Chrome      │    ┌─────────────────────┐
   自动检测)   ├───▶│     JSON / CSV /     │──▶  output/
               │    │     Markdown 输出    │
               │    └─────────────────────┘
               │             ▲
               │             │  广播 / 说说 / 图片
               │    ┌────────┴────────────┐
               └───▶│export_statuses_web.py│
                    │  (HTML 抓取引擎)     │
                    └─────────────────────┘
```

### 为什么是两个脚本

| | `douban_export.py` | `export_statuses_web.py` |
|:--|:--|:--|
| **数据源** | Rexxar API (`m.douban.com`) | HTML (`www.douban.com`) |
| **书影音标记** | ✓ | — |
| **长评 / 日记** | ✓ | — |
| **广播动态** | 受 API 分页限制 | 完整历史 |
| **图片下载** | — | ✓ |

Rexxar API 返回结构化 JSON，适合书影音标记；但对广播分页有硬限制（部分账号仅返回 ~10 条）。网页抓取无此限制。

**推荐工作流：** `douban_export.py --no-statuses` → `export_statuses_web.py`

## 设计细节

- **断点续传** — 每页/每批保存进度至 `progress.json`，中断后 `--resume` 恢复
- **智能限速** — 3s 基础间隔 ± 1s 随机抖动，模拟人类行为
- **自动重试** — HTTP 429/403 指数退避重试，临时失败不丢数据
- **图片可恢复** — 下载失败记录到 `failed_images.json`，重跑自动重试
- **可移植输出** — Markdown 使用相对路径引用图片，拷贝整个 `output/` 即可渲染
- **时间规范化** — 所有时间统一为 `YYYY-MM-DD`，确保排序稳定
- **Cookie 统一** — 两个脚本均自动检测 Safari → Chrome，行为一致

## 实测数据

> 以下数据来自一个重度豆瓣用户账号的实际导出：

| 数据类型 | 条数 | 耗时 |
|:---------|-----:|-----:|
| 电影（看过 + 想看 + 在看） | 4,094 | ~9 min |
| 游戏 | 565 | ~2 min |
| 书 | 262 | ~1 min |
| 音乐 | 18 | <1 min |
| 广播 / 动态 | 763 | ~3 min |
| 图片 | 728 张 | ~6 min |
| **合计** | **~5,700 条 + 728 图** | **~22 min** |

## 注意事项

- 本工具仅用于导出**你自己的**豆瓣数据，请勿用于批量抓取他人信息
- 请遵守豆瓣使用条款，控制请求频率（建议 ≥ 3s）
- Cookie 有时效性，过期后需重新登录浏览器并重新获取

## Changelog

### v0.3.1 (2026-03-25)

- **fix:** Markdown 图片路径改为相对路径，确保可移植
- **fix:** 失败图片重跑自动重试，不再永久跳过
- **fix:** 时间格式统一 `YYYY-MM-DD`，修复中文日期排序问题
- **fix:** Cookie 提取统一 Safari → Chrome，两脚本行为一致
- **fix:** API 广播导出增加去重和限制说明

### v0.3.0 (2026-03-25)

- **feat:** 新增 `export_statuses_web.py` — 网页抓取引擎，绕过 API 分页限制
- **feat:** 原创广播独立导出至 `my_statuses.md`
- **feat:** 广播图片自动下载（优先大图 + 失败重试）
- **fix:** CSV 按标记时间倒序
- **fix:** 修复广播 Markdown 字段解析和分页游标

### v0.2.0 (2026-03-24)

- **fix:** 过滤空广播

### v0.1.0 (2026-03-24)

- 首次发布

## 致谢

- [豆伴 / tofu](https://github.com/doufen-org/tofu) — Rexxar API 端点逆向参考
- [RSSHub](https://github.com/DIYgod/RSSHub) — 豆瓣广播 route 参考

## License

[MIT](LICENSE)

---

<a id="english"></a>

<div align="center">

## English

</div>

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
