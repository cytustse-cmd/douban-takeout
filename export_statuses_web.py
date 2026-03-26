#!/usr/bin/env python3
"""
豆瓣广播/动态导出工具（网页抓取版）
抓取 https://www.douban.com/people/{uid}/statuses 页面，导出原创广播和标记活动
"""

import argparse
import html
import json
import os
import re
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

# ── 常量 ─────────────────────────────────────────────────────────────────────
STATUSES_URL = "https://www.douban.com/people/{uid}/statuses"
PAGE_SIZE = 20  # 每页固定 20 条

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def log(msg: str):
    """带时间戳打印日志"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def ensure_dirs(output_dir: Path):
    """确保输出目录存在"""
    for d in [
        output_dir / "raw",
        output_dir / "markdown",
        output_dir / "images" / "statuses",
    ]:
        d.mkdir(parents=True, exist_ok=True)


def load_progress(output_dir: Path) -> dict:
    """加载断点续传进度"""
    progress_file = output_dir / "progress.json"
    if progress_file.exists():
        try:
            return json.loads(progress_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_progress(output_dir: Path, progress: dict):
    """保存进度到文件"""
    progress_file = output_dir / "progress.json"
    progress_file.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_raw(output_dir: Path, filename: str) -> list:
    """加载已有的原始 JSON"""
    path = output_dir / "raw" / filename
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_raw(output_dir: Path, filename: str, data: list):
    """保存原始 JSON"""
    path = output_dir / "raw" / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Cookie 提取 ───────────────────────────────────────────────────────────────

def extract_cookies_from_browser() -> dict | None:
    """从浏览器自动提取豆瓣 Cookie（依次尝试 Safari → Chrome）"""
    if not HAS_BROWSER_COOKIE3:
        return None
    for browser_name, browser_fn in [("Safari", browser_cookie3.safari), ("Chrome", browser_cookie3.chrome)]:
        try:
            log(f"正在从 {browser_name} 提取豆瓣 Cookie...")
            jar = browser_fn(domain_name=".douban.com")
            cookies = {c.name: c.value for c in jar}
            if "ck" not in cookies:
                cookies["ck"] = "wwpi"
            if "dbcl2" in cookies:
                log(f"Cookie 提取成功（{browser_name}），找到: {', '.join(cookies.keys())}")
                return cookies
            log(f"{browser_name} Cookie 不完整，缺少 dbcl2")
        except Exception as e:
            log(f"{browser_name} 提取失败: {e}")
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
    dbcl2 = dbcl2.strip('"').strip("'")
    if ":" in dbcl2:
        return dbcl2.split(":")[0]
    return None


# ── HTML 解析工具 ─────────────────────────────────────────────────────────────

def strip_tags(text: str) -> str:
    """去除 HTML 标签，<br> 转换为换行"""
    # 先把 <br> 系列转换为换行
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # 去除其余标签
    text = re.sub(r"<[^>]+>", "", text)
    return text


def decode_html(text: str) -> str:
    """解码 HTML 实体，并处理特殊字符"""
    return html.unescape(text)


def clean_text(text: str) -> str:
    """清理文本：去标签 -> 解码实体 -> 去首尾空白"""
    text = strip_tags(text)
    text = decode_html(text)
    # 合并多余空行（超过两个换行压缩为两个）
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def upgrade_image_url(url: str) -> str:
    """将豆瓣图片 URL 从中图(/m/)升级为大图(/l/)"""
    # 替换 /view/photo/m/ 或 /img.../m/ 等路径中的 /m/ 为 /l/
    url = re.sub(r"/photo/m/", "/photo/l/", url)
    url = re.sub(r"/(m)/", "/l/", url)
    # 常见格式：img1.doubanio.com/view/photo/m/public/...
    url = re.sub(r"(img\d*\.doubanio\.com/view/photo)/m/", r"\1/l/", url)
    return url


# ── 网页抓取 ──────────────────────────────────────────────────────────────────

class StatusesWebClient:
    """豆瓣广播网页抓取客户端"""

    def __init__(self, cookies: dict, interval: float = 3.0):
        self.cookies = cookies
        self.interval = interval
        self.session = requests.Session()
        self.session.cookies.update(cookies)
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": "https://www.douban.com/",
        })

    def _sleep(self):
        """请求间隔 + 随机抖动"""
        jitter = random.uniform(-1.0, 1.0)
        delay = max(0.5, self.interval + jitter)
        time.sleep(delay)

    def get_page(self, uid: str, page: int, max_retry: int = 3) -> str | None:
        """获取广播列表页 HTML"""
        url = STATUSES_URL.format(uid=uid)
        params = {"p": page}
        for attempt in range(1, max_retry + 1):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    return resp.text
                elif resp.status_code in (429, 403):
                    wait = 60 * attempt
                    log(f"  ⚠ HTTP {resp.status_code}，等待 {wait}s 后重试 ({attempt}/{max_retry})...")
                    time.sleep(wait)
                elif resp.status_code == 404:
                    log(f"  ⚠ HTTP 404，页面不存在: {url}")
                    return None
                else:
                    log(f"  ⚠ HTTP {resp.status_code}，尝试 {attempt}/{max_retry}")
                    time.sleep(10)
            except requests.RequestException as e:
                log(f"  ⚠ 请求异常: {e}，尝试 {attempt}/{max_retry}")
                time.sleep(10)
        log(f"  ✗ 页面 {page} 抓取失败，跳过")
        return None

    def download_image(self, url: str, dest: Path, max_retry: int = 2) -> bool:
        """下载单张图片，失败重试"""
        if dest.exists():
            return True
        for attempt in range(1, max_retry + 1):
            try:
                resp = self.session.get(url, timeout=30, stream=True)
                if resp.status_code == 200:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with open(dest, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    return True
                else:
                    log(f"    ⚠ 图片 HTTP {resp.status_code}，尝试 {attempt}/{max_retry}: {url}")
                    time.sleep(2)
            except requests.RequestException as e:
                log(f"    ⚠ 图片下载异常: {e}，尝试 {attempt}/{max_retry}: {url}")
                time.sleep(2)
        return False


# ── HTML 解析：广播列表页 ─────────────────────────────────────────────────────

def parse_statuses_page(html_text: str, uid: str) -> list[dict]:
    """
    从广播列表页 HTML 中解析所有 status-item。
    返回结构化的 status 列表。
    """
    statuses = []

    # 提取所有 status-item 块
    # 每条广播：<div class="status-item" data-sid="...">...</div>
    item_pattern = re.compile(
        r'<div[^>]*class="[^"]*status-item[^"]*"[^>]*data-sid="(\d+)"[^>]*>(.*?)</div>\s*</div>\s*</div>',
        re.DOTALL
    )

    # 用更宽松的方式切分：找到每个 status-item 的起始位置，逐段提取
    # 先找所有 data-sid
    sid_positions = [(m.group(1), m.start()) for m in re.finditer(
        r'<div[^>]*class="[^"]*status-item[^"]*"[^>]*data-sid="(\d+)"', html_text
    )]

    if not sid_positions:
        return []

    # 按位置切分 HTML，提取每段
    for i, (sid, start) in enumerate(sid_positions):
        # 截取到下一个 status-item 开始位置（或文档末尾）
        end = sid_positions[i + 1][1] if i + 1 < len(sid_positions) else len(html_text)
        chunk = html_text[start:end]

        status = parse_single_status(chunk, sid, uid)
        if status:
            statuses.append(status)

    return statuses


def parse_single_status(chunk: str, sid: str, uid: str) -> dict | None:
    """解析单条广播 HTML 片段"""
    # ── 时间 ──
    # <span class="created_at" title="2026-03-19 12:34:56">3月19日</span>
    create_time = ""
    time_m = re.search(r'<span[^>]*class="[^"]*created_at[^"]*"[^>]*title="([^"]+)"', chunk)
    if time_m:
        create_time = time_m.group(1).strip()
        # 只取日期部分
        create_time = create_time.split(" ")[0]
    else:
        # 没有 title 属性时，取文本内容并尝试转为 YYYY-MM-DD
        time_m2 = re.search(r'<span[^>]*class="[^"]*created_at[^"]*"[^>]*>(.*?)</span>', chunk, re.DOTALL)
        if time_m2:
            raw_time = clean_text(time_m2.group(1))
            # 尝试解析 "3月19日" 或 "2025-03-19" 格式
            cn_m = re.match(r'(\d{1,2})月(\d{1,2})日', raw_time)
            if cn_m:
                month, day = int(cn_m.group(1)), int(cn_m.group(2))
                year = datetime.now().year
                create_time = f"{year}-{month:02d}-{day:02d}"
            else:
                create_time = raw_time

    # ── activity（标记活动：看过/想看/读过/玩过等）──
    # activity 文本紧跟在 <a class="lnk-people">用户名</a> 后面
    KNOWN_ACTIVITIES = {"看过", "玩过", "读过", "听过", "想看", "想玩", "想读", "想听", "在看", "在玩", "在读", "在听"}
    activity = ""
    act_m = re.search(r'class="lnk-people">[^<]+</a>\s*\n?\s*(\S+)', chunk)
    if act_m and act_m.group(1) in KNOWN_ACTIVITIES:
        activity = act_m.group(1)

    # ── 文字内容 ──
    text = ""

    # 原创广播：<div class="status-saying">...</div>
    saying_m = re.search(
        r'<div[^>]*class="[^"]*status-saying[^"]*"[^>]*>(.*?)</div>',
        chunk, re.DOTALL
    )
    if saying_m:
        text = clean_text(saying_m.group(1))

    # 标记活动的短评在 blockquote 中
    blockquote_m = re.search(r'<blockquote[^>]*>(.*?)</blockquote>', chunk, re.DOTALL)
    if blockquote_m:
        bq_text = clean_text(blockquote_m.group(1))
        if bq_text:
            if text:
                text = text + "\n" + bq_text
            else:
                text = bq_text

    # ── 图片 ──
    images = []
    # 豆瓣广播图片通常在 img*.doubanio.com
    img_pattern = re.compile(r'<img[^>]*src="(https?://img\d*\.doubanio\.com/[^"]+)"', re.IGNORECASE)
    for img_m in img_pattern.finditer(chunk):
        img_url = img_m.group(1)
        # 过滤头像等小图（通常带 icon/avatar/userpic 路径）
        if any(kw in img_url for kw in ["/userpic/", "/icon/", "/avatar/"]):
            continue
        # 升级为大图
        img_url = upgrade_image_url(img_url)
        if img_url not in images:
            images.append(img_url)

    # ── 构建广播 URL ──
    url = f"https://www.douban.com/people/{uid}/status/{sid}/"

    return {
        "id": sid,
        "create_time": create_time,
        "activity": activity,
        "text": text,
        "images": images,
        "url": url,
    }


# ── 主抓取流程 ────────────────────────────────────────────────────────────────

def fetch_all_statuses(
    client: StatusesWebClient,
    uid: str,
    output_dir: Path,
    progress: dict,
) -> list[dict]:
    """抓取所有广播，支持断点续传"""
    all_statuses = load_raw(output_dir, "statuses_web.json")
    seen_ids = {s["id"] for s in all_statuses}

    start_page = progress.get("statuses_web_page", 1)
    log(f"开始抓取广播，从第 {start_page} 页开始（已有 {len(all_statuses)} 条）")

    page = start_page
    consecutive_empty = 0

    while True:
        log(f"  抓取第 {page} 页...")
        html_text = client.get_page(uid, page)

        if html_text is None:
            log(f"  第 {page} 页获取失败，停止")
            break

        page_statuses = parse_statuses_page(html_text, uid)
        log(f"  第 {page} 页解析到 {len(page_statuses)} 条广播")

        if len(page_statuses) == 0:
            consecutive_empty += 1
            if consecutive_empty >= 2:
                log("  连续 2 页为空，抓取完毕")
                break
        else:
            consecutive_empty = 0

        new_count = 0
        for status in page_statuses:
            if status["id"] not in seen_ids:
                all_statuses.append(status)
                seen_ids.add(status["id"])
                new_count += 1

        log(f"  第 {page} 页新增 {new_count} 条（累计 {len(all_statuses)} 条）")

        # 保存进度
        progress["statuses_web_page"] = page + 1
        save_progress(output_dir, progress)
        save_raw(output_dir, "statuses_web.json", all_statuses)

        if len(page_statuses) < PAGE_SIZE:
            log("  最后一页（条数不足），抓取完毕")
            break

        page += 1
        client._sleep()

    # 抓取完成，重置页码
    progress["statuses_web_page"] = 1
    save_progress(output_dir, progress)

    return all_statuses


# ── 图片下载 ──────────────────────────────────────────────────────────────────

def download_images(
    client: StatusesWebClient,
    statuses: list[dict],
    output_dir: Path,
):
    """下载所有广播图片"""
    img_dir = output_dir / "images" / "statuses"
    failed_file = output_dir / "failed_images.json"

    total_images = sum(len(s["images"]) for s in statuses)
    log(f"开始下载图片，共 {total_images} 张...")

    downloaded = 0
    skipped = 0
    fail_count = 0
    failed = []

    for status in statuses:
        sid = status["id"]
        for idx, img_url in enumerate(status["images"]):
            # 提取扩展名
            ext = "jpg"
            ext_m = re.search(r"\.([a-zA-Z0-9]+)(?:\?|$)", img_url)
            if ext_m:
                ext = ext_m.group(1).lower()
                if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
                    ext = "jpg"

            dest = img_dir / f"{sid}_{idx}.{ext}"
            if dest.exists():
                skipped += 1
                continue

            ok = client.download_image(img_url, dest)
            if ok:
                downloaded += 1
                log(f"  ✓ 图片 {sid}_{idx}.{ext}")
            else:
                fail_count += 1
                failed.append({"sid": sid, "idx": idx, "url": img_url})
                log(f"  ✗ 图片下载失败: {img_url}")

            time.sleep(0.5)

    # 保存失败列表（每次重新生成，重跑时会自动重试）
    if failed:
        failed_file.write_text(
            json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    elif failed_file.exists():
        failed_file.unlink()

    log(f"图片下载完成：下载 {downloaded} 张，跳过 {skipped} 张，失败 {fail_count} 张")


# ── Markdown 生成 ─────────────────────────────────────────────────────────────

def format_status_md(status: dict, img_dir: Path | None = None) -> str:
    """将单条广播格式化为 Markdown"""
    lines = []

    # 标题行：时间 + activity
    header = f"### {status['create_time']}"
    if status["activity"]:
        header += f" · {status['activity']}"
    lines.append(header)
    lines.append("")

    if status["text"]:
        lines.append(status["text"])
        lines.append("")

    # 图片（使用相对于 markdown 文件的路径）
    img_rel_dir = "../images/statuses"
    for idx, img_url in enumerate(status["images"]):
        ext = "jpg"
        ext_m = re.search(r"\.([a-zA-Z0-9]+)(?:\?|$)", img_url)
        if ext_m:
            ext = ext_m.group(1).lower()
            if ext not in ("jpg", "jpeg", "png", "gif", "webp"):
                ext = "jpg"
        filename = f"{status['id']}_{idx}.{ext}"
        if img_dir and (img_dir / filename).exists():
            lines.append(f"![图片]({img_rel_dir}/{filename})")
        else:
            lines.append(f"![图片]({img_url})")

    lines.append("")
    lines.append(f"[原文链接]({status['url']})")
    lines.append("")
    lines.append("---")
    lines.append("")

    return "\n".join(lines)


def generate_markdown(statuses: list[dict], output_dir: Path):
    """生成 Markdown 文件"""
    md_dir = output_dir / "markdown"
    img_dir = output_dir / "images" / "statuses"

    # 按时间排序（新到旧）
    sorted_statuses = sorted(statuses, key=lambda s: s["create_time"], reverse=True)

    # my_statuses.md — 仅原创广播（activity 为空）
    original = [s for s in sorted_statuses if not s["activity"]]
    my_md_path = md_dir / "my_statuses.md"
    with open(my_md_path, "w", encoding="utf-8") as f:
        f.write("# 我的广播（原创）\n\n")
        f.write(f"共 {len(original)} 条原创广播\n\n---\n\n")
        for status in original:
            f.write(format_status_md(status, img_dir))
    log(f"原创广播 Markdown 已保存: {my_md_path}（{len(original)} 条）")

    # all_statuses.md — 全部广播
    all_md_path = md_dir / "all_statuses.md"
    with open(all_md_path, "w", encoding="utf-8") as f:
        f.write("# 全部广播\n\n")
        f.write(f"共 {len(sorted_statuses)} 条广播\n\n---\n\n")
        for status in sorted_statuses:
            f.write(format_status_md(status, img_dir))
    log(f"全部广播 Markdown 已保存: {all_md_path}（{len(sorted_statuses)} 条）")


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="豆瓣广播导出工具（网页抓取版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output", "-o",
        default="./output",
        help="输出目录（默认 ./output）",
    )
    parser.add_argument(
        "--cookie",
        default=None,
        help='手动指定 Cookie 字符串，格式：dbcl2="uid:xxx";ck=wwpi',
    )
    parser.add_argument(
        "--interval", "-i",
        type=float,
        default=3.0,
        help="请求间隔秒数（默认 3 秒）",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="跳过图片下载",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    ensure_dirs(output_dir)

    # ── 获取 Cookie ──
    if args.cookie:
        cookies = parse_cookie_string(args.cookie)
        log("使用手动指定的 Cookie")
    else:
        cookies = extract_cookies_from_browser()
        if not cookies:
            log("❌ 无法获取 Cookie，请使用 --cookie 手动传入")
            log('  示例：--cookie \'dbcl2="123456:xxx";ck=wwpi\'')
            sys.exit(1)

    # 确保 ck 存在
    if "ck" not in cookies:
        cookies["ck"] = "wwpi"

    # ── 提取 UID ──
    uid = extract_uid(cookies)
    if not uid:
        log("❌ 无法从 Cookie 中解析 uid，请检查 dbcl2 cookie 是否正确")
        sys.exit(1)
    log(f"用户 UID: {uid}")

    # ── 初始化客户端 ──
    client = StatusesWebClient(cookies=cookies, interval=args.interval)

    # ── 加载进度 ──
    progress = load_progress(output_dir)

    # ── 抓取广播 ──
    log("=" * 50)
    log("开始导出豆瓣广播（网页抓取版）")
    log("=" * 50)

    statuses = fetch_all_statuses(client, uid, output_dir, progress)
    log(f"共抓取 {len(statuses)} 条广播")

    # ── 下载图片 ──
    if not args.no_images:
        download_images(client, statuses, output_dir)
    else:
        log("已跳过图片下载（--no-images）")

    # ── 生成 Markdown ──
    generate_markdown(statuses, output_dir)

    log("=" * 50)
    log("导出完成！")
    log(f"  原始数据: {output_dir}/raw/statuses_web.json")
    log(f"  原创广播: {output_dir}/markdown/my_statuses.md")
    log(f"  全部广播: {output_dir}/markdown/all_statuses.md")
    if not args.no_images:
        log(f"  图片目录: {output_dir}/images/statuses/")
    log("=" * 50)


if __name__ == "__main__":
    main()
