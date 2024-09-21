# pyright: basic

from __future__ import annotations

import json
import logging
import math
import random
import re
from typing import TYPE_CHECKING, TypeVar

from biliass._core import (
    Comment,
    CommentPosition,
    Rows,
    ass_escape,
    convert_color,
    convert_flash_rotation,
    convert_timestamp,
    find_alternative_row,
    get_zoom_factor,
    mark_comment_row,
    read_comments_from_protobuf,
    read_comments_from_xml,
    test_free_rows,
    write_comment,
    write_head,
)

if TYPE_CHECKING:
    from collections.abc import Callable


T = TypeVar("T")


def read_comments_bilibili_xml(text: str | bytes, fontsize: float) -> list[Comment]:
    if isinstance(text, bytes):
        text = text.decode()
    return read_comments_from_xml(text, fontsize)


def read_comments_bilibili_protobuf(protobuf: bytes | str, fontsize: float) -> list[Comment]:
    assert isinstance(protobuf, bytes), "protobuf supports bytes only"
    return read_comments_from_protobuf(protobuf, fontsize)


class AssText:
    def __init__(self):
        self._text = ""

    def write_comment_special(self, comment: Comment, width, height, styleid):
        # BiliPlayerSize = (512, 384)  # Bilibili player version 2010
        # BiliPlayerSize = (540, 384)  # Bilibili player version 2012
        # BiliPlayerSize = (672, 438)  # Bilibili player version 2014
        BiliPlayerSize = (891, 589)  # Bilibili player version 2021 (flex)
        ZoomFactor = get_zoom_factor(BiliPlayerSize, (width, height))

        def get_position(InputPos, isHeight):
            isHeight = int(isHeight)  # True -> 1
            if isinstance(InputPos, int):
                return ZoomFactor[0] * InputPos + ZoomFactor[isHeight + 1]
            elif isinstance(InputPos, float):
                if InputPos > 1:
                    return ZoomFactor[0] * InputPos + ZoomFactor[isHeight + 1]
                else:
                    return BiliPlayerSize[isHeight] * ZoomFactor[0] * InputPos + ZoomFactor[isHeight + 1]
            else:
                try:
                    InputPos = int(InputPos)
                except ValueError:
                    InputPos = float(InputPos)
                return get_position(InputPos, isHeight)

        try:
            special_comment_data = json.loads(comment.comment)
            if not isinstance(special_comment_data, list):
                raise ValueError("Invalid comment")
            comment_args = safe_list(special_comment_data)
            text = ass_escape(str(comment_args[4]).replace("/n", "\n"))
            from_x = comment_args.get(0, 0)
            from_y = comment_args.get(1, 0)
            to_x = comment_args.get(7, from_x)
            to_y = comment_args.get(8, from_y)
            from_x = get_position(from_x, False)
            from_y = get_position(from_y, True)
            to_x = get_position(to_x, False)
            to_y = get_position(to_y, True)
            alpha = safe_list(str(comment_args.get(2, "1")).split("-"))
            from_alpha = float(alpha.get(0, 1))  # pyright: ignore
            to_alpha = float(alpha.get(1, from_alpha))  # pyright: ignore
            from_alpha = 255 - round(from_alpha * 255)
            to_alpha = 255 - round(to_alpha * 255)
            rotate_z = int(comment_args.get(5, 0))  # pyright: ignore
            rotate_y = int(comment_args.get(6, 0))  # pyright: ignore
            lifetime = float(wrap_default(comment_args.get(3, 4500), 4500))
            duration = int(comment_args.get(9, lifetime * 1000))  # pyright: ignore
            delay = int(comment_args.get(10, 0))  # pyright: ignore
            fontface = comment_args.get(12)
            isborder = comment_args.get(11, "true")
            from_rotarg = convert_flash_rotation(rotate_y, rotate_z, from_x, from_y, width, height)
            to_rotarg = convert_flash_rotation(rotate_y, rotate_z, to_x, to_y, width, height)
            styles = ["\\org(%d, %d)" % (width / 2, height / 2)]
            if from_rotarg[0:2] == to_rotarg[0:2]:
                styles.append("\\pos({:.0f}, {:.0f})".format(*from_rotarg[0:2]))
            else:
                styles.append(
                    "\\move({:.0f}, {:.0f}, {:.0f}, {:.0f}, {:.0f}, {:.0f})".format(
                        *(from_rotarg[0:2] + to_rotarg[0:2] + (delay, delay + duration))
                    )
                )
            styles.append("\\frx{:.0f}\\fry{:.0f}\\frz{:.0f}\\fscx{:.0f}\\fscy{:.0f}".format(*from_rotarg[2:7]))
            if (from_x, from_y) != (to_x, to_y):
                styles.append(f"\\t({delay:d}, {delay + duration:d}, ")
                styles.append("\\frx{:.0f}\\fry{:.0f}\\frz{:.0f}\\fscx{:.0f}\\fscy{:.0f}".format(*to_rotarg[2:7]))
                styles.append(")")
            if fontface:
                styles.append(f"\\fn{ass_escape(fontface)}")
            styles.append("\\fs%.0f" % (comment.size * ZoomFactor[0]))
            if comment.color != 0xFFFFFF:
                styles.append(f"\\c&H{convert_color(comment.color)}&")
                if comment.color == 0x000000:
                    styles.append("\\3c&HFFFFFF&")
            if from_alpha == to_alpha:
                styles.append(f"\\alpha&H{from_alpha:02X}")
            elif (from_alpha, to_alpha) == (255, 0):
                styles.append(f"\\fad({lifetime * 1000:.0f},0)")
            elif (from_alpha, to_alpha) == (0, 255):
                styles.append(f"\\fad(0, {lifetime * 1000:.0f})")
            else:
                styles.append(
                    f"\\fade({from_alpha:d}, {to_alpha:d}, {to_alpha:d}, 0, {lifetime * 1000:.0f}, {lifetime * 1000:.0f}, {lifetime * 1000:.0f})"
                )
            if isborder == "false":
                styles.append("\\bord0")
            self._text += "Dialogue: -1,{start},{end},{styleid},,0,0,0,,{{{styles}}}{text}\n".format(
                start=convert_timestamp(comment.timeline),
                end=convert_timestamp(comment.timeline + lifetime),
                styles="".join(styles),
                text=text,
                styleid=styleid,
            )
        except (IndexError, ValueError):
            try:
                logging.warning(f"Invalid comment: {comment.comment!r}")
            except IndexError:
                logging.warning(f"Invalid comment: {comment!r}")

    def write_head(self, width: int, height: int, fontface: str, fontsize: float, alpha: float, styleid: str) -> None:
        self._text += write_head(width, height, fontface, fontsize, alpha, styleid)

    def write_comment(
        self,
        comment: Comment,
        row: int,
        width: int,
        height: int,
        bottom_reserved: int,
        fontsize: float,
        duration_marquee: float,
        duration_still: float,
        styleid: str,
    ):
        self._text += write_comment(
            comment,
            row,
            width,
            height,
            bottom_reserved,
            fontsize,
            duration_marquee,
            duration_still,
            styleid,
        )

    def to_string(self):
        return self._text


