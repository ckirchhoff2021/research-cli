# GitHub 开源生态盘点配方（2026-08-21 实测）

盘点某主题的开源实现时的已验证命令集。

## 1. Search API 找项目

```bash
curl -s "https://api.github.com/search/repositories?q=<keyword>&per_page=15&sort=stars" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('total:', d.get('total_count'))
for r in d.get('items',[]):
    print(f\"{r['full_name']:50s} stars={r['stargazers_count']:6d} pushed={r['pushed_at'][:10]}  {(r['description'] or '')[:90]}\")
"
```

多组关键词（精确名 + 通用短语 `q=%22claude+tag%22` + `in:name`）交叉覆盖。
同法遍历组织仓库：`/orgs/<org>/repos?per_page=100&sort=pushed` 后本地过滤。

## 2. 存活检查（"被移除"结论的依据）

```bash
curl -s -o /dev/null -w "%{http_code}\n" "https://github.com/<owner>/<repo>"
# 200=存活 404=不存在/已删
```

多个候选名一起测（原名、连字符变体、缩写）。注意区分：
- **确认删除**：所有 URL 变体 404 + 组织仓库列表无此名
- **推断收编**：上述基础上，组织内出现"底层引擎"类后继项目（如 Zilliz
  Open Tag 404 → 只剩 zilliztech/mfs）。推断必须在报告中显式标注"推断，无官方公告佐证"。

## 3. 限流与回退（关键坑）

未认证 API：**60 次/h/IP**。盘点 10+ 仓库时，搜索+存活检查+逐个 readme
会迅速 403 `rate limit exceeded`。应对：
- API 预算只留给搜索和存活检查
- README 走 raw（不限流）：

```bash
for br in main master; do
  code=$(curl -sL -o /tmp/rm -w "%{http_code}" \
    "https://raw.githubusercontent.com/<owner>/<repo>/$br/README.md")
  [ "$code" = "200" ] && break
done
head -c 1500 /tmp/rm
```

## 4. 报告要点

- 开头写快照日期（数据 YYYY-MM-DD 实测），GitHub 生态变动快
- 总览表列：stars / 许可证 / 定位 / 通道（Slack/Teams/飞书）/ 支持模型
- 低星项目（<100★）标注"个人项目，生产前审代码"，重点提凭据处理风险
