#!/usr/bin/env python3
"""
build_obsidian_vault.py
=======================

将 output/raw/ 下的 Rexxar API JSON 转换为 Obsidian 友好的「图文并茂」
Markdown 视图——分类目录、中文文件名、本地封面缩略图。

依赖：纯标准库（无需 pip 安装额外包）。
前置：先跑过 `python3 douban_export.py --no-statuses ...`，
      生成 output/raw/{movie,book,game,music}_{done,doing,wish}.json。

用法：
    python3 build_obsidian_vault.py --vault /path/to/标记记录
    python3 build_obsidian_vault.py --vault ./vault --no-covers
    python3 build_obsidian_vault.py --vault ./vault --workers 16

输出结构：
    {vault}/
    ├── _索引.md
    ├── covers/{movie,book,game,music}/{id}.jpg
    ├── 电影/   看过.md 在看.md 想看.md
    ├── 书籍/   读过.md 在读.md 想读.md
    ├── 游戏/   玩过.md 在玩.md 想玩.md
    └── 音乐/   听过.md 想听.md
"""
from __future__ import annotations

import argparse
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CATEGORY = {"movie": "电影", "book": "书籍", "game": "游戏", "music": "音乐"}
ZH_STATUS = {
    "movie": {"done": "看过", "doing": "在看", "wish": "想看"},
    "book":  {"done": "读过", "doing": "在读", "wish": "想读"},
    "game":  {"done": "玩过", "doing": "在玩", "wish": "想玩"},
    "music": {"done": "听过", "doing": "在听", "wish": "想听"},
}
CAT_ORDER = ["movie", "book", "game", "music"]
STATUS_ORDER = ["done", "doing", "wish"]
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15")


def esc(s) -> str:
    if s is None:
        return ""
    return str(s).replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def stars(rating) -> str:
    try:
        n = int(rating)
        if 1 <= n <= 5:
            return "★" * n + "☆" * (5 - n)
    except (TypeError, ValueError):
        pass
    return "—"


def pick_cover_url(subject: dict | None) -> str | None:
    if not subject:
        return None
    pic = subject.get("pic") or {}
    return pic.get("normal") or pic.get("large") or subject.get("cover_url")


def safe_id(item: dict) -> str | None:
    s = item.get("subject") or {}
    sid = s.get("id") or item.get("id")
    return str(sid) if sid else None


def load_raw(raw_dir: Path, cat: str, status: str) -> list[dict]:
    fp = raw_dir / f"{cat}_{status}.json"
    if not fp.exists():
        return []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("interests") or data.get("items") or []
    return []


class CoverDownloader:
    def __init__(self, covers_dir: Path, workers: int = 8):
        self.covers_dir = covers_dir
        self.workers = workers
        self.lock = threading.Lock()
        self.done = 0
        self.total = 0

    def _progress(self):
        with self.lock:
            self.done += 1
            if self.done % 50 == 0 or self.done == self.total:
                print(f"    封面进度 {self.done}/{self.total}")

    def _download_one(self, url: str, path: Path) -> bool:
        if path.exists() and path.stat().st_size > 0:
            self._progress()
            return True
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            req = Request(url, headers={"User-Agent": UA, "Referer": "https://www.douban.com/"})
            with urlopen(req, timeout=20) as r:
                data = r.read()
            path.write_bytes(data)
            self._progress()
            return True
        except (URLError, HTTPError, TimeoutError, OSError):
            self._progress()
            return False

    def run(self, mapping: dict[tuple[str, str], str]) -> tuple[int, int]:
        tasks = []
        for (cat, sid), url in mapping.items():
            ext = ".jpg"
            m = re.search(r"\.(jpg|jpeg|png|webp)(?:\?|$)", url, re.I)
            if m:
                ext = "." + m.group(1).lower()
            tasks.append((url, self.covers_dir / cat / f"{sid}{ext}"))
        self.total = len(tasks)
        self.done = 0
        if not tasks:
            return 0, 0
        print(f"  待下载封面 {self.total} 张（{self.workers} 线程）")
        ok = fail = 0
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for fut in as_completed([pool.submit(self._download_one, u, p) for u, p in tasks]):
                if fut.result():
                    ok += 1
                else:
                    fail += 1
        return ok, fail


def collect_covers(raw_dir: Path) -> dict[tuple[str, str], str]:
    mapping: dict[tuple[str, str], str] = {}
    for cat in CAT_ORDER:
        for status in STATUS_ORDER:
            for item in load_raw(raw_dir, cat, status):
                sid = safe_id(item)
                if not sid:
                    continue
                url = pick_cover_url(item.get("subject"))
                if url:
                    mapping[(cat, sid)] = url
    return mapping


