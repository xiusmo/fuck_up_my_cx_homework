from typing import List, Optional, Dict
from pydantic import BaseModel
from browser_use import ActionResult, Browser, Controller
import logging
import json

logger = logging.getLogger("exam_helper")
logger.setLevel(logging.INFO)

class ExamHelper:
    def __init__(self, controller: Controller):
        self.controller = controller
        self.answered_questions = set()
        self.question_answers = {}
        self.index_to_qid = {}
        self._register_all_actions()

    def _register_all_actions(self):
        self._register_fill_blank_actions()
        self._register_choice_actions()
        self._register_multiplechoice_actions()
        self._register_judge_actions()
        self._register_status_actions()

    def _register_fill_blank_actions(self):
        class FillBlankParams(BaseModel):
            qid: str
            answer: List[str]
            iframe_id: Optional[str] = None

        helper = self

        @self.controller.action("填写填空题答案", param_model=FillBlankParams)
        async def fill_blank_action(params: FillBlankParams, browser: Browser):
            page = await browser.get_current_page()
            return await helper.fill_blank_answer(params, page)

    def _register_choice_actions(self):
        class SingleChoiceParams(BaseModel):
            qid: str
            choice: str

        helper = self

        @self.controller.action("选择单选题答案", param_model=SingleChoiceParams)
        async def single_choice_action(params: SingleChoiceParams, browser: Browser):
            page = await browser.get_current_page()
            return await helper.select_single_choice(params.qid, params.choice, page)

    def _register_multiplechoice_actions(self):
        class MultipleChoiceParams(BaseModel):
            qid: str
            answer: List[str]

        helper = self

        @self.controller.action("选择多选题选项", param_model=MultipleChoiceParams)
        async def multiple_choice_action(params: MultipleChoiceParams, browser: Browser):
            page = await browser.get_current_page()
            return await helper.select_multiple_choice(params.qid, params.answer, page)

    def _register_judge_actions(self):
        class JudgeQuestionParams(BaseModel):
            qid: str
            answer: bool

        helper = self

        @self.controller.action("回答判断题", param_model=JudgeQuestionParams)
        async def judge_action(params: JudgeQuestionParams, browser: Browser):
            page = await browser.get_current_page()
            return await helper.answer_judge_question(params.qid, params.answer, page)

    def _register_status_actions(self):
        helper = self

        @self.controller.action("获取所有题目状态")
        async def get_all_status_action(browser: Browser):
            page = await browser.get_current_page()
            return await helper.get_all_questions_status(page)

        class QuestionStatusParams(BaseModel):
            qid: str

        @self.controller.action("获取题目状态", param_model=QuestionStatusParams)
        async def get_status_action(params: QuestionStatusParams, browser: Browser):
            page = await browser.get_current_page()
            return await helper.get_question_status(params.qid, page)

    async def get_question_status(self, qid: str, page=None):
        try:
            if qid in self.answered_questions:
                return ActionResult(
                    success=True,
                    result={
                        "answered": True,
                        "answer": self.question_answers.get(qid),
                        "source": "local_cache"
                    }
                )

            if page is None:
                page = await self._get_current_page()
                if not page:
                    return ActionResult(success=False, error="无法获取当前页面")

            script = f"""
            (() => {{
                try {{
                    const qid = "{qid}";
                    const container = document.querySelector('#question' + qid) || document.querySelector('[data="' + qid + '"]');
                    if (!container) return null;

                    const typename = container.getAttribute('typename') || '未知题型';
                    const result = {{
                        qid: qid,
                        type: typename,
                        answered: false,
                        answer: null,
                        source: null,
                        hasVisualSelection: false
                    }};

                    if (typename === '填空题') {{
                        const textareas = container.querySelectorAll('textarea[id^="answerEditor' + qid + '"]');
                        const answers = [];
                        for (const textarea of textareas) {{
                            const editorId = textarea.id;
                            const editor = window.UE?.getEditor(editorId);
                            if (editor && !editor.destroyed && editor.hasContents()) {{
                                answers.push(editor.getContentTxt().trim());
                            }}
                        }}
                        if (answers.length > 0) {{
                            result.answered = true;
                            result.answer = answers;
                            result.source = "UEditorArray";
                        }}
                    }} else {{
                        const selected = container.querySelectorAll(
                            '.check_answer, .chosen, .answerBgChoose, [aria-checked="true"]'
                        );
                        if (selected.length > 0) {{
                            const values = Array.from(selected)
                                .map(el => el.getAttribute("data") || el.querySelector("span[data]")?.getAttribute("data"))
                                .filter(Boolean);

                            if (values.length > 0) {{
                                result.answered = true;
                                result.answer = values.join(",");
                                result.source = "visual_mark";
                                result.hasVisualSelection = true;
                            }}
                        }}
                    }}

                    return result;
                }} catch (e) {{
                    console.error("get_question_status error:", e);
                    return null;
                }}
            }})()
            """

            result = await page.evaluate(script)
            if result and result.get("answered"):
                self.answered_questions.add(qid)
                self.question_answers[qid] = result["answer"]
                return ActionResult(success=True, result=result)

            return ActionResult(success=True, result=result or {
                "qid": qid,
                "type": "未知",
                "answered": False,
                "answer": None,
                "source": "not_found"
            })

        except Exception as e:
            return ActionResult(success=False, error=f"获取题目状态时出错: {str(e)}")

    async def get_all_questions_status(self, page=None):
        try:
            if page is None:
                page = await self._get_current_page()
                if not page:
                    return ActionResult(success=False, error="无法获取当前页面")

            script = """
            (() => {
                function getQuestionType(container) {
                    const typename = container.getAttribute('typename');
                    if (typename) return typename;
                    const content = container.textContent.toLowerCase();
                    if (content.includes('单选题')) return '单选题';
                    if (content.includes('多选题')) return '多选题';
                    if (content.includes('判断题')) return '判断题';
                    if (content.includes('填空题')) return '填空题';
                    return '未知题型';
                }

                function getVisualState(container) {
                    return !!container.querySelector('.check_answer, .chosen, .answerBgChoose, .check');
                }

                function getQuestionAnswer(container, type) {
                    const qid = container.getAttribute('data') || container.id;
                    if (!qid) return null;

                    if (type === '填空题') {
                        const textareas = container.querySelectorAll(`textarea[id^="answerEditor${qid}"]`);
                        const values = [];
                        for (let textarea of textareas) {
                            const editorId = textarea.id;
                            const editor = window.UE?.getEditor(editorId);
                            if (!editor || editor.destroyed || !editor.hasContents()) continue;
                            values.push(editor.getContentTxt().trim());
                        }
                        return values.length > 0 ? values : null;
                    } else if (['单选题', '判断题'].includes(type)) {
                        const options = container.querySelectorAll('.choice' + qid);
                        for (const el of options) {
                            const isSelected = el.classList.contains('check_answer') ||
                                el.classList.contains('chosen') ||
                                el.classList.contains('answerBgChoose') ||
                                el.getAttribute('aria-checked') === 'true';
                            if (isSelected) {
                                const data = el.getAttribute('data');
                                if (data) return data;
                            }
                        }
                        return null;
                    } else if (type === '多选题') {
                        const selected = container.querySelectorAll('.check_answer, .chosen, .answerBgChoose, [aria-checked="true"]');
                        if (!selected || selected.length === 0) return null;
                        const selectedOptions = Array.from(selected)
                            .map(el => el.querySelector('span[data]')?.getAttribute('data') || el.getAttribute('data'))
                            .filter(Boolean);
                        return selectedOptions.length > 0 ? selectedOptions.join(',') : null;
                    }

                    return null;
                }

                try {
                    const questions = document.querySelectorAll('.questionLi');
                    const result = [];

                    questions.forEach((q, index) => {
                        const qid = q.getAttribute('data') || q.id;
                        const displayNumber = q.querySelector('.mark_name')?.textContent.trim() || `题目 ${index + 1}`;
                        const type = getQuestionType(q);
                        const answer = getQuestionAnswer(q, type);

                        const status = {
                            index: index + 1,
                            displayNumber: displayNumber,
                            qid: qid,
                            elementId: q.id,
                            type: type,
                            answered: !!answer,
                            answer: answer,
                            hasVisualSelection: getVisualState(q)
                        };

                        result.push(status);
                    });

                    return result;
                } catch (e) {
                    console.error('获取题目状态时出错:', e);
                    return null;
                }
            })();
            """

            result = await page.evaluate(script)
            if result:
                questions = result
                self.index_to_qid = {
                    question["index"]: question["qid"]
                    for question in questions
                    if "index" in question and "qid" in question
                }
                for question in questions:
                    if question["answered"]:
                        self.answered_questions.add(question["qid"])
                        self.question_answers[question["qid"]] = question["answer"]
                result_data = {"total": len(questions), "questions": questions}
                return ActionResult(success=True, result=result_data, extracted_content=json.dumps(result_data, ensure_ascii=False), include_in_memory=True)

            return ActionResult(success=False, error="无法获取题目状态")

        except Exception as e:
            return ActionResult(success=False, error=f"获取题目状态时出错: {str(e)}")

    def _resolve_qid(self, identifier: str | int) -> Optional[str]:
        if isinstance(identifier, int) and identifier > 1000:
            return str(identifier)
        if isinstance(identifier, str) and identifier.isdigit() and int(identifier) > 1000:
            return identifier
        if isinstance(identifier, int):
            return self.index_to_qid.get(identifier)
        if isinstance(identifier, str) and identifier.isdigit():
            return self.index_to_qid.get(int(identifier))
        return identifier

    async def fill_blank_answer(self, params, page=None):
        """
        使用 UEditor 设置填空题答案
        """
        try:
            logger.info(f"填写填空题 {params.qid}，答案: {params.answer}")

            if page is None:
                page = await self._get_current_page()
                if not page:
                    return ActionResult(success=False, error="无法获取当前页面")

            resolved_qid = self._resolve_qid(params.qid)
            if not resolved_qid:
                return ActionResult(success=False, error=f"无法识别题目编号：{params.qid}")
            params.qid = resolved_qid

            textarea_prefix = f"answerEditor{params.qid}"
            # 查找所有填空
            blank_count = await page.evaluate(f'''
                () => {{
                    return Array.from(document.querySelectorAll('textarea[id^="{textarea_prefix}"]'))
                        .filter(el => el.id.match(/^{textarea_prefix}\\d+$/)).length;
                }}
            ''')
            if blank_count == 0:
                return ActionResult(success=False, error=f"未找到匹配的填空字段: {textarea_prefix}*")

            if len(params.answer) != blank_count:
                return ActionResult(success=False, error=f"填空数不匹配：页面需要 {blank_count} 个答案，但提供了 {len(params.answer)} 个")

            # 遍历所有空设置答案
            for i, answer in enumerate(params.answer):
                escaped = answer.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
                success = await page.evaluate(f'''
                    () => new Promise(resolve => {{
                        const editor = window.UE?.getEditor("{textarea_prefix}{i+1}");
                        if (!editor || editor.destroyed) return resolve(false);
                        editor.ready(() => {{
                            try {{
                                editor.setContent("{escaped}");
                                resolve(true);
                            }} catch (e) {{
                                console.error("写入失败:", e);
                                resolve(false);
                            }}
                        }});
                    }})
                ''')
                if not success:
                    return ActionResult(success=False, error=f"第 {i+1} 空设置失败")

            return ActionResult(success=True, result=f"成功填写 {blank_count} 个填空")

        except Exception as e:
            logger.exception("填写填空题失败")
            return ActionResult(success=False, error=f"填写填空题时出错: {str(e)}")

    async def select_single_choice(self, qid: str, choice: str, page):
        """
        设置单选题的选项为选中状态（不使用模拟点击，而是直接设置属性和样式）
        """
        try:
            resolved_qid = self._resolve_qid(qid)
            if not resolved_qid:
                return ActionResult(success=False, error=f"无法识别题目编号：{qid}")
            qid = resolved_qid
            logger.info(f"选择单选题 {qid}，选项: {choice}")

            script = f'''
            (() => {{
                const qid = "{qid}";
                const choice = "{choice}";
                const container = document.querySelector(`#question${{qid}}`) || document.querySelector(`[data="${{qid}}"]`);
                if (!container) return "未找到题目容器";

                const target = container.querySelector(`.choice${{qid}}[data="${{choice}}"]`);
                if (!target) return "未找到选项";

                const wrapper = target.closest('.answerBg');
                if (!wrapper) return "未找到点击容器";
                
                // 防止重复点击导致取消选中
                if (wrapper.getAttribute("aria-checked") === "true") return true;
                
                wrapper.click();
                return true;
            }})()
            '''

            result = await page.evaluate(script)
            if result is True:
                self.answered_questions.add(qid)
                self.question_answers[qid] = choice
                return ActionResult(success=True, result=f"单选题{qid}设置成功")
            else:
                return ActionResult(success=False, error=f"执行脚本失败: {result}")

        except Exception as e:
            logger.exception("单选题设置失败")
            return ActionResult(success=False, error=f"单选题设置时出错: {str(e)}")

    async def select_multiple_choice(self, qid: str, choices: List[str], page):
        """
        设置多选题的选项为选中状态（不使用模拟点击，而是直接设置属性和样式）
        """
        try:
            resolved_qid = self._resolve_qid(qid)
            if not resolved_qid:
                return ActionResult(success=False, error=f"无法识别题目编号：{qid}")
            qid = resolved_qid
            logger.info(f"选择多选题 {qid}，选项: {choices}")

            # Escape all choice values for safety
            choices_set = set(choices)
            choice_js_array = "[" + ",".join(f'"{c}"' for c in choices_set) + "]"

            script = f'''
            (() => {{
                const qid = "{qid}";
                const choices = new Set({choice_js_array});
                const container = document.querySelector(`#question${{qid}}`) || document.querySelector(`[data="${{qid}}"]`);
                if (!container) return "未找到题目容器";
 
                const allOptions = container.querySelectorAll(`.choice${{qid}}`);
                if (!allOptions || allOptions.length === 0) return "未找到选项";
 
                allOptions.forEach(el => {{
                    const data = el.getAttribute("data");
                    if (!choices.has(data)) return;
                    const wrapper = el.closest('.answerBg');
                    if (!wrapper) return;
                    if (wrapper.getAttribute("aria-checked") === "true") return true;
                    wrapper.click();
                }});
 
                return true;
            }})()
            '''

            result = await page.evaluate(script)
            if result is True:
                self.answered_questions.add(qid)
                self.question_answers[qid] = ",".join(choices)
                return ActionResult(success=True, result=f"多选题{qid}设置成功")
            else:
                return ActionResult(success=False, error=f"执行脚本失败: {result}")

        except Exception as e:
            logger.exception("多选题设置失败")
            return ActionResult(success=False, error=f"多选题设置时出错: {str(e)}")

    async def answer_judge_question(self, qid: str, answer: bool, page):
        """
        设置判断题选项为选中状态（直接设置样式和属性）
        """
        try:
            resolved_qid = self._resolve_qid(qid)
            if not resolved_qid:
                return ActionResult(success=False, error=f"无法识别题目编号：{qid}")
            qid = resolved_qid
            logger.info(f"回答判断题 {qid}，答案: {'对' if answer else '错'}")

            # 判断题中通常"对"为 true → data="true"，错为 false → data="false"
            choice_data = "true" if answer else "false"

            script = f'''
            (() => {{
                const qid = "{qid}";
                const container = document.querySelector(`#question${{qid}}`) || document.querySelector(`[data="${{qid}}"]`);
                if (!container) return "未找到题目容器";
 
                const allOptions = container.querySelectorAll(`.choice${{qid}}`);
                if (!allOptions || allOptions.length === 0) return "未找到判断选项";
 
                for (const el of allOptions) {{
                    if (el.getAttribute("data") !== "{choice_data}") continue;
                    const wrapper = el.closest('.answerBg');
                    if (!wrapper) return "未找到点击容器";
                    if (wrapper.getAttribute("aria-checked") === "true") return true;
                    wrapper.click();
                    break;
                }}
 
                return true;
            }})()
            '''

            result = await page.evaluate(script)
            if result is True:
                self.answered_questions.add(qid)
                self.question_answers[qid] = choice_data
                return ActionResult(success=True, result=f"判断题{qid}设置成功")
            else:
                return ActionResult(success=False, error=f"执行脚本失败: {result}")

        except Exception as e:
            logger.exception("判断题设置失败")
            return ActionResult(success=False, error=f"判断题设置时出错: {str(e)}")