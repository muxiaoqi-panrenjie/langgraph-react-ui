import time
from functools import wraps
from typing import Annotated, TypedDict, Any, List

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage

from core.config import model, message_content_to_text, checkpointer
from pydantic import BaseModel, Field

# ------------------------------------------------------------
# 1. 状态定义
# ------------------------------------------------------------
class ResumeScreenerState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    jd: str                      # 岗位 JD 文本
    resume: str                  # 候选人原始简历文本
    evaluation: dict             # 结构化评分及优势劣势数据
    action: str                  # AI 推荐动作: "approve_interview", "reject", "needs_review"
    hr_decision: str             # HR 决策: "approve", "reject"

# ------------------------------------------------------------
# 2. Pydantic 结构化输出模式
# ------------------------------------------------------------
class InputClassification(BaseModel):
    input_type: str = Field(
        description="'jd' 如果是输入/描述岗位需求或JD; 'resume' 如果是描述候选人简历/背景/工作经历/项目经验; 'other' 如果是日常问候、一般疑问或其他说明。"
    )

class ResumeEvaluation(BaseModel):
    candidate_name: str = Field(description="候选人真实姓名。如果简历中未提及，请写'未知'")
    hard_skills_score: int = Field(description="核心硬技能匹配度评分 (0-100)")
    project_exp_score: int = Field(description="项目工作经验匹配度评分 (0-100)")
    stability_score: int = Field(description="求职稳定性与软实力评估评分 (0-100)")
    total_score: int = Field(description="综合匹配度总打分 (0-100)")
    advantages: List[str] = Field(description="候选人核心匹配优势（列表）")
    disadvantages: List[str] = Field(description="候选人核心短板与劣势（列表）")
    interview_questions: List[str] = Field(description="建议面试官对其进行提问的 3-4 个针对性问题（列表）")

# ------------------------------------------------------------
# 3. 节点函数
# ------------------------------------------------------------
def log_node_time(func):
    @wraps(func)
    def wrapper(state: ResumeScreenerState):
        started_at = time.perf_counter()
        print(f"[ResumeScreener][Node:{func.__name__}] start")
        try:
            result = func(state)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            print(f"[ResumeScreener][Node:{func.__name__}] error after {elapsed_ms:.0f}ms: {e}")
            raise
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        print(f"[ResumeScreener][Node:{func.__name__}] end elapsed={elapsed_ms:.0f}ms")
        return result
    return wrapper

@log_node_time
def classify_and_store(state: ResumeScreenerState):
    """分析用户输入类型（JD、简历、其他聊天）并存储状态。"""
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_message = message_content_to_text(messages[-1].content).strip()
    jd = state.get("jd", "")

    # 使用大模型结构化意图分类
    prompt = f"""分析以下用户输入，判断它是属于“招聘需求岗位JD”、“个人简历”还是“通用对话或咨询”。

用户输入：
\"\"\"
{last_message}
\"\"\"
"""
    try:
        classification = model.with_structured_output(InputClassification).invoke(prompt)
        input_type = classification.input_type
    except Exception as e:
        print(f"[ResumeScreener] Classification LLM failed: {e}")
        # 降级关键词匹配规则
        lower_msg = last_message.lower()
        if any(kw in lower_msg for kw in ["岗位需求", "招聘需求", "职位描述", "jd", "job description", "职责", "要求", "任职资格"]):
            input_type = "jd"
        elif any(kw in lower_msg for kw in ["简历", "工作经历", "毕业学校", "个人背景", "项目经历", "工作年限", "求职者", "姓名:"]):
            input_type = "resume"
        else:
            input_type = "other"

    print(f"[ResumeScreener] Classified input_type={input_type}")

    if input_type == "jd":
        msg = AIMessage(content="✅ 已成功录入岗位招聘需求(JD)。现在您可以发送候选人的【个人简历】来进行匹配度筛查。")
        return {"jd": last_message, "messages": [msg]}
    elif input_type == "resume":
        if not jd:
            msg = AIMessage(content="⚠️ 检测到您发送了候选人简历，但当前会话中尚未录入【岗位需求 JD】。请先发送岗位要求，以作为简历筛选的对照标准。")
            return {"messages": [msg]}
        else:
            # 标记已收到简历
            return {"resume": last_message}
    else:
        # 通用聊天或说明
        prompt_instruction = """您好！我是简历筛选 AI 助手。

我的工作流程如下：
1. 请发送**岗位需求或 JD 描述**（例如：“招聘React前端，3年经验...”），系统将自动录入需求。
2. 随后发送**候选人简历内容**，我将针对该岗位生成多维度匹配度分析报表。
3. 如果匹配得分在 60-80 分的灰度区间，会自动触发 HR 审批（进入人工介入状态），让您手工决策是否发起面试。

请现在提供您的岗位需求描述："""
        msg = AIMessage(content=prompt_instruction)
        return {"messages": [msg]}

@log_node_time
def evaluate_match(state: ResumeScreenerState):
    """核心评估节点：调用大模型比对简历与 JD 生成多维度评分表。"""
    jd = state.get("jd", "")
    resume = state.get("resume", "")
    if not jd or not resume:
        return {}

    prompt = f"""您是一位资深的招聘HR与架构师技术面试官。请仔细比对以下【岗位招聘需求(JD)】与【候选人简历内容】，生成一份详尽的多维度评估结果。

【岗位招聘需求(JD)】
{jd}

【候选人简历内容】
{resume}
"""
    try:
        evaluation_result = model.with_structured_output(ResumeEvaluation).invoke(prompt)
        total_score = evaluation_result.total_score

        # 根据综合匹配总分分配路由动作
        if total_score >= 80:
            action = "approve_interview"
        elif total_score < 60:
            action = "reject"
        else:
            action = "needs_review"

        return {
            "evaluation": evaluation_result.dict(),
            "action": action
        }
    except Exception as e:
        print(f"[ResumeScreener] Evaluation match LLM failed: {e}")
        # 降级默认对象
        fallback = {
            "candidate_name": "未知",
            "hard_skills_score": 65,
            "project_exp_score": 65,
            "stability_score": 65,
            "total_score": 65,
            "advantages": ["评估超时，请阅读简历原文判断"],
            "disadvantages": ["未成功调用 LLM"],
            "interview_questions": ["请了解求职者的项目经历细节"]
        }
        return {
            "evaluation": fallback,
            "action": "needs_review"
        }

