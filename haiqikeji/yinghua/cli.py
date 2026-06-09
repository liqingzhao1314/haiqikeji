"""英华平台 CLI 业务逻辑。

包含英华平台的刷课核心流程：验证码登录、课程发现、学时提交循环。
"""

from __future__ import annotations

import time

import requests

from haiqikeji.logging_config import get_logger
from haiqikeji.progress import _BAR_CLEAR_WIDTH, _render_progress_bar
from haiqikeji.yinghua.api import (
    DEFAULT_BASE_URL,
    get_api_token,
    get_captcha_image,
    get_incomplete_course_ids,
    get_study_records,
    get_video_progress,
    login_with_captcha,
    recognize_captcha,
    submit_study_time,
)
from haiqikeji.yinghua.session import create_session

# 进度条平滑刷新间隔（秒）
_TICK = 0.25


def parse_time_to_seconds(time_str: str) -> int:
    """将时间字符串 (HH:MM:SS) 转换为秒数。

    Args:
        time_str: 时间字符串，格式为 HH:MM:SS 或 MM:SS 或 SS。

    Returns:
        总秒数，解析失败返回 0。
    """
    try:
        parts = time_str.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
        if len(parts) == 2:
            minutes, seconds = map(int, parts)
            return minutes * 60 + seconds
        if len(parts) == 1:
            return int(parts[0])
        return 0
    except (ValueError, AttributeError):
        try:
            return int(time_str)
        except (ValueError, TypeError):
            return 0


def _do_login(
    session: requests.Session,
    username: str,
    password: str,
    base_url: str,
) -> bool:
    """执行验证码登录流程。

    自动获取验证码、OCR 识别、提交登录请求。最多重试 3 次。

    Args:
        session: HTTP 会话。
        username: 用户名/学号。
        password: 密码。
        base_url: 英华平台基础地址。

    Returns:
        登录是否成功。
    """
    logger = get_logger(__name__)

    for attempt in range(1, 4):
        logger.info(f"尝试登录（第 {attempt} 次）...")
        try:
            captcha_bytes = get_captcha_image(session, base_url)
            captcha_code = recognize_captcha(captcha_bytes)
            logger.info(f"验证码识别结果: {captcha_code}")
        except ImportError:
            logger.error("未安装 ddddocr，无法自动识别验证码")
            logger.error("请运行: uv sync --extra yinghua")
            return False
        except Exception:
            logger.warning("获取/识别验证码失败", exc_info=True)
            continue

        result = login_with_captcha(session, username, password, captcha_code, base_url)
        if result.get("status", False):
            logger.info("登录成功")
            return True

        logger.warning(f"登录失败: {result}")

    logger.error("登录重试次数已用完")
    return False


def _do_update_progress(
    session: requests.Session,
    token: str,
    node_id: str,
    speed: float,
    base_url: str,
) -> bool:
    """更新单个节点的学习进度直到完成。

    通过每隔 30 秒提交一次学时来模拟学习进度。
    在提交间隔内平滑渲染进度条动画。

    Args:
        session: HTTP 会话。
        token: API 令牌。
        node_id: 章节 nodeId。
        speed: 播放速度倍数。
        base_url: 英华平台基础地址。

    Returns:
        学习是否成功完成。
    """
    logger = get_logger(__name__)
    study_id = 0
    study_time = 1
    frame = 0

    # 初始提交
    result = submit_study_time(session, token, node_id, study_time, study_id, base_url)
    if not result.get("status", False):
        logger.warning(f"课程 {node_id} 初始提交学时失败")
        return False

    study_id = result.get("result", {}).get("data", {}).get("studyId", 0)

    # 获取初始进度
    progress_result = get_video_progress(session, token, node_id, base_url)
    progress_data = progress_result.get("result", {}).get("data", {})
    video_duration = progress_data.get("videoDuration", 0)
    study_total = progress_data.get("study_total", {})
    studied_duration = study_total.get("duration", "") if study_total else ""

    if progress_data.get("cheat", {}).get("state", 0) != 0:
        logger.error(f"课程 {node_id} 存在作弊检测警告，请检查账号安全！")
        return False

    total_sec = parse_time_to_seconds(str(video_duration))
    if total_sec <= 0:
        logger.error(f"课程 {node_id} 视频时长无效: {video_duration}")
        return False

    logger.info(f"课程 {node_id}, 视频总时长: {total_sec} 秒")

    # 计算实际间隔（按倍速缩短）
    interval = max(1, int(30 / speed))

    def _animate_progress(elapsed_from: float, elapsed_to: float, duration: float) -> None:
        """在 interval 秒内平滑推进进度条。"""
        nonlocal frame
        tick_start = time.monotonic()
        end_at = tick_start + interval

        while True:
            now = time.monotonic()
            remaining = end_at - now
            if remaining <= 0:
                break
            time.sleep(min(_TICK, remaining))

            frac = min(1.0, (time.monotonic() - tick_start) / interval)
            fake_elapsed = elapsed_from + (elapsed_to - elapsed_from) * frac
            bar = _render_progress_bar(fake_elapsed, duration, frame)
            print(bar, end="", flush=True)
            frame += 1

        # 到达目标，渲染精确位置
        bar = _render_progress_bar(elapsed_to, duration, frame)
        print(bar, end="", flush=True)
        frame += 1

    # 初始进度位置
    studied_sec = parse_time_to_seconds(str(studied_duration))
    current_elapsed = float(min(studied_sec, total_sec))

    try:
        # 持续提交直到完成
        while True:
            studied_sec = parse_time_to_seconds(str(studied_duration))
            remaining_sec = total_sec - studied_sec

            if remaining_sec <= 0:
                break

            if remaining_sec <= interval:
                study_time += remaining_sec
            else:
                study_time += interval

            # 本轮动画的目标位置（按累计 study_time 推算）
            target_elapsed = min(float(study_time), float(total_sec))

            # 平滑渲染进度条
            _animate_progress(current_elapsed, target_elapsed, float(total_sec))

            # 到达提交时间，发送学时
            result = submit_study_time(session, token, node_id, study_time, study_id, base_url)
            if not result.get("status", False):
                print("\r" + " " * _BAR_CLEAR_WIDTH + "\r", end="")
                logger.warning(f"课程 {node_id} 提交学时失败")
                return False

            study_id = result.get("result", {}).get("data", {}).get("studyId", study_id)

            # 用服务端真实进度校准当前位置
            progress_result = get_video_progress(session, token, node_id, base_url)
            progress_data = progress_result.get("result", {}).get("data", {})
            study_total = progress_data.get("study_total", {})
            studied_duration = study_total.get("duration", "") if study_total else ""

            real_studied_sec = parse_time_to_seconds(str(studied_duration))
            current_elapsed = float(min(real_studied_sec, total_sec))

            # 用真实进度重新渲染一帧
            bar = _render_progress_bar(current_elapsed, float(total_sec), frame)
            print(bar, end="", flush=True)
            frame += 1

            if remaining_sec <= interval:
                break

        # 清除进度条并换行
        print("\r" + " " * _BAR_CLEAR_WIDTH + "\r", end="")
        logger.info(f"  [完成] 课程 {node_id} 学习完成")
        return True

    except KeyboardInterrupt:
        print("\r" + " " * _BAR_CLEAR_WIDTH + "\r", end="")
        logger.info("用户中断")
        raise
    except requests.RequestException:
        print("\r" + " " * _BAR_CLEAR_WIDTH + "\r", end="")
        logger.error("请求异常", exc_info=True)
        raise


