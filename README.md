# Douban Takeout 🥡

一键导出你的豆瓣个人数据。类似 Google Takeout，但给豆瓣用。

豆瓣没有官方数据导出功能，豆伴（Tofu）等浏览器扩展已年久失修。本工具基于豆瓣移动端 Rexxar API（逆向自豆伴源码），用 Python 脚本实现全量导出，稳定可靠。

**[English](#english)** | **中文**

## 支持导出的数据

| 类别 | 数据 | 状态 |
|------|------|------|
| 🎬 电影/剧集 | 看过、想看、在看 + 评分 + 短评 | ✅ |
| 📚 书 | 读过、想读、在读 + 评分 + 短评 | ✅ |
| 🎮 游戏 | 玩过、想玩、在玩 + 评分 + 短评 | ✅ |
| 🎵 音乐 | 听过、想听、在听 + 评分 + 短评 | ✅ |
| 🎭 舞台剧 | 看过、想看、在看 + 评分 + 短评 | ✅ |
| 📢 广播/动态 | 全部历史广播 | ✅ |
| 📝 长评 | 影评、书评、乐评、游戏评论 | ✅ |
| 📓 日记/笔记 | 读书笔记等 | ✅ |

## 输出格式

```
output/
├── raw/          # 原始 JSON（完整 API 数据，含作品元信息）
├── csv/          # CSV 汇总表格（标题、评分、短评、时间）
└── markdown/     # 广播和长评的 Markdown 全文
```

## 安装

```bash
# 克隆项目
git clone https://github.com/cytustse-cmd/douban-takeout.git
cd douban-takeout

# 安装依赖（requests 大概率已有）
pip install requests

# 可选：自动从 Chrome 提取 Cookie（macOS/Windows/Linux）
pip install browser-cookie3
```

**Python 版本要求：** 3.10+（使用了 `dict | None` 类型注解语法）

## 使用方法

### 方式一：自动提取 Cookie（推荐）

确保你已在 Chrome 登录了豆瓣，然后直接运行：

```bash
python3 douban_export.py
```

工具会自动从 Chrome 提取豆瓣 Cookie。

> ⚠️ macOS 可能弹出 Keychain 授权提示，允许即可。如果自动提取失败，用方式二。

### 方式二：手动指定 Cookie

1. 在 Chrome 打开 `https://www.douban.com`，确认已登录
2. 按 `F12` → **Application** → **Cookies** → `https://www.douban.com`
3. 找到 `dbcl2` 和 `ck` 两个 Cookie 的值
4. 运行：

```bash
python3 douban_export.py --cookie 'dbcl2="你的dbcl2值";ck=你的ck值'
```

### 更多选项

```bash
# 只导出电影数据
python3 douban_export.py --type movie

# 只导出游戏
python3 douban_export.py --type game

# 从断点继续（中断后恢复）
python3 douban_export.py --resume

# 加大请求间隔（降低被封风险）
python3 douban_export.py --interval 5

# 跳过广播导出（广播量大时很耗时）
python3 douban_export.py --no-statuses

# 跳过长评
python3 douban_export.py --no-reviews
```

## 实测数据

以下是真实账号的导出测试结果：

| 数据类型 | 条数 | 耗时 |
|----------|------|------|
| 电影（看过+想看+在看） | 4,094 | ~9 min |
| 游戏（玩过+想玩+在玩） | 565 | ~2 min |
| 书（读过+想读+在读） | 262 | ~1 min |
| 音乐 | 18 | <1 min |
| 广播/动态 | 6,090 | ~35 min |
| 长评 | 2 | <1 min |
| **总计** | **11,031** | **~50 min** |

全程零封禁，零数据丢失。API 返回总数与导出总数逐一对比完全一致。

## 技术原理

豆瓣移动端使用 Rexxar API（`m.douban.com/rexxar/api/v2`），返回结构化 JSON 数据。这套 API 是豆瓣移动网页版自身在用的，比桌面端 HTML 爬虫更稳定。

核心发现（逆向自 [豆伴/tofu](https://github.com/doufen-org/tofu) 源码）：
- 所有请求需要 `ck`（CSRF token）和 `for_mobile=1` 参数
- 需要设置 `Referer: https://m.douban.com/mine/` 和 `X-Override-Referer` 请求头
- 每页最多 50 条数据
- 广播使用 `max_id` 游标分页，其他使用 `start` 偏移分页

## 特性

- **断点续传** — 每页数据实时保存进度，中断后 `--resume` 继续
- **智能限速** — 默认 3 秒间隔 ± 1 秒随机抖动，模拟人类行为
- **自动重试** — 遇到 429/403 自动等待并重试，最多 3 次
- **三种输出** — JSON 原始数据 + CSV 表格 + Markdown 全文
- **零依赖** — 核心只需 `requests`，`browser-cookie3` 为可选

## 注意事项

- 本工具仅用于导出**你自己的**豆瓣数据，请勿用于爬取他人数据
- 请控制请求频率，建议间隔 ≥ 3 秒
- Cookie 有时效性，过期后需重新获取
- 广播量特别大（5000+）时，导出可能需要 30 分钟以上，请耐心等待
- 建议在网络稳定的环境下运行

## 常见问题

**Q: 提示 Cookie 缺少 `dbcl2`？**
A: `dbcl2` 是登录后才有的 Cookie。确认你已在浏览器登录豆瓣。`document.cookie` 读不到 `dbcl2`（它是 HttpOnly 的），需要在 DevTools → Application → Cookies 里手动复制。

**Q: 请求被 403 了？**
A: 请求太频繁触发了反爬。加大间隔 `--interval 10`，等几分钟后用 `--resume` 继续。

**Q: 导出的数据不完整？**
A: 用 `--resume` 从断点继续。检查 `output/progress.json` 查看各任务的进度。

**Q: macOS 上自动提取 Cookie 失败？**
A: Chrome 的 Cookie 数据库被 Keychain 加密，`browser-cookie3` 可能需要授权。如果反复失败，用 `--cookie` 手动指定。

## License

MIT

## 致谢

- [豆伴/tofu](https://github.com/doufen-org/tofu) — API 端点和请求头策略的灵感来源
- [豆瓣](https://www.douban.com) — 承载了无数人的精神世界

---

<a id="english"></a>

# Douban Takeout 🥡 (English)

Export all your personal data from [Douban](https://www.douban.com) — the Chinese platform for tracking movies, books, music, and games. Think Google Takeout, but for Douban.

Douban has no official data export feature, and browser extensions like Tofu (豆伴) are long abandoned. This tool uses Douban's mobile Rexxar API (reverse-engineered from the Tofu source code) to reliably export everything.

## What You Can Export

| Category | Data | Status |
|----------|------|--------|
| 🎬 Movies / TV | Watched, Want to Watch, Watching + Ratings + Short Reviews | ✅ |
| 📚 Books | Read, Want to Read, Reading + Ratings + Short Reviews | ✅ |
| 🎮 Games | Played, Want to Play, Playing + Ratings + Short Reviews | ✅ |
| 🎵 Music | Listened, Want to Listen, Listening + Ratings + Short Reviews | ✅ |
| 🎭 Drama / Theater | Watched, Want to Watch, Watching + Ratings + Short Reviews | ✅ |
| 📢 Statuses / Posts | Full timeline history | ✅ |
| 📝 Long Reviews | Movie, book, music, and game reviews | ✅ |
| 📓 Annotations / Notes | Reading notes, etc. | ✅ |

## Output Format

```
output/
├── raw/          # Raw JSON (complete API data with full metadata)
├── csv/          # CSV summaries (title, rating, comment, date)
└── markdown/     # Full-text Markdown for statuses and reviews
```

## Installation

```bash
git clone https://github.com/cytustse-cmd/douban-takeout.git
cd douban-takeout

# Install dependency (you probably already have requests)
pip install requests

# Optional: auto-extract cookies from Chrome (macOS/Windows/Linux)
pip install browser-cookie3
```

**Requires Python 3.10+** (uses `dict | None` type union syntax)

## Usage

### Option 1: Auto-extract Cookies (Recommended)

Make sure you're logged into Douban in Chrome, then run:

```bash
python3 douban_export.py
```

The tool will automatically extract Douban cookies from Chrome.

> ⚠️ On macOS, you may be prompted for Keychain access — allow it. If auto-extraction fails, use Option 2.

### Option 2: Manual Cookie

1. Open `https://www.douban.com` in Chrome (make sure you're logged in)
2. Press `F12` → **Application** → **Cookies** → `https://www.douban.com`
3. Copy the values of `dbcl2` and `ck`
4. Run:

```bash
python3 douban_export.py --cookie 'dbcl2="your_dbcl2_value";ck=your_ck_value'
```

### More Options

```bash
# Export only movies
python3 douban_export.py --type movie

# Export only games
python3 douban_export.py --type game

# Resume from checkpoint (after interruption)
python3 douban_export.py --resume

# Increase request interval (reduce ban risk)
python3 douban_export.py --interval 5

# Skip statuses (can be slow if you have thousands)
python3 douban_export.py --no-statuses

# Skip long reviews
python3 douban_export.py --no-reviews
```

## Real-World Test Results

Tested with a real account:

| Data Type | Records | Time |
|-----------|---------|------|
| Movies (watched + wishlist + watching) | 4,094 | ~9 min |
| Games (played + wishlist + playing) | 565 | ~2 min |
| Books (read + wishlist + reading) | 262 | ~1 min |
| Music | 18 | <1 min |
| Statuses / Posts | 6,090 | ~35 min |
| Long Reviews | 2 | <1 min |
| **Total** | **11,031** | **~50 min** |

Zero bans, zero data loss. API totals matched exported counts exactly.

## How It Works

Douban's mobile web uses the Rexxar API (`m.douban.com/rexxar/api/v2`), which returns structured JSON. This API powers Douban's own mobile site, making it far more stable than scraping desktop HTML.

Key findings (reverse-engineered from [Tofu/豆伴](https://github.com/doufen-org/tofu)):
- All requests require `ck` (CSRF token) and `for_mobile=1` parameters
- `Referer: https://m.douban.com/mine/` and `X-Override-Referer` headers are required
- Max 50 items per page
- Statuses use `max_id` cursor pagination; everything else uses `start` offset pagination

## Features

- **Resume from checkpoint** — Progress saved after every page; use `--resume` to continue after interruption
- **Smart rate limiting** — 3s default interval ± 1s random jitter to mimic human behavior
- **Auto-retry** — Waits and retries on 429/403 errors, up to 3 attempts
- **Triple output** — Raw JSON + CSV tables + Markdown full-text
- **Minimal dependencies** — Only `requests` required; `browser-cookie3` is optional

## Important Notes

- This tool is intended for exporting **your own** Douban data only — do not use it to scrape others' data
- Keep request intervals at 3 seconds or above
- Cookies expire over time; re-extract when needed
- If you have 5,000+ statuses, the export may take 30+ minutes — be patient
- Use a stable network connection

## FAQ

**Q: "Missing `dbcl2` cookie"?**
A: `dbcl2` only exists after login. Make sure you're logged into Douban. Note: `document.cookie` in the console **cannot** read `dbcl2` (it's HttpOnly) — you must copy it from DevTools → Application → Cookies.

**Q: Getting 403 errors?**
A: Too many requests triggered anti-scraping. Increase the interval with `--interval 10`, wait a few minutes, then `--resume`.

**Q: Incomplete data?**
A: Use `--resume` to continue from where it stopped. Check `output/progress.json` for progress details.

**Q: Cookie auto-extraction fails on macOS?**
A: Chrome's cookie database is encrypted via Keychain. `browser-cookie3` may need authorization. If it keeps failing, use `--cookie` to specify manually.

## License

MIT

## Acknowledgements

- [Tofu/豆伴](https://github.com/doufen-org/tofu) — Inspiration for API endpoints and request header strategies
- [Douban](https://www.douban.com) — Home to countless people's cultural lives