def process_comments(
    comments: list[Comment],
    width: int,
    height: int,
    bottom_reserved: int,
    fontface: str,
    fontsize: float,
    alpha: float,
    duration_marquee: float,
    duration_still: float,
    filters_regex,
    reduced: bool,
    progress_callback,
):
    styleid = f"biliass_{random.randint(0, 0xFFFF):04x}"
    ass = AssText()
    ass.write_head(width, height, fontface, fontsize, alpha, styleid)
    rows = Rows(4, height - bottom_reserved + 1)
    for idx, comment in enumerate(comments):
        if progress_callback and idx % 1000 == 0:
            progress_callback(idx, len(comments))
        if comment.pos in (
            CommentPosition.Scroll,
            CommentPosition.Bottom,
            CommentPosition.Top,
            CommentPosition.Reversed,
        ):
            skip = False
            for filter_regex in filters_regex:
                if filter_regex and filter_regex.search(comment.comment):
                    skip = True
                    break
            if skip:
                continue
            row = 0
            rowmax = height - bottom_reserved - comment.height
            while row <= rowmax:
                freerows = test_free_rows(
                    rows,
                    comment,
                    row,
                    width,
                    height,
                    bottom_reserved,
                    duration_marquee,
                    duration_still,
                )
                if freerows >= comment.height:
                    mark_comment_row(rows, comment, row)
                    ass.write_comment(
                        comment,
                        row,
                        width,
                        height,
                        bottom_reserved,
                        fontsize,
                        duration_marquee,
                        duration_still,
                        styleid,
                    )
                    break
                else:
                    row += freerows or 1
            else:
                if not reduced:
                    row = find_alternative_row(rows, comment, height, bottom_reserved)
                    mark_comment_row(rows, comment, row)
                    ass.write_comment(
                        comment,
                        row,
                        width,
                        height,
                        bottom_reserved,
                        fontsize,
                        duration_marquee,
                        duration_still,
                        styleid,
                    )
        elif comment.pos == CommentPosition.Special:
            ass.write_comment_special(comment, width, height, styleid)
        else:
            logging.warning(f"Invalid comment: {comment.comment!r}")
    if progress_callback:
        progress_callback(len(comments), len(comments))
    return ass.to_string()


def convert_type2(row, height, bottom_reserved):
    return height - bottom_reserved - row


class safe_list(list):
    def get(self, index, default=None):
        def is_empty(value):
            return value is None or value == ""

        try:
            return self[index] if not is_empty(self[index]) else default
        except IndexError:
            return default


def wrap_default(value: T | None, default: T) -> T:
    return default if value is None else value


def Danmaku2ASS(
    inputs: list[str | bytes] | str | bytes,
    stage_width: int,
    stage_height: int,
    input_format: str = "xml",
    reserve_blank: int = 0,
    font_face: str = "sans-serif",
    font_size: float = 25.0,
    text_opacity: float = 1.0,
    duration_marquee: float = 5.0,
    duration_still: float = 5.0,
    comment_filter: str | None = None,
    is_reduce_comments: bool = False,
    progress_callback: Callable[..., None] | None = None,
) -> str:
    comment_filters: list[str] = [comment_filter] if comment_filter is not None else []
    filters_regex = []
    for comment_filter in comment_filters:
        try:
            if comment_filter:
                filters_regex.append(re.compile(comment_filter))
        except:  # noqa: E722
            raise ValueError(f"Invalid regular expression: {comment_filter}") from None

    comments: list[Comment] = []
    if not isinstance(inputs, list):
        inputs = [inputs]
    for input in inputs:
        if input_format == "xml":
            comments.extend(read_comments_bilibili_xml(input, font_size))
        else:
            if isinstance(input, str):
                logging.warning("Protobuf can only be read from bytes")
            comments.extend(read_comments_bilibili_protobuf(input, font_size))
    comments.sort(
        key=lambda comment: (
            comment.timeline,
            comment.timestamp,
            comment.no,
            comment.comment,
            comment.pos,
            comment.color,
            comment.size,
            comment.height,
            comment.width,
        )
    )
    return process_comments(
        comments,
        stage_width,
        stage_height,
        reserve_blank,
        font_face,
        font_size,
        text_opacity,
        duration_marquee,
        duration_still,
        filters_regex,
        is_reduce_comments,
        progress_callback,
    )