def main(
    username: str,
    password: str,
    base_url: str = DEFAULT_BASE_URL,
    speed: float = 1.0,
    skip_complete: bool = False,
    verbose: bool = False,
) -> int:
    """英华平台刷课主入口。

    Args:
        username: 登录用户名/学号。
        password: 登录密码。
        base_url: 英华平台基础地址。
        speed: 播放速度倍数（0.5~3.0）。
        skip_complete: 是否跳过已完成的课程。
        verbose: 是否启用 DEBUG 日志。

    Returns:
        退出码：0 表示成功，1 表示失败。
    """
    logger = get_logger(__name__)
    logger.info(f"英华平台自动刷课工具 | 用户: {username} | 地址: {base_url}")

    session = create_session()

    # 第一步：登录
    if not _do_login(session, username, password, base_url):
        return 1

    # 第二步：获取 API 令牌
    try:
        token = get_api_token(session, username, password, base_url)
        logger.info("获取 API 令牌成功")
    except (requests.RequestException, KeyError):
        logger.error("获取 API 令牌失败", exc_info=True)
        return 1

    # 第三步：获取未完成课程
    try:
        incomplete_courses = get_incomplete_course_ids(session, base_url)
    except ImportError:
        logger.error("未安装 lxml，无法解析课程页面")
        logger.error("请运行: uv sync --extra yinghua")
        return 1
    except requests.RequestException:
        logger.error("获取课程列表失败", exc_info=True)
        return 1

    if not incomplete_courses:
        logger.info("没有未完成的课程")
        return 0

    logger.info(f"未完成课程: {len(incomplete_courses)} 个")

    # 第四步：遍历课程，获取章节并刷课
    success_count = 0
    fail_count = 0

    for course in incomplete_courses:
        course_id = course["courseId"]
        course_title = course["title"]
        logger.info(f"\n课程: 《{course_title}》 (ID: {course_id})")

        try:
            records = get_study_records(session, course_id, base_url)
        except requests.RequestException:
            logger.error(f"获取课程 {course_id} 学习记录失败", exc_info=True)
            fail_count += 1
            continue

        if not records:
            logger.info(f"课程 {course_id} 无学习记录")
            continue

        # 筛选未学习的记录
        unlearned = {
            r["id"]: r.get("chapterId", "") for r in records if "未学" in r.get("state", "")
        }

        if not unlearned:
            logger.info(f"课程 {course_id} 所有章节已学习")
            continue

        logger.info(f"需学习章节: {len(unlearned)} 个")

        for node_id, _chapter_id in unlearned.items():
            node_id_str = str(node_id)
            logger.info("正在学习: nodeId=%s", node_id_str)

            success = _do_update_progress(session, token, node_id_str, speed, base_url)
            if success:
                success_count += 1
            else:
                fail_count += 1

    # 输出统计
    logger.info("\n刷课完成")
    logger.info("成功 %d | 失败 %d", success_count, fail_count)
    return 0
