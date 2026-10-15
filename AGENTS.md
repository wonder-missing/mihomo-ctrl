本工具最初为 AI Agent 而作。拿到 `mihomo-ctrl`，先跑 `--help`，输出本身就能充当一份 SKILL。

本仓库开发时若遇到 429 / 403 / 网络不可达，按下面流程切换出口，做完再复原。不要跑 `reset` 或 `tui`。

## 🛠️ 给 Agent 的用法

```bash
mihomo-ctrl --help  # 查看完整用法
mihomo-ctrl lsg  #  列出代理组及各组的选中选项
mihomo-ctrl lsg <组名>  # 查看某组下的选项及延迟
mihomo-ctrl ls  # 按延迟排序列出所有节点
mihomo-ctrl switch <组名> <节点>  # 切换节点
mihomo-ctrl unpin <组名>  # 取消 URLTest/Fallback 组的钉死
```

**建议操作流程（观察 → 调整 → 重试 → 复原）**：

1. **观察**：`mihomo-ctrl lsg` 记下入口组（常见是「默认」）现在的指向。
2. **调整**：代理结构存在分层（如「默认」→「自动选择」→ 香港节点，「默认」→「美国」→ 具体美国节点），**禁止跨层级直接指定叶子节点**。采用两步切换：
   - 若目标地区组内选项不健康，先切地区组：`mihomo-ctrl switch 美国 '<节点名>'`
   - 再将默认组切到该地区：`mihomo-ctrl switch 默认 美国`
3. **重试**：切完后重跑刚才失败的网络请求。
4. **复原**：任务完成后**必须**将代理恢复原状。例如：`mihomo-ctrl switch 默认 自动选择`。
   - **不要执行 `mihomo-ctrl reset`**。它会删掉 `cache.db`，只留给人在配置搞乱时用。
   - **不要执行 `mihomo-ctrl tui`**。那是给人用的界面。

## 📝 Git 约定

你不用主动 commit。做完后问我要不要提交即可。
需要的话直接 commit 到 `main`，不要开新分支。
commit message 用简短英文，不要写多行说明。

## 🏗️ 环境与依赖

- 项目运行时要求 Python `>=3.9`，环境和依赖一律交给 `uv`（关键配置：`pyproject.toml`）。开发目录可用 `.python-version` 固定本地解释器。
- 项目辅助脚本用 Bash（`#!/usr/bin/env bash`），直接 `./scripts/…` 执行。
  不要 `sh scripts/…`，因为 `sh` 会丢掉 shebang。
- 模拟「无 uv、有系统 Python」的安装：`./scripts/sim-install.sh`（隔离 `$HOME`，不碰本机 uv）。
  测未发布的 3.9 兼容：`./scripts/sim-install.sh --local`。回滚：`rm -rf /tmp/mihomo-ctrl-install-sim`。
  不要设置 `UV_INSTALL_DIR`，否则官方安装器不把 `uv` 放进 `~/.local/bin`。
- 要跑 Python 时用 `uv run`，不要直接 `python`，这样才能用上项目自己的版本和虚拟环境。
- 全局已经配好：`uv run` 会自动加载项目目录里的 `.env`。

## 🎯 核心开发纪律

- **本质优先**：动手前先抓住问题本身，用最简单的方式表达。如果发现更好的底层抽象，
  先用一句话跟用户说，确认后再改。
- **渐进式开发**：一次对话只解决一个具体问题。不要做预测性编程。
  可以留 `TODO`，但不要为假想需求写代码，也不要提前堆复杂抽象。
- **先逻辑后形式**：方案还没定下来时，先别写测试和使用说明。
  方案定了之后，核心路径和主要边界情况要补测试。
- **扁平化优先**：能直接写就直接写，不要过度拆模块、分层或包一层。
- **高内聚单文件**：相关逻辑尽量放一起，单文件 `150–300` 行是正常的，不要拆得太碎。
- **可审查性**：少写一层套一层的调用。读一遍就该能看懂在干什么。

## 🐍 代码规范（Modern Python Style）

- **质量检查**：改完必须过 **Ruff**、**Pyright**，以及 **3.9 / 3.14 两套 pytest**。
  - 执行 `uv run ruff check && npx pyright`，确认没有报错。
    格式问题用 `uv run ruff check --fix` 自动修。
  - **Pytest**：优先写顶层 `test_*` 函数；没有特别理由就不要包 `class TestXxx`。
    单元测试先覆盖纯逻辑、不碰 I/O 的底层模块。
    改完必须 `./scripts/run-pytest.sh`，分别在 Python 3.9 和 3.14 上跑 pytest。
    只跑 `uv run pytest` 不够——那只会打中 `.venv` 里的 3.14。
    `run-pytest.sh` 用 `--isolated`，不会改开发用的 `.venv`。
    不要直接 `uv run --python 3.9 pytest`，那会拆掉 3.14 环境。
  - Ruff 规则组：`E` `F` `I` `N` `W` `UP`，已开启 `preview = true`。
    行宽 ≤ 88；import 按 标准库 / 第三方 / 本地 三组排列，组间空行，每组内按字母序。
  - 连续两层函数调用时，括号跟在同一行打开，避免参数再缩进一层：
    ```python
    # ✅
    result = outer(
        inner(
            arg1,
            arg2,
        )
    )

    # ❌
    result = outer(inner(arg1, arg2))
    ```
- **类型安全**：类型标注用现代写法。
  - **`hasattr` 之后改用 `getattr`**：即便 `hasattr(obj, "x")` 为 True，pyright 也不会收窄类型。
- **技术栈偏好**：
  - 路径用 `pathlib`，字符串用 `f-string`，数据结构用 `dataclasses`。
  - **运行时不引入第三方库**。HTTP 用标准库 `urllib`，配置读环境变量。
    不要为了包一层再引入 httpx / pydantic。
- **命名要准**：
  - 变量、类、模块名要能看出边界。先求准，再求短，别把所属类型再重复写一遍。
  - **属性名不要重复类型/类名**：写 `provider.id`，不要写 `provider.provider_id`。
  - 库模块的私有成员加 `_` 前缀；入口模块（`__main__.py`）没人 import，不必乱加。
  - 故意不用的返回值用 `_name` 接住。
  - 作用域不长就不要缩写：`subparsers` 比 `sub` 好读。

- **注释**：只给真正需要注意的地方写。不要把函数名翻译成中文再当 docstring。
  注释里不要夹重构思路、推导过程或修改痕迹。

- **异常与日志**：
  - 对外失败用自定义异常；内部工具函数可以直接抛 `ValueError` 这类内置异常。
  - 用标准库 `logging`，模块里写 `logger = logging.getLogger(__name__)`。
  - 外部调用和异常分支要记日志，方便排查。