def find_cover_relpath(covers_dir: Path, cat: str, sid: str | None) -> str | None:
    if not sid:
        return None
    d = covers_dir / cat
    if not d.exists():
        return None
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = d / f"{sid}{ext}"
        if p.exists() and p.stat().st_size > 0:
            return f"../covers/{cat}/{p.name}"
    return None


def write_md(vault: Path, covers_dir: Path, cat: str, status: str, items: list[dict]) -> int:
    cat_zh = CATEGORY[cat]
    status_zh = ZH_STATUS[cat][status]
    sub = vault / cat_zh
    sub.mkdir(exist_ok=True)
    items.sort(key=lambda r: r.get("create_time", "") or "", reverse=True)

    lines = [
        f"# {cat_zh} · {status_zh}",
        "",
        f"共 **{len(items)}** 条 · 按标记时间倒序",
        "",
        "| 封面 | 时间 | 标题 | 评分 | 短评 |",
        "|---|---|---|---|---|",
    ]
    for it in items:
        s = it.get("subject") or {}
        sid = safe_id(it)
        date = (it.get("create_time", "") or "")[:10]
        title = esc(s.get("title") or s.get("cn_name") or "")
        url = s.get("url") or (f"https://www.douban.com/{cat}/{sid}/" if sid else "")
        title_link = f"[{title}]({url})" if url else title
        rating = it.get("rating") or {}
        rt = stars(rating.get("value")) if isinstance(rating, dict) else "—"
        comment = esc(it.get("comment", "")) or "—"
        rel = find_cover_relpath(covers_dir, cat, sid)
        cover_md = f'<img src="{rel}" width="60">' if rel else "—"
        lines.append(f"| {cover_md} | {date} | {title_link} | {rt} | {comment} |")
    (sub / f"{status_zh}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(items)


def write_index(vault: Path, stats: dict[tuple[str, str], int]) -> None:
    lines = ["# 豆瓣标记记录", "", "> 由 douban-takeout 自动生成 · 图文并茂版", ""]
    for cat in CAT_ORDER:
        if not any((cat, s) in stats for s in STATUS_ORDER):
            continue
        lines.append(f"## {CATEGORY[cat]}")
        lines.append("")
        for s in STATUS_ORDER:
            if (cat, s) in stats:
                n = stats[(cat, s)]
                z = ZH_STATUS[cat][s]
                lines.append(f"- [[{CATEGORY[cat]}/{z}|{z} ({n})]]")
        lines.append("")
    (vault / "_索引.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="将豆瓣 raw JSON 转为 Obsidian 图文 Markdown vault")
    p.add_argument("--raw", default="output/raw", help="raw JSON 目录（默认 output/raw）")
    p.add_argument("--vault", required=True, help="输出 vault 目录（如 ~/Vault/豆瓣资料/标记记录）")
    p.add_argument("--workers", type=int, default=8, help="封面下载并发数（默认 8）")
    p.add_argument("--no-covers", action="store_true", help="跳过封面下载，只生成 Markdown")
    args = p.parse_args()

    raw_dir = Path(args.raw).expanduser().resolve()
    vault = Path(args.vault).expanduser().resolve()
    if not raw_dir.exists():
        raise SystemExit(f"raw 目录不存在: {raw_dir}\n请先运行 douban_export.py")
    vault.mkdir(parents=True, exist_ok=True)
    covers_dir = vault / "covers"

    print(f"raw   : {raw_dir}")
    print(f"vault : {vault}")

    if args.no_covers:
        print("[1/2] 跳过封面下载")
    else:
        print("[1/2] 收集封面 URL")
        mapping = collect_covers(raw_dir)
        print(f"  共 {len(mapping)} 个条目带封面")
        ok, fail = CoverDownloader(covers_dir, workers=args.workers).run(mapping)
        print(f"  下载完成: 成功 {ok} 失败 {fail}")

    print("[2/2] 生成 Markdown")
    stats: dict[tuple[str, str], int] = {}
    for cat in CAT_ORDER:
        for status in STATUS_ORDER:
            items = load_raw(raw_dir, cat, status)
            if not items:
                continue
            n = write_md(vault, covers_dir, cat, status, items)
            stats[(cat, status)] = n
            print(f"  {CATEGORY[cat]}/{ZH_STATUS[cat][status]}.md  ({n} 条)")
    write_index(vault, stats)
    print(f"完成: {vault / '_索引.md'}")


if __name__ == "__main__":
    main()
