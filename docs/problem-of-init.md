# Problem：`kl init` 首次自动安装 server 卡住

> 状态：代码已修复，待发布后验证
> 日期：2026-08-10
> 范围：`cli/src/commands/server.ts` 的 `bootstrapGlobalVenv`
> 关联：docs/server-redesign.md（自动拉起）、docs/release-test.md（发布后测试）

## 1. 现象

在全新机器上只安装 CLI：

```powershell
npm install -g kl-code-cli
kl init
```

`kl init` 会提示：

```text
首次运行将创建全局环境 ~/.kl/venv 并安装 kl-server（版本 0.1.0），是否继续？[Y/n]
```

输入 `Y` 后：

- 长时间没有输出；
- 看起来像卡住；
- 下一行仍能输入字符，但程序没有反应。

手动安装 server 后：

```powershell
python -m pip install kl-server
```

`kl init` 和 `kl tui` 都能正常自动拉起服务端。

## 2. 当前流程

```text
kl init
  -> 探测 http://127.0.0.1:8700
  -> 连接失败
  -> kl server start
  -> 查找可用 Python
  -> 找不到可用 kl_server 环境
  -> 询问是否创建 ~/.kl/venv
  -> 输入 Y
  -> execFileSync("python -m venv ...")
  -> execFileSync("pip install kl-server==<version> ...")
  -> 启动 uvicorn
  -> 轮询 /health
```

## 3. 根因

### 3.1 安装过程不可见、无超时

`bootstrapGlobalVenv` 使用：

```ts
execFileSync(python, ['-m', 'venv', venv], { stdio: 'pipe' });
execFileSync(venvPython, ['-m', 'pip', 'install', `kl-server==${version}`], {
  stdio: 'pipe',
});
```

问题：

- `stdio: 'pipe'` 导致安装输出不会显示；
- 没有超时；
- 如果 venv 创建或 pip 安装较慢，终端表现为完全无反应；
- 输入 Y 后 readline 已关闭，但 stdin 未被禁用，所以后续输入仍会回显，只是不会被处理。

### 3.2 Python 版本选择不可控

Windows 候选顺序为：

```text
py
python
python3
```

`py` 未指定版本时可能选择系统最新 Python。已观察到新机器默认为 Python 3.14。

当前 `server/pyproject.toml` 仅声明：

```text
requires-python = ">=3.11"
```

当前策略应为“Python >=3.11 均可使用”，但自动加载前没有显式检测版本是否满足 >=3.11。3.14 缺少发布前验证，若依赖在 3.14 下缺少 wheel 或需要现场编译，pip 会长时间无输出，表现为卡住。

### 3.3 安装失败被静默吞掉

`bootstrapGlobalVenv` 的异常处理：

```ts
try {
  ...
} catch {
  return null;
}
```

失败后：

- 没有错误详情；
- 没有清理损坏的 `~/.kl/venv`；
- 没有提示手动安装命令；
- 下次运行可能继续复用坏环境。

### 3.4 TUI 先渲染再安装

`kl tui` 当前流程：

```text
kl tui
  -> 立即渲染 TUI
  -> 创建会话失败
  -> 才调用 autoStartDaemon
  -> autoStartDaemon 内部才安装 server
```

没有做到“先完成 server 下载/安装，再打开并渲染 TUI”。

## 4. 复现

新机器或隔离 HOME 中执行：

```powershell
npm install -g kl-code-cli
kl init
```

输入 `Y` 后等待。

手动验证 Python 与安装：

```powershell
py --version
python --version
```

```powershell
python -m venv $env:USERPROFILE\.kl\venv-test
$env:USERPROFILE\.kl\venv-test\Scripts\python -m pip install kl-server==0.1.0
```

如果手动安装正常，说明问题集中在 CLI 的自动 bootstrap 路径。

## 5. 影响

- 全新机器首次使用体验不可用；
- 用户无法判断是在下载、编译还是卡死；
- 失败后没有明确原因；
- 可能留下损坏的 `~/.kl/venv`；
- `kl tui` 会在服务端未就绪时提前渲染，进一步放大问题。

## 6. 修复方向

### 6.1 Python 探测

- 自动加载前先检测 Python 版本，必须满足 `>=3.11`；
- 不限制具体后续版本，3.12 / 3.13 / 3.14 等更高版本均可接受；
- 校验 `sys.version_info` 与依赖导入能力；
- 如果 Python 版本低于 3.11，给出明确提示并停止自动安装。

### 6.2 安装过程可观测

- 将 `execFileSync` 改为异步 `spawn`；
- 实时输出 venv 与 pip 日志；
- 设置超时；
- 超时或失败后清理损坏的 `~/.kl/venv`。

### 6.3 失败提示

失败时输出：

```text
自动创建 ~/.kl/venv 并安装 kl-server 失败。
请手动执行：
python -m venv $env:USERPROFILE\.kl\venv
$env:USERPROFILE\.kl\venv\Scripts\python -m pip install kl-server==0.1.0
```

### 6.4 TUI 进入前 preflight（已确认方向）

`kl tui` 应在进入 TUI 之前先检查 server，而不是先渲染再后台拉起：

```text
kl tui
  -> 检查 http://127.0.0.1:8700/health
  -> 已运行：直接进入 TUI
  -> 未运行：显示“正在检查/安装服务端”
     -> 自动创建 venv（如有必要）
     -> 下载并安装 kl-server
     -> 启动 daemon
     -> 等待 /health 就绪
  -> 成功：进入 TUI
  -> 失败：打印明确错误并退出，不进入 TUI
```

实施顺序：

1. 先修复 `bootstrapGlobalVenv` 的安装可观测性与超时；
2. 再做 TUI preflight，避免“显示正在安装但依然无反应”。

不建议直接用 TUI 内部 loading 界面替代，因为那只是改变卡住的位置，没有解决自动安装流程本身的问题。

### 6.5 Python 版本约束

- 版本约束保持 `>=3.11`，不设置上限；
- 3.12 / 3.13 / 3.14 等后续版本均应纳入发布前测试；
- 如果某个新 Python 版本的依赖安装失败，应修复依赖或给出明确错误，而不是偷偷限制版本。

## 7. 验收标准

- 全新机器只安装 `kl-code-cli`，`kl init` 能看到安装进度，最终成功拉起 server。
- `kl tui` 在 server 未就绪时不会直接进入完整界面，或会先显示等待/安装状态。
- 自动安装失败时清理坏 venv，并提示手动安装命令。
- 手动安装 server 后，`kl init` / `kl tui` 仍可正常自动拉起。
## 8. 修复记录

已实现：

- `cli/src/commands/server.ts`
  - 新增 `runProcess()`，venv 创建与 pip 安装改为异步 `spawn`，实时输出日志，并设置超时；
  - Python 探测增加 `>=3.11` 版本校验，不限制具体后续版本；
  - `bootstrapGlobalVenv` 安装失败或超时后清理损坏的 `~/.kl/venv`；
- `cli/src/main.ts`
  - `kl tui` 进入 TUI 前先执行 `ensureServerReady()`；
  - server 未运行时先自动拉起/安装，就绪后再进入 TUI；
  - 启动失败时打印错误并退出，不进入 TUI。

验证：

- CLI 测试：`129 passed`
- TypeScript：通过

仍需发布后验证：

- 全新机器只安装 CLI 时，`kl init` / `kl tui` 能显示安装进度并完成 server 自举。