# Exam Helper 插件

`exam_helper.py` 是为 [browser-use](https://github.com/browser-use/browser-use) 框架开发的考试自动化插件，支持自动识别和答题多种题型（填空题、单选题、多选题、判断题），并能与 AI 代理无缝协作，极大提升在线考试自动化效率。

## 功能特性

- **自动获取所有题目状态**，支持题号与qid双向解析
- **支持四类题型自动作答**：填空题、单选题、多选题、判断题
- **自动跳过已完成题目，遍历所有未完成题**
- **与 browser-use 控制器无缝集成，支持AI代理调用**
- **详细日志输出，便于调试和追踪答题过程**

## 主要接口

- `获取所有题目状态`：返回所有题目的完成情况、类型、答案等
- `获取题目状态`：返回指定题目的状态
- `填写填空题答案`：自动填写填空题
- `选择单选题答案`：自动选择单选题
- `选择多选题选项`：自动选择多选题
- `回答判断题`：自动选择判断题

## 依赖

- [browser-use](https://github.com/browser-use/browser-use)
- pydantic

## 快速开始

1. 将 `exam_helper.py` 放入你的插件目录，并确保在 main 脚本中正确导入。
2. 在 main.py 中注册插件并启动 agent。

---

## main.py 使用示例

```python
from browser_use import Browser, Controller
from exam_helper import ExamHelper
from browser_use.agent.service import Agent
from browser_use.llm import get_default_llm  # 你可以根据实际情况选择 LLM

# 1. 初始化 Controller 和插件
controller = Controller()
exam_helper = ExamHelper(controller)

# 2. 初始化浏览器
browser = Browser()

# 3. 初始化 LLM（大模型）
llm = get_default_llm()  # 你可以替换为自己的 LLM 实例

# 4. 使用 prompt
# 在底部附上你的考试链接，如：https://mooc1.chaoxing.com/mooc-ans/mooc2/work/view?courseId=000000&classId=000000&cpi=000000&workId=000000&answerId=000000&enc=000000

# 5. 启动 Agent
async def main():
    agent = Agent(
        task=prompt,
        llm=llm,
        browser=browser,
        controller=controller,
        save_conversation_path="logs/conversation",
        use_vision=False,
    )
    await agent.run()

# 6. 运行 main
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

---

## 常见问题

- **Q: AI 代理看不到题目状态怎么办？**  
  A: 请确保 `get_all_questions_status` 返回的 `ActionResult` 设置了 `include_in_memory=True`，并将题目状态写入 `extracted_content` 字段。

- **Q: 如何自定义题目解析逻辑？**  
  A: 你可以修改 `get_all_questions_status` 和 `_resolve_qid` 方法，适配不同考试系统的页面结构。

- **Q: 考试没及格怎么办？**  
  A: 不知道。