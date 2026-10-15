# 自动同步上游

本 fork 通过 `Sync upstream` GitHub Actions 工作流同步
`szkane/ClashRuleSet` 的 `main` 分支。

- 每天北京时间 **06:17** 检查更新，也可以在 Actions 页面手动运行。
- 修改同步工作流或脚本并推送到 `main` 时，会自动运行一次。
- 始终保留本 fork 的 `Clash/kclash.ini`，包括分组、emoji 和规则引用。
- 始终保留 `.github/workflows/` 和 `.github/scripts/`，包括阻止引入上游新增的工作流。
- 其余文件正常合并上游；没有冲突的本地修改也会保留。
- 其他文件发生冲突时中止合并，不提交、不推送；在 Actions 日志中列出冲突文件。
- 正常完成后自动创建合并提交并推送到 `main`，不使用强制推送。
- 上游没有新提交时不创建提交。

保护整个 `kclash.ini` 意味着上游在此文件内新增的规则引用、分组或修复
需要手动挑选。现有 `ruleset` URL 仍引用上游的规则列表，可以独立跟随其内容更新。

## 首次启用与手动运行

打开 <https://github.com/Hitooooo/ClashRuleSet/actions>。如果 fork 的 Actions
尚未启用，先点击启用工作流，然后选择 **Sync upstream → Run workflow → main**。
工作流使用 GitHub 自动提供的 `GITHUB_TOKEN` 和 `contents: write` 权限，无需配置个人令牌。
如果以后启用了禁止直接推送到 `main` 的分支规则，需要相应调整同步流程。

GitHub 对公开仓库的定时工作流有两个限制：运行时间可能延迟；连续 60 天
没有仓库活动时，定时工作流会自动停用，届时需要在 Actions 页面重新启用。

## 配置入口

订阅转换时，`config=` 应使用本 fork 的配置：

<https://raw.githubusercontent.com/Hitooooo/ClashRuleSet/main/Clash/kclash.ini>

## 本地验证

```sh
bash -n .github/scripts/sync-upstream.sh
python3 .github/scripts/test_sync_upstream.py
```

测试在临时 Git 仓库中运行，不联网，也不会修改当前仓库的提交或分支。
