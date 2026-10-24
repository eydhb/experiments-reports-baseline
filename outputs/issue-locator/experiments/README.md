# 文件级定位评测

批量评测已实现：见 [使用与复现说明](BASELINE.md)、[baseline.json](reports/baseline.json) 和
[自动生成的基线报告](reports/baseline.md)。3 个真实 Issue 的固定输出可离线重复评分。

首个真实案例已完成：[Click #3802 实验报告](real_issue_001.md)。规则模式 Top-1 未命中、
Top-3 命中，但阅读窗口偏离实际故障区域；原始输出、修复标签和完整工具记录均已保留。

先运行定位并保存原始 JSON，再用独立命令评分。评测模块不导入 Agent，
不会把修复文件名单传给模型，也不需要新增依赖。

在 `outputs/issue-locator` 中运行：

```powershell
python -m issue_locator --repo ./sample_repo --issue "登录接口返回 500" --output experiments/sample-result.json
python -m issue_locator.evaluate --result experiments/sample-result.json --case experiments/sample_case.json --output experiments/sample-evaluation.json
```

`sample_case.json` 是人工样例标签，只演示评分流程，没有真实 Issue 或修复提交，
不能作为真实 Bug 实验或模型准确率证据。也可用现有 `demo-result.json` 作为输入。

## 真实案例流程

1. 选择有明确修复提交的 Issue；记录仓库、Issue URL、完整修复 SHA 和修复前 SHA。
2. 将待分析仓库检出到修复前版本，确认工作区干净。输入仅使用修复前已有的 Issue
   描述，避免复制泄漏修复位置的后续评论；保存实际输入文本和运行模式/模型配置。
3. 用现有定位命令分析该目录并保存原始结果。保留失败输出，不事后修改排名。
4. 在独立 case JSON 中填写 `case_id`、`issue_url`、`base_commit`、`fix_commit`、
   `expected_files`。依据修复 diff 人工审查标签，通常排除只涉及测试、文档或格式的文件，
   并记录排除理由。重命名使用修复前路径；新建文件在修复前不存在，应单独说明其不可定位性。
5. 运行评分命令。工具只记录用户提供的版本/标签，不检查 Git，也不能证明运行确实使用了
   指定版本。保留源码版本证据、原始结果、case JSON 和评测 JSON。
6. 在 `real_issue_001.md` 记录上述证据、评分、函数/行范围人工核对、根因解释是否一致，
   以及失败原因。不要把文件命中当作根因确认。

## 指标定义

- 按候选输出顺序排名；同一文件的多个片段合并，保留首次出现的位置。
- Top-1 / Top-3：前 1 / 3 个唯一文件中是否命中至少一个标签文件。
- first_relevant_rank：首个命中的 1 起始排名；未命中为 null。
- reciprocal_rank：首个排名的倒数；未命中为 0。单个案例不是数据集 MRR。
- file_recall：全部候选中命中的唯一标签文件数 / 唯一标签文件总数。
- 空候选合法，计为未命中；空标签拒绝评分，避免把缺少答案算成成功。
- 路径大小写敏感，统一斜杠并去除 `./`，不按文件 basename 模糊匹配。

评测报告保存两份原始输入的 SHA-256，方便确认评分对应的确切文件；
它不验证源码证据、行号或根因正确性。输出目录需已存在，输出不能覆盖输入文件。
