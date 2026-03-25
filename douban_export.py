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
        """获取广播/动态（含原创说说、转发、标记活动等全部类型）"""
        url = f"{BASE_URL}/status/user_timeline/{uid}"
        params = {"ck": self.ck, "for_mobile": "1"}
        if max_id:
            params["max_id"] = max_id
        self.session.headers["X-Override-Referer"] = "https://m.douban.com/mine/status"
        return self.get(url, params)

    def get_my_statuses(self, uid: str, start: int = 0) -> dict | None:
        """获取用户原创广播（说说），不含标记活动。
        注意：豆瓣没有独立的原创广播端点，原创广播混在 user_timeline 中，
        通过 activity 为空 + card.subtitle 有内容来识别。此方法保留作为备用。"""
        return None

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

        # 保留所有条目（含原创广播、标记活动等）
        # 原创广播的文字在 card.subtitle 而非 text 中
        all_items.extend(items)

        # 更新游标（id 在 item.status.id 中，非顶层）
        last = items[-1]
        last_status = last.get("status", {}) or {}
        max_id = str(last_status.get("id", "") or last.get("id", ""))
        progress[key] = max_id
        save_progress(progress)

        log(f"  已获取 {len(all_items)} 条广播，max_id={max_id}")
        save_raw(filename, all_items)

        # 检查是否还有更多（API 无 has_next_page 字段，用返回条数判断）
        if len(items) < 5:
            break

        client._sleep()

    log(f"  广播导出完成，共 {len(all_items)} 条")
    save_raw(filename, all_items)

    # 生成 Markdown
    _write_statuses_markdown(all_items)


def export_my_statuses(client: DoubanClient, uid: str, progress: dict):
    """从已抓取的 statuses 数据中筛选原创广播，下载图片，生成独立 Markdown。
    原创广播特征：activity 为空，内容在 card.subtitle 中。"""
    log("=" * 50)
    log("开始处理原创广播/说说 (my_statuses)")

    # 从已有的 statuses.json 读取
    all_statuses = load_raw("statuses.json")
    if not all_statuses:
        log("  ⚠ 没有 statuses 数据，请先运行 export_statuses")
        return

    # 筛选原创广播 + 下载图片
    original = []
    for item in all_statuses:
        status = item.get("status", {}) or item
        activity = (status.get("activity", "") or "").strip()
        text = _extract_status_text(status)
        if not activity and text:
            original.append(item)

    log(f"  从 {len(all_statuses)} 条动态中筛选出 {len(original)} 条原创广播")

    if original:
        # 下载原创广播的图片
        _download_original_images(client, original)
        # 生成独立的原创广播 Markdown
        _write_my_statuses_markdown(original)


