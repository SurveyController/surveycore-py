import json

import httpx
import pytest

from surveycore import RunConfig, SubmissionRequest, SurveyClient


@pytest.mark.asyncio
async def test_tencent_parse_and_submit_all_observed_question_types() -> None:
    options = [{"id": "o1", "text": "甲"}, {"id": "o2", "text": "乙"}]
    rows = [{"id": "r1", "text": "行一"}, {"id": "r2", "text": "行二"}]
    raw_questions = [
        {"type": "radio", "options": options},
        {"type": "checkbox", "options": options, "min_length": 1},
        {"type": "select", "options": options},
        {"type": "text"},
        {"type": "matrix_star", "sub_titles": rows, "star_begin_num": 1, "star_num": 5},
        {"type": "matrix_radio", "sub_titles": rows, "options": options},
        {"type": "nps", "star_begin_num": 0, "star_num": 11},
        {"type": "textarea"},
        {
            "type": "chained_selects",
            "levels": ["一级", "二级"],
            "groups": [["l1", "甲", [["l11", "一"]]], ["l2", "乙", [["l21", "二"]]]],
        },
    ]
    questions = [
        {
            **question, "id": f"q-{i}", "title": f"题目 {i}", "required": True,
            "page_id": "p-1" if i <= 6 else "p-2", "page": 1024 if i <= 6 else 2048,
        }
        for i, question in enumerate(raw_questions, 1)
    ]
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.rsplit("/", 1)[-1]
        calls.append(endpoint)
        match endpoint:
            case "session":
                data = {"answer_session_id": "sess", "answer_session": {"last_answer_id": 0}}
                if "answers" in calls:
                    assert request.headers["x-answer-session"] == "sess"
                    data["answer_session"] = {"last_answer_id": 1}
            case "meta":
                data = {"title": "题型回归"}
            case "questions":
                data = {"questions": questions}
            case "answers":
                assert request.method == "POST"
                assert request.headers["x-answer-session"] == "sess"
                pages = json.loads(request.content)["answer_survey"]["pages"]
                assert [page["id"] for page in pages] == ["p-1", "p-2"]
                assert [len(page["questions"]) for page in pages] == [6, 3]
                answers = [item for page in pages for item in page["questions"]]
                assert [(a["id"], a["type"]) for a in answers] == [(q["id"], q["type"]) for q in questions]
                for answer in answers[:3]:
                    assert answer["options"] and all(o["checked"] == 1 for o in answer["options"])
                assert answers[3]["text"] and answers[7]["text"]
                assert [group["id"] for group in answers[4]["groups"]] == ["r1", "r2"]
                assert all(group["text"] in "12345" for group in answers[4]["groups"])
                assert [group["id"] for group in answers[5]["groups"]] == ["r1", "r2"]
                assert all(len(group["options"]) == 1 for group in answers[5]["groups"])
                assert 0 <= int(answers[6]["text"]) <= 10
                assert (answers[8]["id_list"], answers[8]["text_list"]) in [
                    (["l1", "l11"], ["甲", "一"]), (["l2", "l21"], ["乙", "二"]),
                ]
                data = {"answer_hash": "accepted"}
            case _:
                raise AssertionError(endpoint)
        return httpx.Response(200, json={"code": "OK", "data": data})

    url = "https://wj.qq.com/s2/123/hash/"
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = SurveyClient(http)
        survey = await client.parse(url)
        assert all(q.required and not q.unsupported for q in survey.questions)
        assert survey.questions[-1].option_texts == ("甲 / 一", "乙 / 二")
        result = await client.submit(SubmissionRequest(RunConfig(url, reliability_mode=False), survey))

    assert result.success, result.error
    assert calls == ["session", "meta", "questions", "session", "questions", "answers", "session"]
