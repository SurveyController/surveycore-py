# surveycore-py

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/release/python-3110/)
[![Async](https://img.shields.io/badge/async-httpx-2C5BB4?logo=python&logoColor=white)](https://www.python-httpx.org/async/)
[![Ruff](https://img.shields.io/badge/lint-Ruff-D7FF64?logo=ruff&logoColor=261230)](https://docs.astral.sh/ruff/)
[![ty](https://img.shields.io/badge/types-ty-D7FF64)](https://docs.astral.sh/ty/)

[![CI](https://github.com/SurveyController/surveycore-py/actions/workflows/ci.yml/badge.svg)](https://github.com/SurveyController/surveycore-py/actions/workflows/ci.yml)

纯 Python 异步问卷 HTTP 提交工具包，支持问卷星、腾讯问卷、 Credamo 见数三大平台

> [!CAUTION]
>
> **本项目仅可用于已授权问卷的学习与测试。严禁用于污染第三方问卷数据！**

## 支持平台

- [x] 问卷星
- [x] 腾讯问卷
- [x] Credamo 见数
- [ ] 其他平台（欢迎贡献）

## 使用方法

### 环境要求

- Python 3.11+ （推荐 Python 3.13.15）

### 安装

[![uv](https://img.shields.io/badge/managed%20with-uv-DE5FE9?logo=astral&logoColor=white)](https://docs.astral.sh/uv/)

```bash
uv add surveycore-py
```

或

```bash
python -m pip install surveycore-py
```

### 解析问卷

示例：

```python
import asyncio

import httpx

from surveycore import SurveyClient


async def main() -> None:
    async with httpx.AsyncClient() as http_client:
        client = SurveyClient(http_client)
        survey = await client.parse("https://www.wjx.cn/vm/example.aspx")
        print(survey.title)
        print(survey.questions)


asyncio.run(main())
```

### 运行提交任务

示例：

```python
import asyncio

import httpx

from surveycore import RunConfig, SurveyClient


async def main() -> None:
    config = RunConfig(
        url="https://www.wjx.cn/vm/example.aspx",
        target=3,
        concurrency=2,
    )

    async with httpx.AsyncClient() as http_client:
        client = SurveyClient(http_client)
        async for result in client.run(config):
            print(result.attempt, result.success, result.error)


asyncio.run(main())
```

## 公开接口

| 接口 | 作用 |
|---|---|
| `SurveyClient.parse()` | 识别平台并解析问卷结构。 |
| `SurveyClient.submit()` | 提交一次问卷尝试。 |
| `SurveyClient.run()` | 按指定次数和并发量调度提交。 |
| `RunConfig` | 定义问卷、题目策略和调度参数。 |
| `serialize_config()` / `deserialize_config()` | 在配置对象与字典之间转换。 |
| `dumps_config()` / `loads_config()` | 在配置对象与 JSON 之间转换。 |

公开异常包括：

- `UnsupportedSurveyError`：链接或平台不受支持。
- `SurveyUnavailableError`：问卷未开放、暂停或到期。
- `SurveyParseError`：问卷解析失败。
- `ConfigError`：配置无效或 schema 不兼容。
- `SubmissionError`：提交阶段错误。

## GPL-3.0 License

您有权免费使用、修改和分发该软件。

但若将程序或其衍生作品对外发布，则**必须同样以 `GPL-3.0` 许可开源，完整公开所有修改后的源代码，并保留原始版权声明与免责条款**，确保所有使用者都能平等地获得并回馈软件的自由，而不论其分发方式为何。
