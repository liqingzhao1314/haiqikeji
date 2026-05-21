# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

海启科技课程平台自动刷课 CLI 工具。Python 包结构（`haiqikeji/`），通过模拟浏览器请求与平台 API 交互，实现自动登录、获取课程、遍历章节小节、自动播放视频（心跳上报进度）。

## 开发命令

```bash
# 运行
uv run haiqikeji -n <账号> -p <密码> --skip

# 代码检查
uv run ruff check haiqikeji/ tests/

# 代码格式化
uv run ruff format haiqikeji/ tests/

# 运行测试
uv run pytest
```

## 依赖管理

使用 `uv` 管理。唯一运行时依赖：`requests>=2.33.0`。Python 3.13。

## 架构

`main.py` 是顶层命令行入口，复用 `haiqikeji.cli.main()`。`haiqikeji/` 包按职责分为以下模块：

1. **`api.py`** — API 端点 URL、请求头、Cookie 常量；每个端点一个请求函数（`login`、`get_user_info`、`get_course_list` 等）
2. **`session.py`** — `create_session()` 创建带重试策略的 `requests.Session`
3. **`progress.py`** — 终端进度条渲染（`_format_time`、`_render_progress_bar`）
4. **`utils.py`** — 工具函数：进度判断（`is_complete_progress`）、时长解析（`coerce_duration_seconds`）、断点续刷计算（`get_resume_progress_percent`）、小节进度映射（`build_node_progress_map`）、课程过滤（`course_matches`、`is_unexpired_course`）
5. **`cli.py`** — CLI 参数解析和业务逻辑（学习结果初始化/合并、进度策略分发、`auto_study_node` → `study_chapter` → `study_course`）
6. **`logging_config.py`** — 日志系统配置（`setup_logging`、`get_logger`）；控制台只显示消息正文，文件日志保留详细时间、级别、函数名和行号

## 关键数据流

`main()` 调用链：

```
main()                              # main.py
  → main()                          # cli.py
      → study_course()              # cli.py
          → get_course_chapter_tree()   # api.py — 一次调用获取章节+小节树
          → get_course_progress()       # api.py — 获取课程小节进度列表
          → build_node_progress_map()   # utils.py — 构建 {node_id: progress_data}
          → study_chapter()             # cli.py
              → _study_node_with_progress_policy()  # cli.py — 处理跳过/重刷/续刷策略
                  → auto_study_node()   # cli.py
                      → get_node_progress()          # api.py
                      → study_session_start()        # api.py
                      → study_session_heartbeat()    # api.py — 循环心跳
                      → study_session_end()          # api.py
```

## API 响应约定

所有接口返回 `{code, msg, data}` 结构。`code == 200` 表示成功。登录接口的真实响应中 `data` 直接是 JWT 字符串，`extract_token()` 只按该结构提取 token。认证通过 `authorization` 请求头传递 JWT token。

`yee_node_select` 接口返回树形结构：`data` 是章节数组，每个章节包含 `children`（小节数组）。参数为 `courseId` + `schoolId` + `studentId`，不是按章节查询。

## 代码风格

- 所有函数和常量都有中文 docstring / 注释
- 使用 `ruff` 做 lint 和格式化（配置在 `pyproject.toml` 中）
- 测试放在 `tests/` 目录下，使用 `pytest`