def _download_original_images(client: DoubanClient, items: list):
    """下载原创广播中的图片"""
    img_dir = OUTPUT_DIR / "images" / "statuses"
    img_dir.mkdir(parents=True, exist_ok=True)
    failed_path = OUTPUT_DIR / "failed_images.json"

    total_images = 0
    downloaded = 0
    skipped = 0
    failed = []

    for item in items:
        status = item.get("status", {}) or item
        sid = str(status.get("id", ""))
        img_urls = _extract_status_images(status)

        for idx, url in enumerate(img_urls):
            total_images += 1
            ext = ".jpg"
            if ".png" in url:
                ext = ".png"
            elif ".gif" in url:
                ext = ".gif"
            elif ".webp" in url:
                ext = ".webp"

            img_path = img_dir / f"{sid}_{idx}{ext}"
            if img_path.exists():
                skipped += 1
                downloaded += 1
                continue

            success = False
            for attempt in range(1, 3):
                try:
                    resp = client.session.get(url, timeout=30)
                    if resp.status_code == 200:
                        img_path.write_bytes(resp.content)
                        downloaded += 1
                        success = True
                        break
                    elif resp.status_code in (429, 403):
                        time.sleep(30 * attempt)
                    else:
                        break
                except Exception:
                    time.sleep(5)

            if not success:
                failed.append({"sid": sid, "idx": idx, "url": url})

            time.sleep(0.5)

    if failed:
        failed_path.write_text(
            json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log(f"  ⚠ {len(failed)} 张图片下载失败，���记录到 {failed_path}")

    log(f"  图片下载完成: {downloaded}/{total_images}（跳过已存在 {skipped}）")



def _write_my_statuses_markdown(items: list):
    """原创广播生成 Markdown（从 statuses 中筛选 activity 为空的）"""
    if not items:
        return
    path = MD_DIR / "my_statuses.md"
    lines = ["# 豆瓣原创广播/说说\n"]

    # 筛选原创广播：activity 为空的条目
    original = []
    for item in items:
        status = item.get("status", {}) or item
        activity = (status.get("activity", "") or "").strip()
        text = _extract_status_text(status)
        if not activity and text:
            original.append(status)

    sorted_items = sorted(
        original,
        key=lambda x: x.get("create_time", ""),
        reverse=True,
    )

    img_dir_rel = "../images/statuses"

    for status in sorted_items:
        sid = status.get("id", "")
        created = status.get("create_time", "")
        text = _extract_status_text(status)

        lines.append(f"## [{created}] id={sid}")
        lines.append("")
        if text:
            lines.append(text)
            lines.append("")

        # 图片引用
        img_urls = _extract_status_images(status)
        for idx, url in enumerate(img_urls):
            ext = ".jpg"
            if ".png" in url:
                ext = ".png"
            elif ".gif" in url:
                ext = ".gif"
            elif ".webp" in url:
                ext = ".webp"
            lines.append(f"![img]({img_dir_rel}/{sid}_{idx}{ext})")
        if img_urls:
            lines.append("")

        lines.append("---")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    log(f"  Markdown 已写入: {path}（{len(original)} 条原创广播）")


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
        # 按标记时间倒序排列（最新的在前）
        sorted_items = sorted(
            items,
            key=lambda x: x.get("create_time", ""),
            reverse=True,
        )
        for item in sorted_items:
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


def _extract_status_text(status: dict) -> str:
    """从 status 对象提取文本内容。
    豆瓣原创广播的文字在 card.subtitle，标记活动的短评在 text。"""
    text = (status.get("text", "") or "").strip()
    if not text:
        card = status.get("card") or {}
        text = (card.get("subtitle", "") or "").strip()
    return text


def _extract_status_images(status: dict) -> list[str]:
    """从 status 对象提取图片 URL 列表（优先大图）。"""
    urls = []
    # 方式1：status.images
    for img in (status.get("images") or []):
        url = (img.get("large", {}) or {}).get("url") or \
              (img.get("normal", {}) or {}).get("url") or \
              img.get("url", "")
        if url:
            urls.append(url)
    # 方式2：card.image（原创广播可能图片在 card 里）
    if not urls:
        card = status.get("card") or {}
        card_img = card.get("image")
        if isinstance(card_img, dict):
            url = (card_img.get("large", {}) or {}).get("url") or \
                  (card_img.get("normal", {}) or {}).get("url") or \
                  card_img.get("url", "")
            if url:
                urls.append(url)
        elif isinstance(card_img, str) and card_img:
            urls.append(card_img)
    return urls


def _write_statuses_markdown(items: list):
    """广播/动态生成 Markdown"""
    if not items:
        return
    path = MD_DIR / "statuses.md"
    lines = ["# 豆瓣广播/动态导出\n"]
    # 按时间倒序排列
    sorted_items = sorted(
        items,
        key=lambda x: (x.get("status", {}) or {}).get("create_time", ""),
        reverse=True,
    )
    for item in sorted_items:
        status = item.get("status", {}) or item
        sid = status.get("id", "")
        created = status.get("create_time", "")
        text = _extract_status_text(status)
        activity = (status.get("activity", "") or "").strip()
        if not text:
            continue
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

    # 原创广播/说说（含图片）
    if not args.no_statuses:
        export_my_statuses(client, uid, progress)

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