@log_node_time
def human_review(state: ResumeScreenerState):
    """人工审批节点：匹配分在 60-80 之间时触发 interrupt()。"""
    eval_data = state.get("evaluation", {})
    candidate_name = eval_data.get("candidate_name", "未知")
    total_score = eval_data.get("total_score", 70)

    # 触发 LangGraph 中             断
    response = interrupt({
        "type": "tool_approval",
        "tool_name": "resume_screening",
        "args": {
            "candidate_name": candidate_name,
            "total_score": f"{total_score} 分",
            "reason": f"该候选人评分得 {total_score} 分，介于临界灰度区间(60-80分)，需HR决策是否给予面试机会。"
        },
        "message": f"候选人 '{candidate_name}'  综合得分为 {total_score} 分。是否发起面试邀约？",
        "severity": "medium"
    })

    decision = "approve"
    if isinstance(response, dict):
        decision = response.get("action", "approve")
    else:
        decision = str(response)

    return {"hr_decision": decision}

@log_node_time
def generate_final_report(state: ResumeScreenerState):
    """生成最终 Markdown 匹配评估报告节点。"""
    eval_data = state.get("evaluation", {})
    action = state.get("action", "")
    hr_decision = state.get("hr_decision", "")

    candidate_name = eval_data.get("candidate_name", "未知")
    hard_skills = eval_data.get("hard_skills_score", 0)
    project_exp = eval_data.get("project_exp_score", 0)
    stability = eval_data.get("stability_score", 0)
    total_score = eval_data.get("total_score", 0)

    advantages_md = "\n".join([f"- {adv}" for adv in eval_data.get("advantages", [])])
    disadvantages_md = "\n".join([f"- {dis}" for dis in eval_data.get("disadvantages", [])])
    questions_md = "\n".join([f"- {q}" for q in eval_data.get("interview_questions", [])])

    # 渲染最终匹配决定标识
    if action == "approve_interview":
        decision_display = "🟩 **推荐面试** (AI 自动推荐)"
    elif action == "reject":
        decision_display = "🟥 **淘汰** (AI 自动淘汰)"
    elif hr_decision == "approve":
        decision_display = "🟪 **推荐面试** (HR 人工批准)"
    elif hr_decision == "reject":
        decision_display = "🟫 **淘汰** (HR 人工拒绝)"
    else:
        decision_display = "⚠️ **未定**"

    report_markdown = f"""### 📄 候选人智能匹配报告

* **候选人姓名**：{candidate_name}
* **最终筛选决策**：{decision_display}

#### 📊 维度评估评分
* **核心硬技能匹配**：`{hard_skills} / 100`
* **项目经验匹配**：`{project_exp} / 100`
* **求职稳定性评估**：`{stability} / 100`
* **🌟 综合匹配总得分**：`{total_score} / 100`

---

#### 🌟 核心优势亮点
{advantages_md}

#### ⚠️ 潜在短板与匹配劣势
{disadvantages_md}

#### 💬 针对性面试提问建议
{questions_md}

---
*💡 系统状态已重置，您可以直接继续发送下一份候选人简历进行匹配筛选。*
"""
    # 清除当前评估的简历及临时状态，允许在该 Thread 针对同一个 JD 连续筛查不同的简历
    return {
        "messages": [AIMessage(content=report_markdown)],
        "resume": "",
        "evaluation": {},
        "action": "",
        "hr_decision": ""
    }

# ------------------------------------------------------------
# 4. 路由逻辑
# ------------------------------------------------------------
def route_after_classify(state: ResumeScreenerState):
    jd = state.get("jd", "")
    resume = state.get("resume", "")
    if jd and resume:
        return "evaluate_match"
    return END

def route_after_eval(state: ResumeScreenerState):
    action = state.get("action", "")
    if action == "needs_review":
        return "human_review"
    return "generate_final_report"

# ------------------------------------------------------------
# 5. 构建图
# ------------------------------------------------------------
resume_screener_builder = StateGraph(ResumeScreenerState, input_schema=ResumeScreenerState)

resume_screener_builder.add_node("classify_and_store", classify_and_store)
resume_screener_builder.add_node("evaluate_match", evaluate_match)
resume_screener_builder.add_node("human_review", human_review)
resume_screener_builder.add_node("generate_final_report", generate_final_report)

resume_screener_builder.add_edge(START, "classify_and_store")
resume_screener_builder.add_conditional_edges(
    "classify_and_store",
    route_after_classify,
    {
        "evaluate_match": "evaluate_match",
        END: END
    }
)
resume_screener_builder.add_conditional_edges(
    "evaluate_match",
    route_after_eval,
    {
        "human_review": "human_review",
        "generate_final_report": "generate_final_report"
    }
)
resume_screener_builder.add_edge("human_review", "generate_final_report")
resume_screener_builder.add_edge("generate_final_report", END)

resume_screener_graph = resume_screener_builder.compile(
    checkpointer=checkpointer,
    name="resume_screener_graph"
)
