# Douban Takeout 🥡

一键导出你的豆瓣个人数据。类似 Google Takeout，但给豆瓣用。

豆瓣没有官方数据导出功能，豆伴（Tofu）等浏览器扩展已年久失修。本工具基于豆瓣移动端 Rexxar API + 网页抓取双引擎，用 Python 脚本实现全量导出，稳定可靠。

**[English](#english)** | **中文**

## 支持导出的数据

| 类别 | 数据 | 方式 | 状态 |
|------|------|------|------|
| 🎬 电影/剧集 | 看过、想看、在看 + 评分 + 短评 | API | ✅ |
| 📚 书 | 读过、想读、在读 + 评分 + 短评 | API | ✅ |
| 🎮 游戏 | 玩过、想玩、在玩 + 评分 + 短评 | API | ✅ |
| 🎵 音乐 | 听过、想听、在听 + 评分 + 短评 | API | ✅ |
| 🎭 舞台剧 | 看过、想看、在看 + 评分 + 短评 | API | ✅ |
| 📢 原创广播/说说 | 全部历史动态 + 图片下载 | 网页抓取 | ✅ |
| 📢 标记动态 | 看过/想看等标记活动 + 短评 | 网页抓取 | ✅ |
| 📝 长评 | 影评、书评、乐评、游戏评论 | API | ✅ |
| 📓 日记/笔记 | 读书笔记等 | API | ✅ |

## 输出格式

```
output/
├── raw/                    # 原始 JSON（完整数据，含作品元信息）
│   ├── movie_done.json     # 电影-看过
│   ├── statuses_web.json   # 全部广播（网页抓取版）
│   └── ...
├── csv/                    # CSV 汇总表格（按时间倒序排列）
│   ├── movie_done.csv      # 标题、评分、短评、时间
│   └── ...
├── markdown/               # Markdown 全文
│   ├── my_statuses.md      # 仅原创广播/说说
│   ├── all_statuses.md     # 全部广播（含标记活动）
│   └── reviews_movie.md    # 长评
└── images/
    └── statuses/           # 广播中的图片（优先大图）
```

## 安装

```bash
git clone https://github.com/cytustse-cmd/douban-takeout.git
cd douban-takeout

# 安装依赖
pip install requests

# 可选：自动从浏览器提取 Cookie（macOS Safari / Chrome）
pip install browser-cookie3
```

**Python 版本要求：** 3.10+

## 使用方法

### 导出书影音标记 + 长评 + 日记

```bash
# 自动从浏览器提取 Cookie
python3 douban_export.py

# 手动指定 Cookie
python3 douban_export.py --cookie 'dbcl2="你的dbcl2值";ck=你的ck值'

# 只导出电影
python3 douban_export.py --type movie

# 从断点继续
python3 douban_export.py --resume

# 加大请求间隔
python3 douban_export.py --interval 5
```

### 导出广播/动态 + 图片（推荐）

```bash
# 自动从浏览器提取 Cookie（Safari → Chrome），抓取全部广播 + 下载图片
python3 export_statuses_web.py

# 手动指定 Cookie
python3 export_statuses_web.py --cookie 'dbcl2="xxx";ck=xxx'

# 自定义输出目录
python3 export_statuses_web.py --output ~/douban-backup

# 跳过图片下载（只要文字和 JSON）
python3 export_statuses_web.py --no-images

# 加大请求间隔
python3 export_statuses_web.py --interval 5
```

> **为什么广播单独一个脚本？** 豆瓣 Rexxar API 对广播分页有限制（部分账号只返回 10 条），网页抓取版 (`export_statuses_web.py`) 通过直接解析 HTML 页面绕过了这个限制，可以完整导出所有广播，包括原创说说和图片。

## 实测数据

| 数据类型 | 条数 | 耗时 |
|----------|------|------|
| 电影（看过+想看+在看） | 4,094 | ~9 min |
| 游戏（玩过+想玩+在玩） | 565 | ~2 min |
| 书（读过+想读+在读） | 262 | ~1 min |
| 音乐 | 18 | <1 min |
| 广播/动态（网页版） | 763 | ~3 min |
| 图片下载 | 728 张 | ~6 min |
| 长评 | 2 | <1 min |
| **总计** | **~5,700 + 728 图** | **~22 min** |

## 两个脚本对比

| | `douban_export.py` | `export_statuses_web.py` |
|---|---|---|
| 数据源 | Rexxar API | 网页 HTML |
| 书影音标记 | ✅ | ❌ |
| 长评/日记 | ✅ | ❌ |
| 原创广播 | ⚠️ 可能被 API 限制 | ✅ 完整 |
| 标记动态 | ⚠️ 可能被 API 限制 | ✅ 完整 |
| 图片下载 | ❌ | ✅ |
| CSV 排序 | ✅ 按时间倒序 | — |

**推荐组合**：先跑 `douban_export.py --no-statuses` 导出书影音，再跑 `export_statuses_web.py` 导出广播和图片。

## 技术原理

### 书影音标记（API）
豆瓣移动端 Rexxar API（`m.douban.com/rexxar/api/v2`），返回结构化 JSON。逆向自 [豆伴/tofu](https://github.com/doufen-org/tofu) 源码。

### 广播/动态（网页抓取）
直接请求 `www.douban.com/people/{uid}/statuses?p={page}`，解析 HTML 提取广播内容。原因：
- Rexxar API 对部分账号有分页限制（只返回 10 条）
- 原创广播的文本在 `card.subtitle` 而非 `text` 字段，API 解析不稳定
- 网页版无此限制，且能正确区分原创广播和标记活动

## 特性

- **断点续传** — 每页实时保存进度，中断后 `--resume` 继续
- **智能限速** — 默认 3 秒间隔 ± 1 秒随机抖动
- **自动重试** — 429/403 自动等待重试
- **图片下载** — 广播图片自动下载，失败记录到 `failed_images.json`，重跑自动重试
- **CSV 按时间排序** — 所有 CSV 按标记时间倒序排列
- **原创广播独立输出** — `my_statuses.md` 仅包含你发的说说
- **零依赖** — 核心只需 `requests`，`browser-cookie3` 为可选

## 注意事项

- 本工具仅用于导出**你自己的**豆瓣数据
- 请控制请求频率，建议间隔 ≥ 3 秒
- Cookie 有时效性，过期后需重新获取
- 建议在网络稳定的环境下运行

## 迭代进程

### v0.3.1 (2026-03-25)
- **修复** Markdown 图片路径改为相对路径（`../images/statuses/`），确保可移植
- **修复** 失败图片不再被永久跳过，重跑自动重试
- **修复** 时间格式统一为 `YYYY-MM-DD`，解决 "3月19日" 等中文格式导致排序不稳定
- **修复** Cookie 提取统一为 Safari → Chrome 自动检测，两个脚本行为一致
- **修复** API 版广播导出增加去重逻辑和限制说明（Rexxar API 仅返回最近 ~10 条）

### v0.3.0 (2026-03-25)
- **新增** `export_statuses_web.py` — 网页抓取版广播导出，绕过 API 分页限制
- **新增** 原创广播（说说）独立导出到 `my_statuses.md`
- **新增** 广播图片自动下载（优先大图，失败重试 + 记录）
- **修复** CSV 文件按标记时间倒序排列
- **修复** 广播 Markdown 生成：正确读取嵌套的 `status` 字段和 `card.subtitle`
- **修复** 分页游标：从 `item.status.id` 取值而非顶层 `item.id`

### v0.2.0 (2026-03-24)
- 过滤空广播，只保留有实际文字内容的条目
- 新增英文 README

### v0.1.0 (2026-03-24)
- 首次发布：支持全量导出书影音标记、广播、长评、日记

## License

MIT

## 致谢

- [豆伴/tofu](https://github.com/doufen-org/tofu) — API 端点和请求头策略的灵感来源
- [RSSHub](https://github.com/DIYgod/RSSHub) — 豆瓣广播 route 的参考
- [豆瓣](https://www.douban.com) — 承载了无数人的精神世界

---

<a id="english"></a>

# Douban Takeout 🥡 (English)

Export all your personal data from [Douban](https://www.douban.com) — the Chinese platform for tracking movies, books, music, and games. Think Google Takeout, but for Douban.

Douban has no official data export feature. This tool uses a dual-engine approach: Rexxar API for structured data (ratings, reviews) and web scraping for statuses/posts (including images).

## What You Can Export

| Category | Data | Method | Status |
|----------|------|--------|--------|
| 🎬 Movies / TV | Watched, Wishlist, Watching + Ratings + Reviews | API | ✅ |
| 📚 Books | Read, Wishlist, Reading + Ratings + Reviews | API | ✅ |
| 🎮 Games | Played, Wishlist, Playing + Ratings + Reviews | API | ✅ |
| 🎵 Music | Listened, Wishlist, Listening + Ratings + Reviews | API | ✅ |
| 🎭 Drama | Watched, Wishlist, Watching + Ratings + Reviews | API | ✅ |
| 📢 Original Posts | Full timeline + image download | Web Scrape | ✅ |
| 📢 Activity Marks | Watched/Want to Watch marks + comments | Web Scrape | ✅ |
| 📝 Long Reviews | Movie, book, music, game reviews | API | ✅ |
| 📓 Notes | Reading notes, etc. | API | ✅ |

## Output Structure

```
output/
├── raw/                    # Raw JSON (full data with metadata)
│   ├── movie_done.json
│   ├── statuses_web.json   # All statuses (web scraping)
│   └── ...
├── csv/                    # CSV summaries (sorted by date, newest first)
│   ├── movie_done.csv      # Title, rating, comment, date
│   └── ...
├── markdown/               # Markdown exports
│   ├── my_statuses.md      # Original posts only
│   ├── all_statuses.md     # All statuses (including activity marks)
│   └── reviews_movie.md    # Long reviews
└── images/
    └── statuses/           # Status images (large size preferred)
```

## Quick Start

```bash
git clone https://github.com/cytustse-cmd/douban-takeout.git
cd douban-takeout
pip install requests browser-cookie3

# Export ratings, reviews, notes (API)
python3 douban_export.py --no-statuses

# Export statuses + images (web scraping)
python3 export_statuses_web.py
```

**Python 3.10+ required.**

> **Why two scripts?** The Rexxar API has a pagination limit for statuses (only ~10 items for some accounts). The web scraper (`export_statuses_web.py`) parses HTML pages directly to bypass this limitation, exporting all statuses including original posts and images.

## Two Scripts Compared

| | `douban_export.py` | `export_statuses_web.py` |
|---|---|---|
| Data source | Rexxar API | Web HTML |
| Ratings (movies/books/games/music) | Yes | No |
| Reviews / Notes | Yes | No |
| Original posts | Limited by API | Full history |
| Activity marks | Limited by API | Full history |
| Image download | No | Yes |

**Recommended workflow**: Run `douban_export.py --no-statuses` for ratings, then `export_statuses_web.py` for statuses and images.

## Features

- **Resumable** — Progress saved per page; resume with `--resume`
- **Smart rate limiting** — 3s interval with ±1s jitter
- **Auto retry** — Retries on 429/403 with backoff
- **Image download** — Auto-downloads status images; failures are retried on rerun
- **Portable Markdown** — Image links use relative paths
- **Cookie auto-detection** — Tries Safari then Chrome automatically
- **Original posts separated** — `my_statuses.md` contains only your own posts
- **Minimal dependencies** — Only `requests` required; `browser-cookie3` optional

## Changelog

### v0.3.1 (2026-03-25)
- **Fixed** Markdown image paths now use relative paths for portability
- **Fixed** Failed image downloads are retried on rerun (no longer permanently skipped)
- **Fixed** Date format normalized to `YYYY-MM-DD` for stable sorting
- **Fixed** Cookie extraction unified: Safari → Chrome auto-detection in both scripts
- **Fixed** API status export now deduplicates and warns about Rexxar API limitations

### v0.3.0 (2026-03-25)
- **Added** `export_statuses_web.py` — web scraping for statuses, bypassing API pagination limits
- **Added** Original posts exported separately to `my_statuses.md`
- **Added** Auto image download (large size preferred, with retry + failure logging)
- **Fixed** CSV files sorted by date (newest first)

### v0.2.0 (2026-03-24)
- Filter empty statuses

### v0.1.0 (2026-03-24)
- Initial release

## License

MIT
