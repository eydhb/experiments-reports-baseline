# CodeLens · Issue → 文件定位

一个可以在本机运行的毕业设计原型：导入代码仓库，输入问题，沿搜索与读取工具收集证据，输出候选文件、真实行号、判断依据和待验证项。

## 立即使用

当前工作台地址：**http://127.0.0.1:8766**

1. 双击 `start.bat`（当前服务已启动时可直接打开上面的地址）。
2. 页面自动导入内置登录示例仓库。
3. 保留问题「登录接口返回 500」，点击「开始定位」。
4. 查看候选文件、展开代码上下文、检查工具调用记录，可导出 JSON。

首次在其他电脑启动需要 Python 3.11+ 和网络；GitHub 导入另外需要 Git。本次环境已经安装依赖。启动脚本优先使用当前工作区的独立环境，复制到其他目录时会创建 `.venv`。

也可以使用 PowerShell：

```powershell
.\start.ps1
# 指定另一个端口：
.\start.ps1 -Port 8770
```

## 两种运行模式

| 模式 | 当前状态 | 能力 |
|---|---|---|
| 规则检索演示 | 已端到端运行验证，无需 API 密钥 | 根据问题关键词选择搜索，读取代码后提取 Service、Exception 等符号继续检索；通过 LangGraph 循环调度 |
| 模型 Agent | 已实现，已用模拟服务响应测试；尚未连接真实模型 | 模型自主调用三个工具，沿代码进行搜索、阅读和解释 |

**规则模式不是大模型语义推理，也不是 AST 调用图分析。** 两种模式都只输出待验证的候选位置，不将关键词命中视为确定根因；没有准确率或“60%”效果承诺。

模型模式需要兼容 Chat Completions 且支持工具调用的服务。在启动服务前，在同一个 PowerShell 窗口配置：

```powershell
$env:LOCATOR_BASE_URL = 'https://你的模型服务地址/v1'
$env:LOCATOR_MODEL = '你的模型名称'
$env:LOCATOR_API_KEY = '你的密钥'
.\start.ps1 -Port 8770
```

环境变量必须由新启动的服务进程读取。已运行的服务不会自动取得另一个窗口设置的变量；选择新端口启动后访问该端口。`BASE_URL` 应是 API 基础地址，不包含 `/chat/completions`。本机模型服务允许 `http://127.0.0.1:端口/v1`，其他地址要求 HTTPS。

密钥只从服务进程环境读取，不发送到网页、不写入报告。模型模式会将问题、文件列表和必要源码片段发送到所配置的服务。规则模式无需调用模型服务。

## 示例结果与边界

内置的 `sample_repo/` 是明确标记的人工 Java/Spring 风格静态分析样例，不是实际 GitHub 项目，也不是可启动的登录后端。

「登录接口返回 500」会发现：

- `UserController.java`：`/api/login` 入口调用认证服务。
- `UserService.java`：认证方法调用令牌检查。
- `TokenService.java`：过期时显式抛出 `TokenExpiredException`。
- `GlobalExceptionHandler.java`：包含通用异常转 HTTP 500 的映射。

完整输出保存在 `demo-result.json`。输出行号来自文件读取，不是预设答案。阅读窗口内的代码会附带 SHA-256，在报告生成前检查内容是否发生变化；模型引用的未读文件、未读区间和无效行号会被丢弃。

源码可以支持“过期异常可能进入通用 500 处理”的假设，确认真实故障仍需请求、日志、异常堆栈和运行配置。报告中的候选排序分值仅用于内部启发式排序，不是概率。

## 导入自己的项目

- **本地目录**：填写绝对路径，只读访问，源码不会被修改或执行。目录不强制包含 `.git`。
- **GitHub**：填写公开仓库根地址，例如 `https://github.com/owner/repo`；浅克隆到项目下的 `data/`。当前不支持私有仓库、分支页面、子目录 URL 和子模块。
- 文件列表是本次导入的快照；新增文件后请重新导入。单文件最多 1 MiB，最多枚举 20,000 个文件和 100,000 个目录条目；命中上限会提示结果不完整。
- 跳过依赖、构建产物、版本控制目录、常见密钥文件、`.env`、二进制内容和符号链接/目录联接。源码或普通配置中的硬编码秘密无法保证识别，模型模式使用前请自行检查。
- 原型适合小型源码仓库。大仓库、跨语言间接调用、动态路由和复杂框架注入可能定位不全；没有 AST、Embedding 或向量索引。

## 结构和工具

```text
issue_locator/
  repository.py  # list_files / search_code / read_file
  agent.py       # LangGraph: decide → tools → decide → report
  model.py       # 可配置的工具调用模型客户端
  server.py      # 本地 HTTP 接口
web/             # 中文操作界面，无前端依赖
sample_repo/     # 含预设问题的静态登录代码样例
tests/           # 工具、Agent、HTTP 行为测试
demo-result.json # 实际示例定位结果
```

工具示例：

```python
from issue_locator.repository import Repository
from issue_locator.agent import analyze

repo = Repository("./sample_repo")
repo.list_files()
repo.search_code("login")
repo.read_file("src/main/java/demo/auth/controller/UserController.java", 12, 24)
result = analyze(repo, "登录接口返回 500", mode="offline")
```

命令行（在已安装依赖的 Python 环境中）：

```powershell
python -m issue_locator --repo .\sample_repo --issue "登录接口返回 500" --output result.json
python -m issue_locator.server --port 8766
python -m unittest discover -s tests -v
```

已导出的 JSON 可独立评测 Top-1、Top-3、首个命中排名和文件召回率：

```powershell
python -m issue_locator.evaluate --result demo-result.json --case experiments/sample_case.json --output experiments/sample-evaluation.json
```

该命令不调用模型。内置标签仅用于人工样例演示；真实案例的版本固定、标签选择和指标定义见
[评测说明](experiments/README.md)。

主要接口：

```text
GET  /api/status
POST /api/import   {"source":"sample"}
POST /api/import   {"source":"local","path":"D:\\projects\\my-repo"}
POST /api/import   {"source":"github","url":"https://github.com/owner/repo"}
POST /api/analyze  {"repository_id":"导入结果中的 id","issue":"登录接口返回 500","mode":"offline"}
GET  /api/file?repository_id=...&path=...&start_line=1&end_line=80
```

服务只监听 `127.0.0.1`，检查 Host/Origin，并限制请求体、工具步数和并发。它不是可直接部署到公网的多用户服务。

## 验证

本次环境使用 Python 3.11.4、LangGraph 1.2.16。`requirements-lock.txt` 记录实际安装版本，便于在兼容环境复现。

自动测试覆盖：文件越界与排除规则、真实行号、示例调用链定位、无关问题不编造候选、模型引用校验、文件变化、完整 HTTP 流程、跨站请求拒绝和密钥不泄漏。详见 `VALIDATION.md`。

LangGraph 接入方式参考官方 [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api) 与 [条件路由 API](https://reference.langchain.com/python/langgraph/graph/state/StateGraph/add_conditional_edges)。
