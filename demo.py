"""Demo: spawn a fleet of medical robots, dispatch tasks, shut down cleanly.

Run:
    python demo.py
    python demo.py --robots 4 --tasks 20 --capacity 5
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time
import unicodedata
from typing import List

from dispatcher import TaskDispatcher
from medical_task import MedicalTask, TaskType
from robot import MedicalRobot

logger = logging.getLogger("medbot.demo")

# ----------------------------------------------------------------------------
# Presentation helpers (terminal colors + width-aware alignment for CJK text).
# ----------------------------------------------------------------------------
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"

# Stable per-robot color palette (Robot-1 -> CYAN, Robot-2 -> GREEN, ...).
ROBOT_PALETTE = [CYAN, GREEN, MAGENTA, BLUE, YELLOW, RED]


def supports_color(disabled: bool) -> bool:
    """Color only when the user allows it and stdout is a real terminal."""
    if disabled or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def color_for_thread(name: str) -> str:
    if name.startswith("Robot-"):
        try:
            idx = int(name.split("-", 1)[1]) - 1
        except ValueError:
            idx = 0
        return ROBOT_PALETTE[idx % len(ROBOT_PALETTE)]
    return BOLD  # MainThread and others


def disp_width(text: str) -> int:
    """Display width, counting CJK/full-width characters as 2 columns."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def pad(text: str, width: int, align: str = "left") -> str:
    gap = max(0, width - disp_width(text))
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


class ColorFormatter(logging.Formatter):
    """Colorize each log line by robot (thread) and by event type."""

    def __init__(self, use_color: bool) -> None:
        super().__init__(datefmt="%H:%M:%S")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, self.datefmt)
        name = record.threadName or ""
        msg = record.getMessage()
        if not self.use_color:
            return f"{ts} | {name:<10} | {msg}"

        name_c = color_for_thread(name)
        if record.levelno >= logging.WARNING:
            msg_c = YELLOW
        elif "✔" in msg:
            msg_c = GREEN
        elif "▶" in msg:
            msg_c = name_c
        elif "启动" in msg or "已停止" in msg:
            msg_c = DIM
        else:
            msg_c = ""
        return (
            f"{DIM}{ts}{RESET} {DIM}│{RESET} "
            f"{BOLD}{name_c}{name:<10}{RESET} {DIM}│{RESET} "
            f"{msg_c}{msg}{RESET}"
        )


def configure_logging(use_color: bool) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(ColorFormatter(use_color))
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def print_summary(
    robots: List[MedicalRobot],
    total_tasks: int,
    wall_seconds: float,
    use_color: bool,
) -> None:
    """Show how the fleet shared the load, to make collaboration measurable."""

    def c(text: str, color: str) -> str:
        return f"{color}{text}{RESET}" if use_color else text

    processed_total = sum(r.stats.processed for r in robots)
    abandoned_total = sum(r.stats.abandoned for r in robots)
    serial_seconds = sum(r.stats.busy_seconds for r in robots)
    max_busy = max((r.stats.busy_seconds for r in robots), default=0.0) or 1.0
    speedup = serial_seconds / wall_seconds if wall_seconds > 0 else 0.0
    bar_cells = 16

    name_w, num_w, busy_w = 12, 8, 10
    inner = name_w + num_w * 2 + busy_w + 2 + bar_cells
    rule = "─" * inner

    title = " 协作结果汇总 "
    side = (inner - disp_width(title)) // 2
    banner = "═" * side + title + "═" * (inner - side - disp_width(title))

    print()
    print(c(banner, BOLD + CYAN))
    print(
        "  "
        + pad("机器人", name_w)
        + pad("已处理", num_w, "right")
        + pad("已放弃", num_w, "right")
        + pad("忙碌(s)", busy_w, "right")
        + "  "
        + pad("负载分布", bar_cells)
    )
    print("  " + c(rule, DIM))
    for robot in robots:
        s = robot.stats
        cells = round(bar_cells * s.busy_seconds / max_busy)
        bar = "█" * cells
        abandoned_txt = pad(str(s.abandoned), num_w, "right")
        if s.abandoned:
            abandoned_txt = c(abandoned_txt, RED)
        print(
            "  "
            + c(pad(robot.name, name_w), color_for_thread(robot.name))
            + pad(str(s.processed), num_w, "right")
            + abandoned_txt
            + pad(f"{s.busy_seconds:.1f}", busy_w, "right")
            + "  "
            + c(bar, color_for_thread(robot.name))
        )
    print("  " + c(rule, DIM))
    print(
        "  "
        + pad("合计", name_w)
        + pad(str(processed_total), num_w, "right")
        + pad(str(abandoned_total), num_w, "right")
        + pad(f"{serial_seconds:.1f}", busy_w, "right")
    )
    print()
    print(
        "  "
        + c(f"⏱  墙钟耗时 {wall_seconds:.1f}s", BOLD)
        + c("  vs  ", DIM)
        + f"串行预计 {serial_seconds:.1f}s"
        + c("   →   ", DIM)
        + c(f"加速比 {speedup:.1f}×", BOLD + GREEN)
    )
    print(
        "  "
        + c(
            f"已处理 {processed_total}/{total_tasks} 个任务，"
            f"放弃 {abandoned_total} 个",
            DIM,
        )
    )
    print()


def build_tasks(count: int) -> list[MedicalTask]:
    types = list(TaskType)
    tasks = []
    for i in range(count):
        task_type = random.choice(types)
        tasks.append(
            MedicalTask(
                task_type=task_type,
                target=f"病房{random.randint(101, 110)}",
                duration=round(random.uniform(0.3, 1.2), 1),
            )
        )
    return tasks


def main() -> None:
    parser = argparse.ArgumentParser(description="多智能体医疗机器人演示")
    parser.add_argument("--robots", type=int, default=3, help="机器人数量")
    parser.add_argument("--tasks", type=int, default=15, help="医疗任务数量")
    parser.add_argument("--capacity", type=int, default=5, help="单机器人队列容量阈值")
    parser.add_argument("--seed", type=int, default=42, help="随机种子(可复现)")
    parser.add_argument("--no-color", action="store_true", help="禁用彩色输出")
    args = parser.parse_args()

    random.seed(args.seed)
    use_color = supports_color(args.no_color)
    configure_logging(use_color)

    robots = [MedicalRobot(name=f"Robot-{i + 1}") for i in range(args.robots)]
    for robot in robots:
        robot.start()

    dispatcher = TaskDispatcher(robots, capacity=args.capacity)

    tasks = build_tasks(args.tasks)
    logger.info("开始派发 %d 个任务给 %d 个机器人...", len(tasks), len(robots))
    started = time.perf_counter()
    dispatcher.dispatch_all(tasks)

    logger.info("全部任务已派发，等待机器人处理完毕并停止...")
    for robot in robots:
        robot.stop(drain=True)
    for robot in robots:
        robot.join()
    wall_seconds = time.perf_counter() - started

    logger.info("所有机器人已安全停止，演示结束。")
    print_summary(robots, len(tasks), wall_seconds, use_color)


if __name__ == "__main__":
    main()
