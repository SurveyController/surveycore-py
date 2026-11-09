from __future__ import annotations

import re
from dataclasses import replace
from typing import Any
from urllib.parse import unquote, urljoin

from selectolax.lexbor import LexborHTMLParser

import surveycore.network.http as http_client
from surveycore.app.config import DEFAULT_HTTP_HEADERS
from surveycore.providers.answering import AnswerAction
from surveycore.providers.contracts import SurveyQuestionMeta

MULTILEVEL_DROPDOWN = "multilevel_dropdown"
_SPLIT_CHAR = "‐"
_DISPLAY_SUFFIXES = "┌┍┎┏┐┑┒┓└┕┖┗┘┙┚┛├┝┞┟┠┡┢┣┤┥┦┧┨┩┪┫┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻┼┽┾┿╀╁╂╃╄╅╆╇"


def parse_multilevel_options(html: str, *, encoded: bool = False) -> dict[str, Any]:
    soup = LexborHTMLParser(html)
    data_input = soup.css_first("input#hfLevelData")
    if data_input is None:
        raise ValueError("问卷星多级下拉未返回 hfLevelData")
    for script in soup.css("script"):
        if re.search(r"levelDataExternalUrl\s*=\s*['\"][^'\"]+", script.text()):
            raise ValueError("问卷星多级下拉暂不支持外部数据源")
    data = data_input.attributes.get("value") or ""
    if encoded:
        data = unquote(data)
    levels, _, labels = data.partition("〒")
    columns = levels.split("|")
    if not levels or not 1 <= len(columns) <= 6:
        raise ValueError("问卷星多级下拉层级数据为空或超过六级")
    paths: list[tuple[str, ...]] = []
    terminal_paths: list[tuple[str, ...]] = []
    previous_options: set[str] = set()
    for level_index, column in enumerate(columns):
        lines = [line.strip() for line in column.splitlines() if line.strip()]
        if level_index == 0:
            if not lines or any(line.startswith("---") for line in lines):
                raise ValueError("问卷星多级下拉首级选项无效")
            paths = [(line,) for line in lines]
            previous_options = set(lines)
            continue
        groups: dict[str, list[str]] = {}
        parent = ""
        for line in lines:
            if line.startswith("---"):
                parent = line[3:]
                if parent not in previous_options:
                    raise ValueError(f"问卷星多级下拉父选项不存在：{parent}")
                groups[parent] = []
            elif parent:
                groups[parent].append(line)
            else:
                raise ValueError("问卷星多级下拉子选项缺少父选项")
        next_paths: list[tuple[str, ...]] = []
        for path in paths:
            children = groups.get(path[-1])
            if not children:
                raise ValueError(f"问卷星多级下拉缺少子选项：{path[-1]}")
            if any(child.find("々") > 0 for child in children):
                terminal_paths.append(path)
            else:
                next_paths.extend((*path, child) for child in children)
        paths = next_paths
        previous_options = {child for children in groups.values() for child in children}
    paths = terminal_paths + paths
    submit_values = []
    option_texts = []
    for path in paths:
        values = [re.sub(r"╰[0-9]+╯", "", item) for item in path]
        submit_values.append(_SPLIT_CHAR.join(values))
        option_texts.append(_SPLIT_CHAR.join(
            item[:-1] if len(item) > 1 and item[-1] in _DISPLAY_SUFFIXES else item
            for item in values
        ))
    return {
        "option_texts": option_texts,
        "submit_values": submit_values,
        "level_labels": labels.split("|") if labels else [],
    }


async def load_multilevel_options(
    questions: list[dict[str, Any]], html: str, url: str
) -> None:
    multilevel_questions = [
        question for question in questions
        if question.get("provider_type") == MULTILEVEL_DROPDOWN
    ]
    if not multilevel_questions:
        return
    scripts = "\n".join(script.text() for script in LexborHTMLParser(html).css("script"))
    activity = re.search(r"\bvar\s+activityId\s*=\s*(?:DecodeId\((\d+)\)|(\d+))", scripts)
    if activity is None:
        raise ValueError("问卷星多级下拉缺少 activityId")
    if activity[1]:
        decoder = re.search(r"function\s+DecodeId\([^)]*\)\s*\{\s*return\s+\w+\s*\^\s*(\d+)", scripts)
        if decoder is None:
            raise ValueError("问卷星多级下拉无法解析 activityId")
        activity_id = int(activity[1]) ^ int(decoder[1])
    else:
        activity_id = int(activity[2])
    for question in multilevel_questions:
        metadata = question["provider_page_raw"]
        params = {"activityid": str(activity_id), "ct": "5", "pos": str(question["num"])}
        if metadata["cid"]:
            params["cid"] = metadata["cid"]
        response = await http_client.aget(
            urljoin(url, "/joinnew/setmenuselnew.aspx"),
            params=params,
            headers={**DEFAULT_HTTP_HEADERS, "Referer": url},
            timeout=12,
            proxies={},
        )
        response.raise_for_status()
        options = parse_multilevel_options(response.text, encoded=bool(metadata["cid"]))
        question["option_texts"] = options.pop("option_texts")
        question["options"] = len(question["option_texts"])
        metadata.update(options)


def multilevel_answer_action(action: AnswerAction, question: SurveyQuestionMeta) -> AnswerAction:
    if question.provider_type != MULTILEVEL_DROPDOWN:
        return action
    value = question.provider_page_raw["submit_values"][action.selected_indices[0]]
    return replace(action, kind="text", text_values=(value,))
