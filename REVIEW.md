# Review Notes

Date: 2026-03-26
Repo: `cytustse-cmd/douban-takeout`
Scope: static review only, no source changes in this PR

## Findings

### 1. Broken local image links in generated Markdown
- Severity: high
- Location: `export_statuses_web.py:505-510`
- Problem: `format_status_md()` writes image links using `local_path = img_dir / ...` directly. `img_dir` is `output_dir / "images" / "statuses"`, while the markdown files are written under `output_dir / "markdown"`.
- Effect: when `--output` is relative, the generated links become `output/images/...` inside a file already located in `output/markdown/`, so many Markdown renderers resolve them to `output/markdown/output/images/...`. When `--output` is absolute, the Markdown embeds absolute filesystem paths, which is not portable.
- Recommendation: always emit image links relative to the markdown file location, for example `../images/statuses/{sid}_{idx}.{ext}`.

### 2. Failed image downloads become permanently non-retryable
- Severity: medium
- Location: `export_statuses_web.py:424-457`
- Problem: `failed_images.json` is loaded into `failed_set`, and any `(sid, idx)` already in that set is skipped unconditionally on subsequent runs.
- Effect: transient network failures, rate limits, or expired cookies cannot be recovered by simply rerunning the script. Users have to manually edit or delete `failed_images.json`, which defeats the advertised resumable workflow.
- Recommendation: either retry failed items on every run, or add an explicit `--retry-failed-images` mode. At minimum, don't hard-skip historical failures forever.

### 3. Time sorting is not stable because multiple date formats are mixed
- Severity: medium
- Location: `export_statuses_web.py:281-290`, `export_statuses_web.py:529`
- Problem: `create_time` is sometimes normalized to `YYYY-MM-DD`, but the fallback path stores the visible page text directly, such as `3月19日`. Later, statuses are sorted with plain string comparison.
- Effect: output order in `my_statuses.md` and `all_statuses.md` can become incorrect when items contain mixed date formats, especially around year boundaries or when Douban omits the `title` attribute.
- Recommendation: normalize all parsed times into one comparable format before sorting. If the year is missing, infer it relative to the fetch date and store a separate sortable key.

### 4. Browser cookie extraction behavior is inconsistent with the documented workflow
- Severity: low
- Location: `douban_export.py:90-106`, `export_statuses_web.py:87-106`, `README.md`
- Problem: the main exporter only auto-reads Chrome cookies, while the web-status exporter only auto-reads Safari cookies. The README presents browser cookie extraction as a general capability and suggests a combined workflow.
- Effect: the two scripts have different platform/browser requirements, which is easy to miss. A user can successfully run one script and then fail on the other without changing anything except the entrypoint.
- Recommendation: align both scripts to the same browser detection strategy or document the difference explicitly in the usage section.

## Secondary observations
- `python3 -m py_compile douban_export.py export_statuses_web.py` succeeds.
- Running `--help` in a clean environment fails before argument parsing because `requests` is imported at module import time and there is no lockfile / requirements file in the repo. This is not a correctness bug in the exporter logic, but it does reduce first-run usability.
