import time
import os
from yutto.mux import 获取所有下载索引
from loguru import logger
from pathlib import Path

def 执行抓取():
    # sessdata 从 ~/.sessdata 文件中读取
    sessdata = Path("/Users/transmux/.sessdata").read_text()

    命令行参数 = [
        "-b",
        "--proxy no",
        "--login-strict",
        "--with-metadata",
        "-d",
        "/Users/transmux/Projects/Backup/Bili收藏视频/",
        "-c",
        sessdata,
    ]

    下载索引 = 获取所有下载索引()["list"]
    下载索引 = [item["链接"] for item in 下载索引]

    logger.info(f"共有 {len(下载索引)} 个下载索引")

    for index, item in enumerate(下载索引):
        logger.info(f"开始下载 {item} ({index + 1}/{len(下载索引)})")
        # os 执行命令
        os.system(f"yutto {' '.join(命令行参数)} {item}")

        logger.info(f"{item} 抓取完成，等待10秒 ({index + 1}/{len(下载索引)})")
        time.sleep(10)

    logger.info("所有下载完成")


if __name__ == "__main__":
    while True:
        执行抓取()
        logger.info(f"抓取完成，等待3小时")
        time.sleep(3 * 60 * 60)
