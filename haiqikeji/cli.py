"""CLI 入口和业务逻辑。

包含命令行参数解析、自动刷课核心逻辑（心跳循环、章节遍历、课程处理）。
"""

from __future__ import annotations

import argparse
import logging
import math
import time
from datetime import date
from typing import Any

import requests

from haiqikeji import __version__
from haiqikeji.api import (
    extract_token,
    get_course_chapter_tree,
    get_course_list,
    get_course_progress,
    get_node_progress,
    get_user_info,
    login,
    study_session_end,
    study_session_heartbeat,
    study_session_start,
)
from haiqikeji.logging_config import DEFAULT_LOG_FILE, get_logger, setup_logging
from haiqikeji.progress import (
    _BAR_CLEAR_WIDTH,
    _render_progress_bar,
)
from haiqikeji.session import create_session
from haiqikeji.utils import (
    build_node_progress_map,
    coerce_duration_seconds,
    course_matches,
    get_resume_progress_percent,
    is_complete_progress,
    is_unexpired_course,
)

STUDY_RESULT_KEYS = ("success", "failed", "skipped")


def _new_study_results() -> dict[str, int]:
    """创建刷课统计计数器。"""
    return dict.fromkeys(STUDY_RESULT_KEYS, 0)


def _merge_study_results(target: dict[str, int], source: dict[str, int]) -> None:
    """合并刷课统计计数器。"""
    for key in STUDY_RESULT_KEYS:
        target[key] += source[key]


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。

    Returns:
        配置好的 ArgumentParser 实例。
    """
    parser = argparse.ArgumentParser(description="自动刷海启科技课程")
    parser.add_argument("-n", "--number", required=True, help="登录账号/学号")
    parser.add_argument("-p", "--password", required=True, help="登录密码")
    parser.add_argument(
        "--sid",
        "--school-id",
        type=int,
        default=10,
        dest="school_id",
        help="学校 ID，默认 10",
    )
    parser.add_argument("--cid", "--course-id", type=int, dest="course_id", help="仅刷指定课程 ID")
    parser.add_argument(
        "--cn", "--course-name", dest="course_name", help="仅刷课程名包含指定文本的课程"
    )
    parser.add_argument(
        "--chid",
        "--chapter-id",
        type=int,
        dest="chapter_id",
        help="仅刷指定章节 ID（需配合 --cid）",
    )
    parser.add_argument(
        "--nid",
        "--node-id",
        type=int,
        dest="node_id",
        help="仅刷指定小节 ID（需配合 --cid 和 --chid）",
    )
    parser.add_argument(
        "--step",
        "--progress-step",
        type=int,
        default=25,
        dest="progress_step",
        help="每次心跳之间的间隔秒数，默认25",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="播放速度倍数（0.5~3.0），默认 1.0",
    )
    parser.add_argument(
        "--skip",
        "--skip-complete",
        action="store_true",
        dest="skip_complete",
        help="跳过已完成的小节",
    )
    parser.add_argument(
        "--list",
        "--list-incomplete",
        action="store_true",
        dest="list_incomplete",
        help="仅打印未观看的课程/章节/小节，不执行刷课",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="启用 DEBUG 级别日志输出",
    )
    parser.add_argument(
        "--platform",
        choices=["haiqikeji", "yinghua"],
        default="haiqikeji",
        help="刷课平台：haiqikeji（默认）或 yinghua",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="英华平台基础地址（--platform yinghua 时必填，如 https://scauzj.xxx.com）",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=DEFAULT_LOG_FILE,
        help=f"指定日志文件路径（默认 {DEFAULT_LOG_FILE}）",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def auto_study_node(
    session: requests.Session,
    token: str,
    school_id: int,
    student_id: int,
    course_id: int,
    node_id: int,
    node_name: str,
    video_duration: Any,
    heartbeat_interval_seconds: int,
    progress_data: Any = None,
    chapter_name: str = "",
    resume_progress: bool = True,
    speed: float = 1.0,
) -> bool:
    """自动完成单个小节的学习生命周期。

    严格遵循平台协议：start -> heartbeat 循环 -> end。
    心跳循环的进度从断点续刷位置开始，逐步递增到 100%。
    每次心跳的进度增量根据视频时长和心跳间隔自动计算。
    发生错误时会发送一次当前进度心跳并结束会话。

    Returns:
        True 表示该小节学习成功完成。
    """
    logger = get_logger(__name__)
    location = f"课程《{node_name}》"
    if chapter_name:
        location = f"章节《{chapter_name}》/小节《{node_name}》"

    # 第一步：获取最新进度（用于断点续刷）
    node_progress_data = None
    if resume_progress:
        node_progress_result = get_node_progress(session, token, school_id, student_id, node_id)
        if node_progress_result.get("code") == 200:
            node_progress_data = node_progress_result.get("data")
            logger.debug(f"  当前进度: {node_progress_data}")

    # 第二步：启动学习会话
    logger.info(f"  开始小节: {node_name}")
    start_result = study_session_start(session, token, school_id, student_id, course_id, node_id)
    if start_result.get("code") != 200:
        logger.error(f"  [失败][start] {location}: {start_result.get('msg') or '学习会话启动失败'}")
        return False

    logger.info(f"  [成功][start] {location}")

    session_id = start_result.get("data")
    if not session_id:
        logger.error(f"  [失败][start] {location}: 未获取到有效 sessionId")
        return False

    session_ended = False

    def end_session_once() -> dict[str, Any] | None:
        """结束当前学习会话，确保只提交一次 end。"""
        nonlocal session_ended
        if session_ended:
            return None
        session_ended = True
        try:
            return study_session_end(session, token, session_id, course_id)
        except requests.RequestException:
            logger.warning("学习会话结束请求失败", exc_info=True)
            return None

    # 第三步：计算心跳参数
    interval_seconds = max(1, heartbeat_interval_seconds / speed)
    duration_seconds = coerce_duration_seconds(video_duration)
    if duration_seconds is None:
        logger.error(f"  [失败] {location}: 缺少有效视频时长")
        end_session_once()
        return False

    total_heartbeats = max(1, math.ceil(duration_seconds / interval_seconds))
    progress_increment = 100.0 / total_heartbeats
    # 优先使用 get_node_progress 获取的实时进度，回退到 progress_data
    if not resume_progress:
        current_progress = 0.0
    elif node_progress_data is not None:
        current_progress = get_resume_progress_percent(node_progress_data)
    else:
        current_progress = get_resume_progress_percent(progress_data)
    last_sent_progress = math.floor(current_progress)
    heartbeat_frame = 0

    try:
        # 第三步：心跳循环，直到进度达到 100%
        _TICK = 0.25  # 进度条刷新间隔（秒）
        while last_sent_progress < 100:
            # 本轮心跳的目标进度
            current_progress = min(100.0, current_progress + progress_increment)
            next_progress = min(100, max(last_sent_progress + 1, math.ceil(current_progress)))

            # 在心跳间隔内平滑推进进度条
            tick_start = time.monotonic()
            next_heartbeat_at = tick_start + interval_seconds
            base_elapsed = duration_seconds * (last_sent_progress / 100.0)
            target_elapsed = duration_seconds * (next_progress / 100.0)

            while True:
                now = time.monotonic()
                remaining = next_heartbeat_at - now
                if remaining <= 0:
                    break
                time.sleep(min(_TICK, remaining))

                frac = min(1.0, (time.monotonic() - tick_start) / interval_seconds)
                fake_elapsed = base_elapsed + (target_elapsed - base_elapsed) * frac
                bar = _render_progress_bar(fake_elapsed, duration_seconds, heartbeat_frame)
                print(bar, end="", flush=True)
                heartbeat_frame += 1

            # 到达心跳时间，发送心跳
            bar = _render_progress_bar(target_elapsed, duration_seconds, heartbeat_frame)
            print(bar, end="", flush=True)
            heartbeat_frame += 1

            heartbeat_result = study_session_heartbeat(
                session,
                token,
                session_id,
                next_progress,
                course_id,
            )
            if heartbeat_result.get("code") != 200:
                logger.error(
                    f"\r  [失败][心跳] {location}: {heartbeat_result.get('msg') or '学习心跳提交失败'}"
                )
                # 发送一次当前进度心跳保存进度
                if last_sent_progress > 0:
                    study_session_heartbeat(
                        session,
                        token,
                        session_id,
                        last_sent_progress,
                        course_id,
                    )
                end_session_once()
                return False

            last_sent_progress = next_progress

        # 清除进度条并换行
        print("\r" + " " * _BAR_CLEAR_WIDTH + "\r", end="")
        # 第四步：结束学习会话
        end_result = end_session_once()
        if end_result is None:
            logger.error(f"  [失败][end] {location}: 学习会话结束失败")
            return False
        if end_result.get("code") != 200:
            logger.error(f"  [失败][end] {location}: {end_result.get('msg') or '学习会话结束失败'}")
            return False

        logger.info(f"  [成功][end] {location}")
        logger.info(f"  [完成] {node_name}")
        return True

    except KeyboardInterrupt:
        print("\r" + " " * _BAR_CLEAR_WIDTH + "\r", end="")
        logger.info("用户中断，正在结束学习会话...")
        end_session_once()
        raise
    except requests.RequestException:
        # 清除进度条行
        print("\r" + " " * _BAR_CLEAR_WIDTH + "\r", end="")
        logger.error("请求异常", exc_info=True)
        # 网络异常时尝试发送当前进度并结束会话
        if not session_ended and last_sent_progress > 0:
            try:
                study_session_heartbeat(
                    session,
                    token,
                    session_id,
                    last_sent_progress,
                    course_id,
                )
            except requests.RequestException:
                pass
        end_session_once()
        raise


def _study_node_with_progress_policy(
    session: requests.Session,
    token: str,
    school_id: int,
    student_id: int,
    course_id: int,
    node: dict[str, Any],
    progress_data: Any,
    heartbeat_interval_seconds: int,
    skip_complete: bool,
    chapter_name: str = "",
    speed: float = 1.0,
) -> dict[str, int]:
    """按已完成/跳过/重刷策略学习单个小节。"""
    logger = get_logger(__name__)
    results = _new_study_results()
    node_id = node.get("id")
    node_name = node.get("name", "")
    if not isinstance(node_id, int):
        return results

    node_completed = is_complete_progress(progress_data)
    if node_completed:
        if skip_complete:
            logger.info(f"    - [跳过] {node_name}")
            results["skipped"] += 1
            return results
        logger.info(f"    - [重刷] {node_name}")

    success = auto_study_node(
        session,
        token,
        school_id,
        student_id,
        course_id,
        node_id,
        node_name,
        node.get("videoDuration"),
        heartbeat_interval_seconds,
        progress_data=progress_data,
        chapter_name=chapter_name,
        resume_progress=not node_completed,
        speed=speed,
    )
    if success:
        results["success"] += 1
    else:
        results["failed"] += 1
    return results


def list_incomplete_courses(
    session: requests.Session,
    token: str,
    school_id: int,
    student_id: int,
    courses: list[dict[str, Any]],
) -> bool:
    """打印未观看的课程、章节、小节层级信息。

    Args:
        session: 已配置的 HTTP 会话。
        token: 认证令牌。
        school_id: 学校 ID。
        student_id: 学生 ID。
        courses: 经过过滤的课程列表。

    Returns:
        True 表示存在未完成的小节。
    """
    logger = get_logger(__name__)
    found_any = False
    for course in courses:
        course_id = course.get("id")
        course_name = course.get("courseName", "")
        if not isinstance(course_id, int):
            continue

        # 一次调用获取课程的章节-小节树形结构
        tree_result = get_course_chapter_tree(session, token, school_id, course_id, student_id)
        if tree_result.get("code") != 200:
            continue

        chapters = tree_result.get("data") or []

        # 获取该课程的学习进度
        progress_list_result = get_course_progress(session, token, school_id, student_id, course_id)
        progress_map: dict[int, dict[str, Any]] = {}
        if progress_list_result.get("code") == 200:
            progress_map = build_node_progress_map(progress_list_result.get("data"))

        has_incomplete = False
        course_output_lines: list[str] = []

        for chapter in chapters:
            chapter_id = chapter.get("id")
            chapter_name = chapter.get("name", "")
            if not isinstance(chapter_id, int):
                continue

            nodes = chapter.get("children") or []
            incomplete_nodes: list[tuple[int, str]] = []

            for node in nodes:
                node_id = node.get("id")
                node_name = node.get("name", "")
                if not isinstance(node_id, int):
                    continue

                progress_data = progress_map.get(node_id)
                if not is_complete_progress(progress_data):
                    incomplete_nodes.append((node_id, node_name))

            if incomplete_nodes:
                has_incomplete = True
                course_output_lines.append(f"  [{chapter_id}] {chapter_name}")
                for node_id, node_name in incomplete_nodes:
                    course_output_lines.append(f"    - [{node_id}] {node_name}")

        if has_incomplete:
            found_any = True
            logger.info(f"课程 [{course_id}] {course_name}")
            for line in course_output_lines:
                logger.info(line)

    return found_any


def study_chapter(
    session: requests.Session,
    token: str,
    school_id: int,
    student_id: int,
    course_id: int,
    course_name: str,
    chapter: dict[str, Any],
    nodes: list[dict[str, Any]],
    progress_map: dict[int, dict[str, Any]],
    heartbeat_interval_seconds: int,
    skip_complete: bool,
    speed: float = 1.0,
) -> dict[str, int]:
    """学习单个章节的所有小节。

    Args:
        session: 已配置的 HTTP 会话。
        token: 认证令牌。
        school_id: 学校 ID。
        student_id: 学生 ID。
        course_id: 课程 ID。
        course_name: 课程名称。
        chapter: 章节信息字典。
        nodes: 该章节下的小节列表（来自章节的 children 字段）。
        progress_map: 小节进度映射 {node_id: progress_data}。
        heartbeat_interval_seconds: 心跳间隔秒数。
        skip_complete: 是否跳过已完成的小节。

    Returns:
        统计字典，包含 success/failed/skipped 三个计数器。
    """
    logger = get_logger(__name__)
    results = _new_study_results()
    chapter_id = chapter.get("id")
    chapter_name = chapter.get("name", "")

    if not isinstance(chapter_id, int):
        return results

    logger.info(f"  [{chapter_id}] {chapter_name}")

    for node in nodes:
        node_id = node.get("id")
        if not isinstance(node_id, int):
            continue

        node_results = _study_node_with_progress_policy(
            session,
            token,
            school_id,
            student_id,
            course_id,
            node,
            progress_map.get(node_id),
            heartbeat_interval_seconds,
            skip_complete,
            chapter_name,
            speed=speed,
        )
        _merge_study_results(results, node_results)

    return results


def study_course(
    session: requests.Session,
    token: str,
    school_id: int,
    student_id: int,
    course: dict[str, Any],
    heartbeat_interval_seconds: int,
    skip_complete: bool,
    chapter_id: int | None = None,
    node_id: int | None = None,
    speed: float = 1.0,
) -> dict[str, int]:
    """学习单个课程。

    Args:
        session: 已配置的 HTTP 会话。
        token: 认证令牌。
        school_id: 学校 ID。
        student_id: 学生 ID。
        course: 课程信息字典。
        heartbeat_interval_seconds: 心跳间隔秒数。
        skip_complete: 是否跳过已完成的小节。
        chapter_id: 仅学习指定章节（None 表示全部）。
        node_id: 仅学习指定小节（None 表示全部）。

    Returns:
        统计字典，包含 success/failed/skipped 三个计数器。
    """
    logger = get_logger(__name__)
    results = _new_study_results()
    course_id = course.get("id")
    course_name = course.get("courseName", "")

    if not isinstance(course_id, int):
        return results

    logger.info(f"\n课程 [{course_id}] {course_name}")

    # 一次调用获取课程的章节-小节树形结构
    tree_result = get_course_chapter_tree(session, token, school_id, course_id, student_id)
    if tree_result.get("code") != 200:
        logger.error(
            f"获取课程章节失败：课程《{course_name}》: {tree_result.get('msg') or '接口返回失败'}"
        )
        results["failed"] += 1
        return results

    chapters = tree_result.get("data") or []

    # 获取该课程的学习进度
    progress_list_result = get_course_progress(session, token, school_id, student_id, course_id)
    progress_map: dict[int, dict[str, Any]] = {}
    if progress_list_result.get("code") == 200:
        progress_map = build_node_progress_map(progress_list_result.get("data"))
    else:
        logger.warning(
            f"获取课程进度失败：课程《{course_name}》: {progress_list_result.get('msg') or '将继续处理课程内容'}"
        )

    # 如果指定了 node_id，需要找到对应的章节
    if node_id is not None:
        for chapter in chapters:
            cid = chapter.get("id")
            if not isinstance(cid, int):
                continue
            if chapter_id is not None and cid != chapter_id:
                continue

            for node in chapter.get("children") or []:
                if node.get("id") == node_id:
                    node_results = _study_node_with_progress_policy(
                        session,
                        token,
                        school_id,
                        student_id,
                        course_id,
                        node,
                        progress_map.get(node_id),
                        heartbeat_interval_seconds,
                        skip_complete,
                        chapter.get("name", ""),
                        speed=speed,
                    )
                    _merge_study_results(results, node_results)
                    return results

        logger.error(f"未找到小节 ID {node_id}")
        results["failed"] += 1
        return results

    # 遍历章节
    for chapter in chapters:
        cid = chapter.get("id")
        if not isinstance(cid, int):
            continue
        if chapter_id is not None and cid != chapter_id:
            continue

        chapter_results = study_chapter(
            session,
            token,
            school_id,
            student_id,
            course_id,
            course_name,
            chapter,
            chapter.get("children") or [],
            progress_map,
            heartbeat_interval_seconds,
            skip_complete,
            speed=speed,
        )
        _merge_study_results(results, chapter_results)

    return results


def main() -> int:
    """程序主入口。

    Returns:
        退出码：0 表示成功，1 表示失败。
    """
    args = build_parser().parse_args()

    # 初始化日志系统
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = setup_logging(log_level=log_level, log_file=args.log_file)

    # 英华平台路由
    if args.platform == "yinghua":
        if not args.url:
            logger.error("使用英华平台时必须通过 --url 指定平台地址")
            logger.error("示例: --platform yinghua --url https://scauzj.xxx.com")
            return 1

        # 规范化 URL：去除末尾斜杠
        base_url = args.url.rstrip("/")

        # 校验 URL 格式
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            logger.error(f"--url 格式无效: {args.url}")
            logger.error("示例: --url https://scauzj.xxx.com")
            return 1

        from haiqikeji.yinghua.cli import main as yinghua_main

        return yinghua_main(
            username=args.number,
            password=args.password,
            base_url=base_url,
            speed=args.speed,
            skip_complete=args.skip_complete,
        )

    session = create_session()

    try:
        logger.info(f"自动刷课工具 | 用户: {args.number}")
        # 参数验证
        if args.node_id is not None:
            if args.course_id is None or args.chapter_id is None:
                logger.error("--nid 需要同时指定 --cid 和 --chid")
                return 1
        elif args.chapter_id is not None:
            if args.course_id is None:
                logger.error("--chid 需要同时指定 --cid")
                return 1

        if not (0.5 <= args.speed <= 3.0):
            logger.error("--speed 必须在 0.5 到 3.0 之间")
            return 1

        # 登录
        logger.info("正在登录...")
        login_result = login(session, args.number, args.password, args.school_id)
        if login_result.get("code") != 200:
            logger.error("登录失败")
            logger.error(f"msg: {login_result.get('msg') or '账号、密码或学校 ID 可能无效'}")
            return 1

        logger.debug("登录成功，正在提取 token...")
        token = extract_token(login_result)

        # 验证 token 有效性
        logger.info("正在验证用户信息...")
        user_info_result = get_user_info(session, token)
        if user_info_result.get("code") != 200:
            logger.error("获取用户信息失败")
            logger.error(f"msg: {user_info_result.get('msg') or '当前会话无法通过用户校验'}")
            return 1

        user = user_info_result.get("data") or {}
        student_id = user.get("id")
        if not isinstance(student_id, int) or isinstance(student_id, bool):
            raise ValueError("用户信息中缺少有效 student_id")

        logger.debug(f"学生 ID: {student_id}")

        # 获取课程列表
        logger.info("正在获取课程列表...")
        course_list_result = get_course_list(session, token, args.school_id, student_id)
        if course_list_result.get("code") != 200:
            logger.error("获取课程列表失败")
            logger.error(f"msg: {course_list_result.get('msg') or '课程列表接口返回失败'}")
            return 1

        # 过滤课程
        courses = course_list_result.get("data") or []
        today = date.today()
        filtered_courses = [
            course
            for course in courses
            if is_unexpired_course(course, today)
            and course_matches(course, args.course_id, args.course_name)
        ]

        if not filtered_courses:
            logger.info("没有匹配的可刷课程")
            return 0

        logger.info(f"匹配课程: {len(filtered_courses)} 个")

        # 打印未观看课程信息
        if args.list_incomplete:
            has_incomplete = list_incomplete_courses(
                session=session,
                token=token,
                school_id=args.school_id,
                student_id=student_id,
                courses=filtered_courses,
            )
            if not has_incomplete:
                logger.info("所有课程小节均已完成，没有需要刷课的内容")
            return 0

        # 执行刷课
        logger.info("\n开始自动刷课")
        if args.speed != 1.0:
            logger.info(
                f"播放速度: {args.speed}x（心跳间隔 {args.progress_step}s → {args.progress_step / args.speed:.1f}s）"
            )
        study_results = _new_study_results()

        for course in filtered_courses:
            course_results = study_course(
                session=session,
                token=token,
                school_id=args.school_id,
                student_id=student_id,
                course=course,
                heartbeat_interval_seconds=args.progress_step,
                skip_complete=args.skip_complete,
                chapter_id=args.chapter_id,
                node_id=args.node_id,
                speed=args.speed,
            )
            _merge_study_results(study_results, course_results)

        # 输出统计结果
        total = study_results["success"] + study_results["failed"] + study_results["skipped"]
        logger.info("\n刷课完成")
        logger.info(
            f"成功 {study_results['success']} | 失败 {study_results['failed']} | 跳过 {study_results['skipped']} | 总计 {total}"
        )
        return 0

    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else "未知"
        logger.error(f"HTTP 请求失败（状态码: {status_code}）")
        return 1
    except requests.RequestException:
        logger.error("请求失败，请检查网络连接或稍后重试")
        return 1
    except ValueError as exc:
        logger.error(f"响应解析失败: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
