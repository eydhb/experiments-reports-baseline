# CodeLens 第二份自动化评测基线

2026-10-25 15:50（Asia/Shanghai）实际重新运行 3 次 offline 规则模式 Agent，随后自动评分并验证。没有调用真实模型，没有修改定位策略。第一份结果保留。

## 结果

| 案例 | Issue | 标签文件 | 首次命中排名 | Top-1 | Top-3 |
| --- | --- | --- | --- | --- | --- |
| real_issue_001 | Click #3802 | src/click/core.py | 2 | false | true |
| real_issue_002 | Click #936 | click/core.py | 6 | false | false |
| real_issue_003 | Click #1905 | src/click/_termui_impl.py | 未命中 | false | false |

Top-1 = 0/3（0%）；Top-3 = 1/3（33.33%）。相比第一份，两项命中率变化均为 0 个百分点。三个完整候选列表与第一份一致；原始 result.json 的唯一字段差异为 elapsed_ms，因此原始结果文件的哈希不同。

这次验证了重新运行 Agent 后的结果一致性，没有证明定位能力提升。文件命中不能证明代码区域或根因正确，三个同项目案例不能代表跨项目准确率。标签沿用第一份经审查的标签；本次未重新标注。第二轮报告中的人工失败分析保留 pending，未把旧分析伪装为新分析。

## 验证与证据

- [第二份基线 JSON](reports/baseline-02.json) / [自动评分报告](reports/baseline-02.md)
- [验证及前后对比](reports/verification.json)
- [第一份基线快照](baseline-01.json)
- [批量评测测试：6/6 通过](logs/benchmark-tests.txt)
- [Agent 测试：8/8 通过](logs/agent-tests.txt)
- 每个 real_issue_00N 目录保存本次 result.json、tool-results.json、run.json，以及沿用的 issue、修复证据和源码清单。
- 源码文件数量分别为 166、120、136；运行前后逐文件 SHA-256 及完整文件集合校验通过，全部候选证据与源码逐行一致。
- 运行时未向 Agent 提供修复标签。修复信息只在后续独立评分阶段读取。
- 对新输出连续评分两次，JSON 和 Markdown 分别逐字节一致；独立核算三个案例的 Top-1、Top-3 和首次命中排名通过。
- Python 3.11.4，LangGraph 1.2.16，安装原仓库锁定依赖；实际依赖见 environment-freeze.txt。
- 实际运行使用仓库提交 `557d83e6be8dccc994cd7fe4f29b5671f4187d28` 的代码，代码位于 ../issue-locator/。
- 基线 SHA-256：`8a582abecb10ca0c612370c3c4289864df312e04b176323e4c22969df62d0b49`。

自动评分报告中“只评分已保存输出”描述的是评分器阶段；本交付包的三个输入均来自本轮实际 Agent 运行。

## 复现评分（无需第三方依赖）

从仓库根目录执行：

```powershell
cd outputs/issue-locator
python -S -m issue_locator.benchmark --manifest ../baseline-02/baseline_cases.json --output data/baseline-02-repeat.json
```

JSON 和 Markdown 应分别与本目录 reports 中对应文件逐字节一致。

## 再次运行 Agent

沿用 ../issue-locator/experiments/BASELINE.md 中的固定源码下载流程，使用每例 source-manifest.json 的 base_commit 检出修复前版本，禁止换行转换。源码、虚拟环境和重复代码不纳入本次提交。

在 outputs/issue-locator 中安装 requirements-lock.txt 的依赖后执行（以第一例为例，源码目录需自行准备）：

```powershell
python experiments/run_real_issue_001.py --repo data/real_issue_001/source --case-dir ../baseline-02/real_issue_001 --output-dir data/baseline-02-replay/real_issue_001
```

其他两例同理。始终使用新输出目录；重新评分需创建新案例清单并更新结果路径和 SHA-256。

## 下一步

优先修改源码阅读窗口选择，再在同一固定案例集上运行新策略。分别核对文件排名、故障代码区域覆盖情况和根因解释。本轮未修改策略，也未进行真实模型评测。
