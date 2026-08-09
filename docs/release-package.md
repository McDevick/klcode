# KL Code Release 包内容清单

> 状态：草案（2026-08-09，基础发布资产已补齐）
> 目标：明确正式发布时需要构建、检查和附带哪些文件，避免把用户数据/密钥/本地环境打进发布包。

## 1. 版本约定

server 包与 CLI 包必须使用同一个版本号：

- `server/pyproject.toml` 的 `[project].version`
- CLI 构建时由 `cli/scripts/sync-server-version.mjs` 生成 `cli/src/server-version.ts`
- 发布 tag 建议使用：`v<version>`
- 发布前必须通过：

```bash
cd cli
npm run check:server-version
```

## 2. 必须包含的发布产物

### 2.1 Server 包

| 产物 | 文件 | 说明 |
|---|---|---|
| Wheel | `server/dist/kl_server-<version>-py3-none-any.whl` | 用户可直接 `pip install` |
| Source dist | `server/dist/kl_server-<version>.tar.gz` | 源码安装/审计使用 |
| Python 版本要求 | `>=3.11` | 写在 `server/pyproject.toml` |
| 运行依赖 | fastapi/uvicorn/websockets/pydantic/aiosqlite/keyring/cryptography/httpx/jsonschema/openai/mcp/PyYAML | 由 pyproject 声明，不在包内嵌依赖 |

构建命令：

```bash
python -m build server
```

### 2.2 CLI 包

| 产物 | 文件 | 说明 |
|---|---|---|
| npm tarball | `cli/kl-code-cli-<version>.tgz` | 通过 `npm pack` 生成 |
| 入口 | `cli/dist/main.js` | 已 esbuild 打包，包内 `bin.kl` 指向它 |
| Node 版本要求 | `>=22` | 写在 `cli/package.json` |
| 运行时依赖 | ink/commander/react/marked 等 | 由 npm dependencies 声明，不手动打包 |

`kl` 命令注册说明：

- `npm install -g @kl-code/cli` 会注册 `kl`。
- `npm link` 也会注册，但只适合开发环境。
- `npx @kl-code/cli` 不会注册全局 `kl`。
- PyPI 的 `kl-server` 只注册服务端命令 `kl-server`。
- 如果 `kl` 找不到，检查 npm 全局 bin 是否在 PATH：
  ```bash
  npm config get prefix
  npm bin -g
  ```
- Windows 常见目录：`%APPDATA%\npm`
- Linux/macOS 常见目录：`~/.npm-global/bin`、`/usr/local/bin`

构建/检查命令：

```bash
cd cli
npm run build
npm run check:server-version
npm pack --dry-run
```

### 2.3 文档与配置模板

当前仓库已提供以下发布文档与资产：

- `README.md`
- `docs/check.md`
- `docs/release-test.md`：发布前测试与检查清单
- `docs/server-redesign.md`
- `docs/context-redesign.md`
- `LICENSE`（MIT）
- `RELEASE_NOTES.md`：本次版本变更、已知问题、升级注意事项
- `examples/config.example.yaml`

示例配置内容覆盖：

- `default_provider` / `default_model`
- provider 的 `base_url` / `default_model` / `credential_ref`
- `mcp` server 示例
- `sandbox`
- `guardrail.approval_timeout_seconds`

用户首次运行后应手动复制为：

```text
~/.kl/config.yaml
```

## 3. 可选发布资产

| 资产 | 用途 | 建议 |
|---|---|---|
| `release/checksums.sha256` | 校验下载完整性 | 推荐 |
| `release/SBOM` | 依赖/许可审计 | 正式发布建议 |
| 单文件二进制/installer | 后续“免 Python/Node”体验 | 当前未实现，不要假装包含 |
| 项目源码 zip/tar.gz | GitHub Release 源码附件 | 可选 |

## 4. 明确不要打包的内容

以下内容属于用户本地状态或构建中间产物，严禁进入发布包：

```text
.kl/
  config.yaml
  kl.db
  memory.db
  audit.jsonl
  daemon.token
  daemon.pid
  daemon.log
  credentials.master
  venv/

cli/node_modules/
cli/dist/            # 只通过 npm tarball 发布，不单独附在源码包
server/build/
server/egg-info/
server/__pycache__/
```

特别提醒：

- 不要把 `~/.kl/` 或项目 `.kl/` 里的真实配置/数据库/日志打进包。
- 不要把任何 `api_key`、`credential_ref`、密钥文件打进包。
- `cli/dist/main.js` 是 CLI 发布产物，但应由 `npm pack` 统一打包，而不是手工复制。

## 5. 用户首次运行时会自动生成什么

发布包本身不携带用户数据。用户第一次运行时：

- 自动创建 `~/.kl/`
- 自动创建/自举 `~/.kl/venv`
- 自动生成 `~/.kl/daemon.token`
- 如果用户没有配置 `~/.kl/config.yaml`，加载器会自动合并 DeepSeek 预设并把默认 provider 设为 `deepseek`；需要 mock 冷启动请使用 `/model` 切换，或在配置中显式设置 `default_provider: mock`
- 如果用户没有 `~/.kl/user-rules.md`、`~/.kl/skills/`、`~/.kl/tools/`，不报错

项目目录不再作为配置/数据库根目录；项目级规则只读取：

```text
<项目>/.kl/rules.md
<项目>/AGENTS.md
```

大输出统一落盘到全局目录：

```text
~/.kl/tool_outputs/
```

可通过 `storage.tool_outputs_dir` 覆盖，不再在项目工作区创建 `.kl/tool_outputs`。

## 6. 发布前检查清单

- [ ] `server/pyproject.toml` 与 `cli/src/server-version.ts` 版本一致
- [ ] `python -m build server` 成功
- [ ] `cd cli && npm run build && npm run check:server-version` 成功
- [ ] `npm pack --dry-run` 只包含 `dist` 和 package metadata
- [ ] 测试全量通过：`server` 与 `cli`
- [ ] 按 `docs/release-test.md` 完成发布前预发布检查
- [x] 示例配置 `examples/config.example.yaml` 已包含
- [ ] 发布包内没有 `.kl`、密钥、数据库、日志、venv、node_modules
- [x] `LICENSE` 与 `RELEASE_NOTES.md` 已包含
- [x] release notes 已写清升级迁移说明
