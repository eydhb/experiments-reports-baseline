# 本次实际运行结果

输入：**登录接口返回 500**

数据源：内置人工 Java 登录样例（10 个可检索文件）。

运行模式：LangGraph 编排的规则检索演示，未调用大模型。

执行过程：导入样例 → 搜索登录入口 → 读取源码 → 根据符号继续搜索和读取 → 校验引用 → 输出报告。本次共执行 **20 次工具调用**，完整记录见 `demo-result.json`。

主要候选位置：

| 文件 | 实际引用行号 | 源码提供的依据 |
|---|---|---|
| `src/main/java/demo/auth/controller/UserController.java` | 11–23 | `/api/login` 入口调用 `userService.authenticate(request)` |
| `src/main/java/demo/auth/service/UserService.java` | 15–21 | 认证方法调用 `tokenService.validateRefreshToken(...)` |
| `src/main/java/demo/auth/service/TokenService.java` | 8–12 | 过期条件满足时抛出 `TokenExpiredException` |
| `src/main/java/demo/auth/exception/GlobalExceptionHandler.java` | 10–21 | 存在特定异常处理和通用异常转 500 的映射 |

报告还列出两个关联异常定义，供继续阅读。

**待验证假设**：当前失败是否由过期令牌触发，并进入了通用异常处理分支。代码证据可以指导排查，但样例没有真实请求或运行日志，不能据此声称已复现和确认生产故障。

需要补充的验证材料：

1. 本次失败请求的异常类型与堆栈。
2. 接口路径、请求参数、令牌过期时间和复现步骤。
3. 实际全局异常处理注册情况及运行配置。

在工作台打开结果中的「读取上下文」可再次读取真实文件；「导出 JSON」可保存当前报告。
