import sys
import os

# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
from stream import rich_console_stream_call


def main():
    parser = argparse.ArgumentParser(description="Research Agent - 流式输出测试")
    parser.add_argument("--task", type=str, default="请给讲个笑话吧", help="任务提示词")
    parser.add_argument("--thread-id", type=str, default=None, help="线程ID用于追踪")
    args = parser.parse_args()

    rich_console_stream_call(args.task, args.thread_id)


if __name__ == '__main__':
    main()
