#!/usr/bin/env python3
"""
豆瓣个人数据导出工具
基于豆瓣移动端 Rexxar API，逆向自豆伴(tofu)扩展
"""

import argparse
import csv
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ── 尝试导入 browser_cookie3 ────────────────────────────────────────────────
try:
    import browser_cookie3
    HAS_BROWSER_COOKIE3 = True
except ImportError:
    HAS_BROWSER_COOKIE3 = False

# ── 常量 ────────────────────────────────────────────────────────────────────
BASE_URL = "https://m.douban.com/rexxar/api/v2"
INTERESTS_TYPES = ["movie", "book", "music", "game", "drama"]
INTERESTS_STATUSES = ["done", "wish", "doing"]
REVIEWS_TYPES = ["movie", "book", "music", "game", "drama"]
PAGE_SIZE = 50

# 输出目录
OUTPUT_DIR = Path("output")
RAW_DIR = OUTPUT_DIR / "raw"
CSV_DIR = OUTPUT_DIR / "csv"
MD_DIR = OUTPUT_DIR / "markdown"
PROGRESS_FILE = OUTPUT_DIR / "progress.json"

# ── 工具函数 ─────────────────────────────────────────────────────────────────

def log(msg: str):
    """带时间戳打印日志"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def ensure_dirs():
    """确保输出目录存在"""
    for d in [RAW_DIR, CSV_DIR, MD_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_progress() -> dict:
    """加载断点续传进度"""
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_progress(progress: dict):
    """保存进度到文件"""
    PROGRESS_FILE.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_raw(filename: str) -> list:
    """加载已有的原始 JSON（断点续传时复用）"""
    path = RAW_DIR / filename
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_raw(filename: str, data: list):
    """保存原始 JSON"""
    path = RAW_DIR / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Cookie 提取 ──────────────────────────────────────────────────────────────

def extract_cookies_from_browser() -> dict | None:
    """从 Chrome 自动提取豆瓣 Cookie"""
    if not HAS_BROWSER_COOKIE3:
        return None
    try:
        log("正在从 Chrome 提取豆瓣 Cookie...")
        jar = browser_cookie3.chrome(domain_name=".douban.com")
        cookies = {c.name: c.value for c in jar}
        required = {"dbcl2", "ck"}
        if required.issubset(cookies.keys()):
            log(f"Cookie 提取成功，找到: {', '.join(cookies.keys())}")
            return cookies
        log(f"Cookie 不完整，缺少: {required - cookies.keys()}")
        return None
    except Exception as e:
        log(f"自动提取 Cookie 失败: {e}")
        return None


def parse_cookie_string(cookie_str: str) -> dict:
    """解析手动输入的 cookie 字符串（格式：name=value;name2=value2）"""
    cookies = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            name, _, value = part.partition("=")
            cookies[name.strip()] = value.strip()
    return cookies


def extract_uid(cookies: dict) -> str | None:
    """从 dbcl2 cookie 解析 uid，格式为 '"uid:xxx"'"""
    dbcl2 = cookies.get("dbcl2", "")
    # 去除引号
    dbcl2 = dbcl2.strip('"').strip("'")
    if ":" in dbcl2:
        return dbcl2.split(":")[0]
    return None


# ── HTTP 请求 ────────────────────────────────────────────────────────────────

class DoubanClient:
    """豆瓣 API 客户端，封装请求、重试、限速"""

    def __init__(self, cookies: dict, interval: float = 3.0):
        self.cookies = cookies
        self.ck = cookies.get("ck", "")
        self.interval = interval
        self.session = requests.Session()
        self.session.cookies.update(cookies)
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
            ),
            "Referer": "https://m.douban.com/mine/",
            "X-Override-Referer": "https://m.douban.com/mine/",
            "Accept": "application/json, text/plain, */*",
        })

    def _sleep(self):
        """请求间隔 + 随机抖动"""
        jitter = random.uniform(-1.0, 1.0)
        delay = max(0.5, self.interval + jitter)
        time.sleep(delay)

    def get(self, url: str, params: dict = None, max_retry: int = 3) -> dict | None:
        """发送 GET 请求，遇到 429/403 自动重试"""
        if params is None:
            params = {}
        params.setdefault("ck", self.ck)
        params.setdefault("for_mobile", "1")

        for attempt in range(1, max_retry + 1):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code in (429, 403):
                    wait = 60 * attempt
                    log(f"  ⚠ HTTP {resp.status_code}，等待 {wait}s 后重试 ({attempt}/{max_retry})...")
                    time.sleep(wait)
                elif resp.status_code == 404:
                    log(f"  ⚠ HTTP 404，跳过: {url}")
                    return None
                else:
                    log(f"  ⚠ HTTP {resp.status_code}，尝试 {attempt}/{max_retry}")
                    time.sleep(10)
            except requests.RequestException as e:
                log(f"  ⚠ 请求异常: {e}，尝试 {attempt}/{max_retry}")
                time.sleep(10)

        log(f"  ✗ 请求失败，已放弃: {url}")
        return None

    def get_interests(self, uid: str, itype: str, status: str, start: int = 0) -> dict | None:
        """获取书影音标记"""
        url = f"{BASE_URL}/user/{uid}/interests"
        params = {
            "type": itype,
            "status": status,
            "start": start,
            "count": PAGE_SIZE,
        }
        self.session.headers["X-Override-Referer"] = f"https://m.douban.com/mine/{itype}"
        return self.get(url, params)

    def get_statuses(self, uid: str, max_id: str = "") -> dict | None:
        """获取广播/动态"""
        url = f"{BASE_URL}/status/user_timeline/{uid}"
        params = {}
        if max_id:
            params["max_id"] = max_id
        self.session.headers["X-Override-Referer"] = "https://m.douban.com/mine/status"
        return self.get(url, params)

    def get_status_detail(self, status_id: str) -> dict | None:
        """获取单条广播全文"""
        url = f"{BASE_URL}/status/{status_id}"
        return self.get(url)

    def get_reviews(self, uid: str, rtype: str, start: int = 0) -> dict | None:
        """获取长评"""
        url = f"{BASE_URL}/user/{uid}/reviews"
        params = {
            "type": rtype,
            "start": start,
            "count": PAGE_SIZE,
        }
        self.session.headers["X-Override-Referer"] = f"https://m.douban.com/mine/{rtype}"
        return self.get(url, params)

    def get_annotations(self, uid: str, start: int = 0) -> dict | None:
        """获取日记/笔记"""
        url = f"{BASE_URL}/user/{uid}/annotations"
        params = {
            "start": start,
            "count": PAGE_SIZE,
        }
        self.session.headers["X-Override-Referer"] = "https://m.douban.com/mine/"
        return self.get(url, params)


# ── 导出逻辑 ─────────────────────────────────────────────────────────────────

def export_interests(client: DoubanClient, uid: str, progress: dict,
                     filter_type: str = None):
    """导出书影音标记"""
    log("=" * 50)
    log("开始导出书影音标记 (interests)")

    types = [filter_type] if filter_type else INTERESTS_TYPES

    for itype in types:
        for status in INTERESTS_STATUSES:
            key = f"interests_{itype}_{status}"
            filename = f"{itype}_{status}.json"
            start = progress.get(key, 0)

            # 断点续传：加载已有数据
            all_items = load_raw(filename) if start > 0 else []

            log(f"  [{itype}/{status}] 从 start={start} 开始...")

            while True:
                data = client.get_interests(uid, itype, status, start)
                if not data:
                    break

                items = data.get("interests", [])
                total = data.get("total", 0)

                if not items:
                    break

                all_items.extend(items)
                start += len(items)
                progress[key] = start
                save_progress(progress)

                log(f"    已获取 {start}/{total} 条")

                # 每页保存一次
                save_raw(filename, all_items)

                if start >= total:
                    break

                client._sleep()

            log(f"  [{itype}/{status}] 完成，共 {len(all_items)} 条")
            save_raw(filename, all_items)

            # 生成 CSV
            _write_interests_csv(itype, status, all_items)


def export_statuses(client: DoubanClient, uid: str, progress: dict):
    """导出广播/动态"""
    log("=" * 50)
    log("开始导出广播/动态 (statuses)")

    key = "statuses_max_id"
    max_id = progress.get(key, "")
    filename = "statuses.json"

    all_items = load_raw(filename) if max_id else []
    log(f"  从 max_id={max_id or '最新'} 开始，已有 {len(all_items)} 条...")

    while True:
        data = client.get_statuses(uid, max_id)
        if not data:
            break

        items = data.get("items", [])
        if not items:
            log("  没有更多广播了")
            break

        # 过滤空广播：只保留有实际文字内容的条目
        MARK_ACTIVITIES = {"看过", "玩过", "读过", "听过", "想看", "想玩", "想读", "想听", "在看", "在玩", "在读", "在听"}
        filtered = []
        for item in items:
            status = item.get("status", {}) or item
            text = (status.get("text", "") or "").strip()
            activity = (status.get("activity", "") or "").strip()
            if text and not (activity in MARK_ACTIVITIES and len(text) < 5):
                filtered.append(item)
        all_items.extend(filtered)

        # 更新游标（最后一条的 id）
        last = items[-1]
        max_id = str(last.get("id", ""))
        progress[key] = max_id
        save_progress(progress)

        log(f"  已获取 {len(all_items)} 条广播，max_id={max_id}")
        save_raw(filename, all_items)

        # 检查是否还有更多
        if not data.get("has_next_page", True) or len(items) < 5:
            break

        client._sleep()

    log(f"  广播导出完成，共 {len(all_items)} 条")
    save_raw(filename, all_items)

    # 生成 Markdown
    _write_statuses_markdown(all_items)


def export_reviews(client: DoubanClient, uid: str, progress: dict,
                   filter_type: str = None):
    """导出长评"""
    log("=" * 50)
    log("开始导出长评 (reviews)")

    types = [filter_type] if filter_type else REVIEWS_TYPES

    for rtype in types:
        key = f"reviews_{rtype}"
        filename = f"reviews_{rtype}.json"
        start = progress.get(key, 0)

        all_items = load_raw(filename) if start > 0 else []
        log(f"  [{rtype}] 从 start={start} 开始...")

        while True:
            data = client.get_reviews(uid, rtype, start)
            if not data:
                break

            items = data.get("reviews", [])
            total = data.get("total", 0)

            if not items:
                break

            all_items.extend(items)
            start += len(items)
            progress[key] = start
            save_progress(progress)

            log(f"    已获取 {start}/{total} 条")
            save_raw(filename, all_items)

            if start >= total:
                break

            client._sleep()

        log(f"  [{rtype}] 完成，共 {len(all_items)} 条")
        save_raw(filename, all_items)

        # 生成 Markdown
        _write_reviews_markdown(rtype, all_items)


def export_annotations(client: DoubanClient, uid: str, progress: dict):
    """导出日记/笔记"""
    log("=" * 50)
    log("开始导出日记/笔记 (annotations)")

    key = "annotations"
    filename = "annotations.json"
    start = progress.get(key, 0)

    all_items = load_raw(filename) if start > 0 else []
    log(f"  从 start={start} 开始...")

    while True:
        data = client.get_annotations(uid, start)
        if not data:
            break

        items = data.get("annotations", [])
        total = data.get("total", 0)

        if not items:
            break

        all_items.extend(items)
        start += len(items)
        progress[key] = start
        save_progress(progress)

        log(f"  已获取 {start}/{total} 条")
        save_raw(filename, all_items)

        if start >= total:
            break

        client._sleep()

    log(f"  日记/笔记导出完成，共 {len(all_items)} 条")
    save_raw(filename, all_items)


# ── CSV / Markdown 生成 ───────────────────────────────────────────────────────

def _safe(v) -> str:
    """安全转字符串，处理 None"""
    return str(v) if v is not None else ""


def _write_interests_csv(itype: str, status: str, items: list):
    """生成书影音标记 CSV"""
    if not items:
        return
    path = CSV_DIR / f"{itype}_{status}.csv"

    # 动态提取字段，优先常用字段
    fieldnames = ["id", "title", "rating", "comment", "create_time", "url"]

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for item in items:
            subject = item.get("subject", {}) or {}
            row = {
                "id": _safe(subject.get("id")),
                "title": _safe(subject.get("title")),
                "rating": _safe((item.get("rating") or {}).get("value")),
                "comment": _safe(item.get("comment")),
                "create_time": _safe(item.get("create_time")),
                "url": _safe(subject.get("url")),
            }
            writer.writerow(row)


def _write_statuses_markdown(items: list):
    """广播/动态生成 Markdown"""
    if not items:
        return
    path = MD_DIR / "statuses.md"
    lines = ["# 豆瓣广播/动态导出\n"]
    for item in items:
        sid = item.get("id", "")
        created = item.get("created_at", "")
        text = item.get("text", "") or ""
        activity = item.get("activity", "") or ""
        lines.append(f"## [{created}] id={sid}")
        if activity:
            lines.append(f"**活动**: {activity}")
        lines.append("")
        lines.append(text)
        lines.append("")
        lines.append("---")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    log(f"  Markdown 已写入: {path}")


def _write_reviews_markdown(rtype: str, items: list):
    """长评生成 Markdown"""
    if not items:
        return
    path = MD_DIR / f"reviews_{rtype}.md"

    type_name = {
        "movie": "电影", "book": "书籍", "music": "音乐",
        "game": "游戏", "drama": "剧集"
    }.get(rtype, rtype)

    lines = [f"# 豆瓣{type_name}长评导出\n"]
    for item in items:
        title_val = (item.get("subject") or {}).get("title", "未知")
        created = item.get("created", "")
        review_title = item.get("title", "")
        abstract = item.get("abstract", "") or ""
        rating_val = (item.get("rating") or {}).get("value", "")
        url = item.get("url", "")

        lines.append(f"## {review_title or '（无标题）'}")
        lines.append(f"**作品**: {title_val}  ")
        lines.append(f"**评分**: {rating_val}  ")
        lines.append(f"**时间**: {created}  ")
        if url:
            lines.append(f"**链接**: {url}  ")
        lines.append("")
        lines.append(abstract)
        lines.append("")
        lines.append("---")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    log(f"  Markdown 已写入: {path}")


# ── 主入口 ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="豆瓣个人数据导出工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 douban_export.py                      # 导出全部
  python3 douban_export.py --type movie         # 只导出电影
  python3 douban_export.py --resume             # 从断点继续
  python3 douban_export.py --interval 5         # 请求间隔 5 秒
  python3 douban_export.py --cookie "dbcl2=xxx;ck=xxx"  # 手动指定 Cookie
        """,
    )
    parser.add_argument(
        "--type",
        choices=INTERESTS_TYPES,
        default=None,
        help="只导出指定类型（movie/book/music/game/drama）",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="从断点继续（读取 output/progress.json）",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=3.0,
        help="请求间隔秒数（默认 3 秒，实际 ±1 秒抖动）",
    )
    parser.add_argument(
        "--cookie",
        type=str,
        default=None,
        help="手动指定 Cookie 字符串，格式：dbcl2=xxx;ck=xxx",
    )
    parser.add_argument(
        "--no-statuses",
        action="store_true",
        help="跳过广播/动态导出",
    )
    parser.add_argument(
        "--no-reviews",
        action="store_true",
        help="跳过长评导出",
    )
    parser.add_argument(
        "--no-annotations",
        action="store_true",
        help="跳过日记/笔记导出",
    )

    args = parser.parse_args()

    # ── 初始化目录 ──────────────────────────────────────────────────────────
    ensure_dirs()

    # ── 获取 Cookie ─────────────────────────────────────────────────────────
    cookies = None

    if args.cookie:
        log("使用手动指定的 Cookie")
        cookies = parse_cookie_string(args.cookie)
    else:
        cookies = extract_cookies_from_browser()
        if not cookies:
            log("自动提取失败，请手动输入 Cookie")
            log("在浏览器登录豆瓣后，F12 → Application → Cookies → douban.com")
            cookie_input = input("请粘贴 Cookie 字符串（格式：dbcl2=xxx;ck=xxx）: ").strip()
            if not cookie_input:
                log("未输入 Cookie，退出")
                sys.exit(1)
            cookies = parse_cookie_string(cookie_input)

    # 验证必要 Cookie
    missing = {"dbcl2", "ck"} - cookies.keys()
    if missing:
        log(f"Cookie 缺少必要字段: {missing}")
        sys.exit(1)

    # 解析 uid
    uid = extract_uid(cookies)
    if not uid:
        log("无法从 dbcl2 解析 uid，请检查 Cookie 格式（dbcl2 值应为 \"uid:xxx\"）")
        sys.exit(1)

    log(f"用户 uid: {uid}")
    log(f"请求间隔: {args.interval}s ±1s")

    # ── 加载进度 ─────────────────────────────────────────────────────────────
    progress = {}
    if args.resume:
        progress = load_progress()
        log(f"断点续传模式，已有进度节点: {list(progress.keys())}")
    else:
        # 非 resume 模式：清空进度（但保留已有文件可被覆盖）
        save_progress({})

    # ── 创建客户端 ───────────────────────────────────────────────────────────
    client = DoubanClient(cookies, interval=args.interval)

    start_time = time.time()

    # ── 执行导出 ─────────────────────────────────────────────────────────────
    log(f"\n{'=' * 50}")
    log(f"豆瓣数据导出开始 — uid={uid}")
    log(f"{'=' * 50}\n")

    # 书影音标记
    export_interests(client, uid, progress, filter_type=args.type)

    # 广播/动态（--type 指定时也可导出，除非 --no-statuses）
    if not args.no_statuses:
        export_statuses(client, uid, progress)

    # 长评
    if not args.no_reviews:
        export_reviews(client, uid, progress, filter_type=args.type)

    # 日记/笔记
    if not args.no_annotations:
        export_annotations(client, uid, progress)

    # ── 汇总报告 ─────────────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    log(f"\n{'=' * 50}")
    log(f"导出完成！耗时 {elapsed:.0f}s")
    log(f"原始 JSON: {RAW_DIR}")
    log(f"CSV 汇总:  {CSV_DIR}")
    log(f"Markdown:  {MD_DIR}")
    log(f"{'=' * 50}")

    # 统计文件数量
    raw_files = list(RAW_DIR.glob("*.json"))
    total_items = 0
    for f in raw_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            total_items += len(data)
        except Exception:
            pass
    log(f"共导出 {total_items} 条记录，分布在 {len(raw_files)} 个文件")


if __name__ == "__main__":
    main()
