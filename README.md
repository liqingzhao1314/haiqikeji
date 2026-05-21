# 海启科技课程平台自动刷课 CLI 工具

本程序通过模拟浏览器请求与海启科技课程平台 API 交互，实现自动登录、获取课程列表、遍历章节小节、以及自动播放视频（通过心跳上报进度）等功能。可通过命令行参数灵活控制刷课行为。

> **免责声明：** 本工具仅供学习和研究使用，请勿用于任何非法用途。使用前请确保已获得相关课程的合法访问权限。

## 环境要求

- Python 3.13+
- pip
- 可选：[uv](https://docs.astral.sh/uv/) 包管理器

## 安装

### 不使用 uv

```bash
# 克隆项目
git clone <repo-url>
cd haiqikeji_v2

# 创建虚拟环境
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate

# 升级 pip
python -m pip install --upgrade pip

# 安装工具
python -m pip install .
```

安装完成后即可直接使用 `haiqikeji` 命令。

如果不想安装命令行入口，也可以在项目根目录安装依赖后直接运行：

```bash
python -m pip install requests
python main.py -n <账号> -p <密码> --skip
```

### 使用 uv

```bash
uv sync
```

## 使用方法

```bash
# 一键刷课
haiqikeji -n <账号> -p <密码> --skip

# 打印未观看的课程/章节/小节信息（不刷课）
# 先打印出详细的课程信息，再根据课程 ID、章节 ID、小节 ID 选择性刷课
haiqikeji -n <账号> -p <密码> --list

# 仅刷指定课程（按课程名称关键词）
haiqikeji -n <账号> -p <密码> --cn <课程关键词> --skip

# 指定课程 ID 刷课
haiqikeji -n <账号> -p <密码> --cid <课程ID>

# 仅刷指定章节
haiqikeji -n <账号> -p <密码> --cid <课程ID> --chid <章节ID>

# 仅刷指定小节
haiqikeji -n <账号> -p <密码> --cid <课程ID> --chid <章节ID> --nid <小节ID>
```

## 输出格式

控制台默认只显示消息正文，输出格式示例如下：

```text
自动刷课工具 | 用户: <账号>
正在登录...
正在验证用户信息...
正在获取课程列表...
匹配课程: 1 个

开始自动刷课

课程 [课程ID] 课程名称
  [章节ID] 导论 课程简介
    - [跳过] 导论 课程简介
  [章节ID] 项目一 项目介绍
    - [跳过] 任务一 项目介绍

刷课完成
成功 7891 | 失败 2778 | 跳过 103845 | 总计 114514
```

如需保留详细时间戳、级别、函数名和行号，可使用 `--log-file <日志文件>` 输出文件日志。

## 命令行参数

| 参数 | 缩写 | 说明 | 默认值 |
|------|------|------|--------|
| `--number` | `-n` | 登录账号/学号 | - |
| `--password` | `-p` | 登录密码 | - |
| `--school-id` | `--sid` | 学校 ID | 10 |
| `--course-id` | `--cid` | 仅刷指定课程 ID | - |
| `--course-name` | `--cn` | 仅刷课程名包含指定文本的课程 | - |
| `--chapter-id` | `--chid` | 仅刷指定章节 ID（需配合 `--cid`） | - |
| `--node-id` | `--nid` | 仅刷指定小节 ID（需配合 `--cid` 和 `--chid`） | - |
| `--progress-step` | `--step` | 每次心跳之间的间隔秒数 | 25 |
| `--skip-complete` | `--skip` | 跳过已完成的小节 | False |
| `--list-incomplete` | `--list` | 仅打印未观看的课程/章节/小节，不执行刷课 | False |
| `--verbose` | `-v` | 启用 DEBUG 级别日志输出 | False |
| `--log-file` | - | 指定日志文件路径 | - |

## 开发

### 不使用 uv

```bash
python -m pip install -e .
python -m pip install pytest ruff

# 代码检查
ruff check haiqikeji/ tests/

# 代码格式化
ruff format haiqikeji/ tests/

# 运行测试
pytest
```

### 使用 uv

```bash
# 安装开发依赖
uv sync --dev

# 代码检查
uv run ruff check haiqikeji/ tests/

# 代码格式化
uv run ruff format haiqikeji/ tests/

# 运行测试
uv run pytest
```

## 工作原理

1. 登录并从真实响应结构中提取 token：`data` 必须是 JWT 字符串。
2. 校验 token 并获取 `student_id`。
3. 获取课程列表（自动过滤已过期课程）。
4. 每门课程只调用一次章节树接口，获取章节和小节结构。
5. 使用课程进度接口和 `build_node_progress_map()` 构建小节进度映射。
6. 按跳过/重刷策略处理每个小节：
   - 已完成且指定 `--skip`：跳过。
   - 已完成但未指定 `--skip`：从 0 开始重刷。
   - 未完成：支持断点续刷。
7. 对需要学习的小节执行自动学习生命周期：
   - `study_session_start` - 开始学习会话
   - `study_session_heartbeat` - 循环心跳上报进度
   - `study_session_end` - 结束学习会话
8. 合并每门课程的成功、失败、跳过统计并输出汇总。

## 项目结构

```
main.py                  # 顶层命令行入口
haiqikeji/
├── __init__.py          # 包版本
├── api.py               # API 请求函数和常量
├── session.py           # HTTP 会话配置
├── progress.py          # 终端进度条渲染
├── utils.py             # 工具函数
├── cli.py               # CLI 参数解析和业务逻辑
└── logging_config.py    # 日志配置
```

## 作者

- **momo** - [小红书](https://xhslink.com/m/A7dz60XUVy8)
