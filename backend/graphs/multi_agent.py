"""
多智能体客服系统（Notebook 201 迁移）。
包含：音乐目录子 Agent、发票信息子 Agent、监督 Agent、身份验证、长期记忆。
"""

import ast
import json
from typing import Annotated, TypedDict, Any, List

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.base import BaseStore
from langgraph.prebuilt import ToolNode, create_react_agent
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain.tools import ToolRuntime

from core.config import db, model, in_memory_store, message_content_to_text


# ============================================================
# 状态定义
# ============================================================
class MultiAgentInputState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


class MultiAgentState(MultiAgentInputState):
    customer_id: Any
    loaded_memory: str
    remaining_steps: int


# ============================================================
# 音乐目录查询工具
# ============================================================
@tool
def get_albums_by_artist(artist: str) -> str:
    """获取某位艺术家的专辑。"""
    return db.run(
        f"SELECT Album.Title, Artist.Name FROM Album JOIN Artist ON Album.ArtistId = Artist.ArtistId WHERE Artist.Name LIKE '%{artist}%';",
        include_columns=True
    )


@tool
def get_tracks_by_artist(artist: str) -> str:
    """获取某位艺术家（或相似艺术家）的歌曲。"""
    return db.run(
        f"SELECT Track.Name as SongName, Artist.Name as ArtistName FROM Album LEFT JOIN Artist ON Album.ArtistId = Artist.ArtistId LEFT JOIN Track ON Track.AlbumId = Album.AlbumId WHERE Artist.Name LIKE '%{artist}%';",
        include_columns=True
    )


@tool
def get_songs_by_genre(genre: str) -> Any:
    """从数据库中获取匹配特定流派的歌曲。"""
    genre_id_query = f"SELECT GenreId FROM Genre WHERE Name LIKE '%{genre}%'"
    genre_ids = db.run(genre_id_query)
    if not genre_ids:
        return f"No songs found for the genre: {genre}"
    try:
        genre_ids = ast.literal_eval(genre_ids)
    except (ValueError, SyntaxError):
        return f"No songs found for the genre: {genre}"

    genre_id_list = ", ".join(str(gid[0]) for gid in genre_ids)

    songs_query = f"""
        SELECT MIN(Track.Name) as SongName, Artist.Name as ArtistName
        FROM Track
        LEFT JOIN Album ON Track.AlbumId = Album.AlbumId
        LEFT JOIN Artist ON Album.ArtistId = Artist.ArtistId
        WHERE Track.GenreId IN ({genre_id_list})
        GROUP BY Artist.Name
        LIMIT 8;
    """
    songs = db.run(songs_query, include_columns=True)
    if not songs:
        return f"No songs found for the genre: {genre}"
    try:
        formatted_songs = ast.literal_eval(songs)
        return [
            {"Song": song["SongName"], "Artist": song["ArtistName"]}
            for song in formatted_songs
        ]
    except (ValueError, SyntaxError):
        return songs


@tool
def check_for_songs(song_title: str) -> str:
    """根据歌曲名称检查歌曲是否存在。"""
    return db.run(
        f"SELECT * FROM Track WHERE Name LIKE '%{song_title}%';",
        include_columns=True
    )


music_tools = [get_albums_by_artist, get_tracks_by_artist, get_songs_by_genre, check_for_songs]


# ============================================================
# 发票信息查询工具（从 ToolRuntime.state 读取 customer_id）
# ============================================================
@tool
def get_invoices_by_customer_sorted_by_date(runtime: ToolRuntime) -> str:
    """
    Look up all invoices for a customer using their ID, the customer ID is in a state variable, so you will not see it in the message history.
    The invoices are sorted in descending order by invoice date.
    """
    customer_id = runtime.state.get("customer_id")
    if not customer_id:
        return "Error: Customer ID is not set. Please verify your account first."
    return db.run(f"SELECT * FROM Invoice WHERE CustomerId = {customer_id} ORDER BY InvoiceDate DESC;")


@tool
def get_invoices_sorted_by_unit_price(runtime: ToolRuntime) -> str:
    """
    Use this tool when the customer wants to know the details of one of their invoices based on the unit price/cost of the invoice.
    This tool looks up all invoices for a customer, and sorts the unit price from highest to lowest.
    """
    customer_id = runtime.state.get("customer_id")
    if not customer_id:
        return "Error: Customer ID is not set. Please verify your account first."
    query = f"""
        SELECT Invoice.*, InvoiceLine.UnitPrice
        FROM Invoice
        JOIN InvoiceLine ON Invoice.InvoiceId = InvoiceLine.InvoiceId
        WHERE Invoice.CustomerId = {customer_id}
        ORDER BY InvoiceLine.UnitPrice DESC;
    """
    return db.run(query)


@tool
def get_employee_by_invoice_and_customer(runtime: ToolRuntime, invoice_id: int) -> str:
    """
    This tool will take in an invoice ID and return the employee information associated with the invoice.
    """
    customer_id = runtime.state.get("customer_id")
    if not customer_id:
        return "Error: Customer ID is not set. Please verify your account first."
    query = f"""
        SELECT Employee.FirstName, Employee.Title, Employee.Email
        FROM Employee
        JOIN Customer ON Customer.SupportRepId = Employee.EmployeeId
        JOIN Invoice ON Invoice.CustomerId = Customer.CustomerId
        WHERE Invoice.InvoiceId = {invoice_id} AND Invoice.CustomerId = {customer_id};
    """
    employee_info = db.run(query, include_columns=True)
    if not employee_info:
        return f"No employee found for invoice ID {invoice_id} and customer ID {customer_id}."
    return employee_info


invoice_tools = [
    get_invoices_by_customer_sorted_by_date,
    get_invoices_sorted_by_unit_price,
    get_employee_by_invoice_and_customer,
]


# ============================================================
# 音乐目录助理（从零构建 ReAct）
# ============================================================
def music_assistant(state: MultiAgentState):
    memory = state.get("loaded_memory") or "None"
    prompt_str = f"""
    <important_background>
    你是助理团队的成员，你的职责是专注于帮助客户在我们的数字目录中发现和了解音乐。
    如果你找不到与艺术家关联的播放列表、歌曲或专辑，这没关系。
    只需回复目录中没有与该艺术家关联的任何播放列表、歌曲或专辑。
    你还拥有关于已保存用户偏好的上下文，帮助你量身定制回复。
    重要提示：你与客户的交互是通过自动化系统完成的。你不是直接与客户交互，因此请避免闲聊或追问，纯粹专注于用必要的信息回应请求。
    </important_background>

    <core_responsibilities>
    - 搜索并提供关于歌曲、专辑、艺术家和播放列表的准确信息
    - 根据客户兴趣提供相关的推荐
    - 处理与音乐相关的查询，并注重细节
    - 帮助客户发现他们可能喜欢的新音乐
    - 只有在有与音乐目录相关的问题时，你才会被路由；忽略其他问题。
    </core_responsibilities>

    <guidelines>
    1. 在得出某物不可用的结论之前，请务必进行彻底的搜索
    2. 如果找不到精确匹配，请尝试：
       - 检查替代拼写
       - 寻找相似的艺术家名字
       - 通过部分匹配进行搜索
       - 检查不同的版本/混音版
    3. 在提供歌曲列表时：
       - 每首歌曲都包含艺术家名字
       - 相关时提及专辑
       - 注意它是否是任何播放列表的一部分
       - 指示是否存在多个版本
    </guidelines>

    下方提供了额外的上下文：

    先前保存的用户偏好： {memory}
    """
    try:
        llm_with_music_tools = model.bind_tools(music_tools)
        response = llm_with_music_tools.invoke([SystemMessage(prompt_str)] + state["messages"])
        return {"messages": [response]}
    except Exception as e:
        print(f"[MultiAgent] Music assistant error: {e}")
        err_msg = AIMessage(content="【音乐目录助理】由于网络异常或服务限额，暂时无法为您检索音乐库，请稍后再试。")
        return {"messages": [err_msg]}


def should_continue_music(state: MultiAgentState):
    last_message = state["messages"][-1]
    if not last_message.tool_calls:
        return "end"
    return "continue"


music_tool_node = ToolNode(music_tools)

music_workflow = StateGraph(MultiAgentState)
music_workflow.add_node("music_assistant", music_assistant)
music_workflow.add_node("music_tool_node", music_tool_node)
music_workflow.add_edge(START, "music_assistant")
music_workflow.add_conditional_edges(
    "music_assistant",
    should_continue_music,
    {"continue": "music_tool_node", "end": END}
)
music_workflow.add_edge("music_tool_node", "music_assistant")

music_catalog_subagent = music_workflow.compile(
    checkpointer=MemorySaver(),
    store=in_memory_store,
    name="music_catalog_subagent"
)


# ============================================================
# 发票信息助理（使用 prebuilt create_react_agent）
# ============================================================
invoice_information_subagent = create_react_agent(
    model=model,
    tools=invoice_tools,
    state_schema=MultiAgentState,
    checkpointer=MemorySaver(),
    store=in_memory_store,
    prompt="""
    <important_background>
    你是助理团队中的一个子 Agent。你专门负责检索和处理发票信息。
    发票包含诸如歌曲购买和账单历史之类的信息。仅回答在某种程度上与账单、发票或购买相关的问题。
    如果你无法检索发票信息，请回复你无法检索该信息。
    重要提示：你与客户的交互是通过自动化系统完成的。你不是直接与客户交互，因此请避免闲聊或追问，纯粹专注于用必要的信息回应请求。
    </important_background>

    <tools>
    你有权访问三个工具。这些工具使你能够从数据库中检索和处理发票信息。以下是这些工具：
    - get_invoices_by_customer_sorted_by_date：此工具检索客户的所有发票，按发票日期排序。
    - get_invoices_sorted_by_unit_price：此工具检索客户的所有发票，按单价排序。
    - get_employee_by_invoice_and_customer：此工具检索与发票和客户关联的员工信息。
    </tools>

   <core_responsibilities>
    - 从数据库检索和处理发票信息
    - 当客户要求时，提供关于发票的详细信息，包括客户详情、发票日期、总金额、与发票关联的员工等。
    - 在你的回复中始终保持专业、友好和耐心的态度。
    </core_responsibilities>
    """,
    name="invoice_information_subagent"
)


# ============================================================
# 监督智能体工具包装器
# ============================================================
@tool("invoice_information_subagent")
def call_invoice_information_subagent(runtime: ToolRuntime, query: str) -> str:
    """An agent that can assist with all invoice-related queries. It can retrieve information about a customer's past purchases or invoices."""
    try:
        result = invoice_information_subagent.invoke({
            "messages": [HumanMessage(content=query)],
            "customer_id": runtime.state.get("customer_id")
        })
        return message_content_to_text(result["messages"][-1].content)
    except Exception as e:
        print(f"[MultiAgent] call_invoice_information_subagent error: {e}")
        return "【系统提示】发票子智能体服务繁忙，暂时无法查询发票信息，请稍后再试。"


@tool("music_catalog_subagent")
def call_music_catalog_subagent(query: str) -> str:
    """An agent that can assist with all music-related queries. This agent has access to user's saved music preferences. It can also retrieve information about the digital music store's music catalog (albums, tracks, songs, etc.)."""
    try:
        result = music_catalog_subagent.invoke({
            "messages": [HumanMessage(content=query)]
        })
        return message_content_to_text(result["messages"][-1].content)
    except Exception as e:
        print(f"[MultiAgent] call_music_catalog_subagent error: {e}")
        return "【系统提示】音乐子智能体服务繁忙，暂时无法查询音乐目录，请稍后再试。"


# ============================================================
# 监督智能体（使用 prebuilt create_react_agent）
# ============================================================
supervisor_agent = create_react_agent(
    model=model,
    tools=[call_invoice_information_subagent, call_music_catalog_subagent],
    state_schema=MultiAgentState,
    checkpointer=MemorySaver(),
    store=in_memory_store,
    prompt="""
    <background>
    你是数字音乐商店的专家客户服务助手。你可以处理关于过去购买、歌曲或专辑可用性的音乐目录或发票相关问题。
    你致力于提供卓越的服务，确保客户的查询得到彻底的解答，并拥有一支子 Agent 团队，你可以利用他们来帮助回答客户的查询。
    你的主要职责是将任务分配给这支多 Agent 团队，以便回答客户的查询。
    </background>

    <important_instructions>
    始终通过总结各个子 Agent 响应的发现来回复客户。
    如果问题与音乐或发票无关，请礼貌地提醒客户你的工作范围。不要回答不相关的问题。
    根据消息中已采取的现有步骤，你的职责是根据用户的查询调用相应的子 Agent。
    </important_instructions>

    <tools>
    You have 2 tools available to delegate to the subagents on your team:
    1. music_catalog_subagent：调用此工具以委托给音乐子 Agent。音乐 Agent 有权访问用户保存的音乐偏好。它还可以从数据库中检索有关数字音乐商店音乐目录的信息（专辑、音轨、歌曲等）。
    2. invoice_information_subagent：调用此工具以委托给发票子 Agent。该子 Agent 能够从数据库中检索有关客户过去购买或发票的信息。
    </tools>
    """,
    name="supervisor"
)


# ============================================================
# 身份验证节点
# ============================================================
def extract_phone_number(user_input_msg: BaseMessage) -> str:
    """从用户消息中提取电话号码。"""
    prompt = """从下方的用户消息中提取电话号码。
    请仅返回提取到的电话号码字符串（例如：+55 (12) 3923-5555 或 +1 (204) 452-6452）。
    如果消息中没有包含任何电话号码，请仅返回单词 None。
    不要返回任何额外的解释或包装。"""

    try:
        response = model.invoke([
            SystemMessage(content=prompt),
            user_input_msg
        ])
        result = message_content_to_text(response.content).strip().strip("'\"")
        if "none" in result.lower() or not result:
            return ""
        return result
    except Exception as e:
        print(f"[MultiAgent] extract_phone_number error: {e}")
        return ""


def verify_info(state: MultiAgentState):
    """尝试验证客户身份：从消息中提取电话号码并查询数据库。"""
    if state.get("customer_id") is not None:
        return

    user_input = state["messages"][-1]
    identifier = extract_phone_number(user_input)

    customer_id = ""
    if identifier:
        query = f"SELECT CustomerId FROM Customer WHERE Phone = '{identifier}';"
        result = db.run(query)
        try:
            formatted_result = ast.literal_eval(result)
            if formatted_result:
                customer_id = formatted_result[0][0]
        except Exception:
            pass

    if customer_id != "":
        intent_message = AIMessage(
            content=f"感谢您提供信息！我已成功验证您的账户，客户 ID 为 {customer_id}。"
        )
        return {
            "customer_id": customer_id,
            "messages": [intent_message]
        }
    else:
        system_instructions = """
        你是音乐商店的客服代表，在客户服务的第一步尝试验证客户身份。
        在他们的账户通过验证之前，你无法为他们提供支持。
        为了验证他们的身份，请确认他们提供的电话号码。
        如果客户尚未提供电话号码，请向其索要。
        如果他们提供了电话号码但找不到其记录，请让他们重新修改。

        重要提示：在他们的身份通过验证之前，请勿询问有关其需求的任何问题，或尝试处理其需求。出于安全目的，你只能询问与其身份相关的信息，这至关重要。
        """
        try:
            response = model.invoke([SystemMessage(content=system_instructions)] + state['messages'])
            return {"messages": [response]}
        except Exception as e:
            print(f"[MultiAgent] verify_info error: {e}")
            err_msg = AIMessage(content="【系统提示】身份验证引导服务暂时不可用，请在此处直接回复并提供您的电话号码（例如：+55 (12) 3923-5555）。")
            return {"messages": [err_msg]}


def human_input(state: MultiAgentState):
    """通过参数审批形式向用户索要电话号码（契合前端 UI）。"""
    user_input = interrupt({
        "type": "verification",
        "tool_name": "verify_phone_number",
        "args": {"phone_number": ""},
        "message": "为了保障您的账户安全，我们需要验证您的身份。请在此处输入您的电话号码（例如：+55 (12) 3923-5555 或 +1 (204) 452-6452）：",
        "severity": "medium"
    })

    phone_number = ""
    if isinstance(user_input, dict):
        phone_number = user_input.get("phone_number", "")
    else:
        phone_number = str(user_input)

    return {"messages": [HumanMessage(content=f"我的电话号码是 {phone_number}")]}


def should_interrupt(state: MultiAgentState):
    if state.get("customer_id") is not None:
        return "continue"
    else:
        return "interrupt"


# ============================================================
# 长期记忆节点
# ============================================================
def format_user_memory(user_data):
    profile = user_data.get('memory')
    if not profile:
        return ""
    if hasattr(profile, 'music_preferences') and profile.music_preferences:
        return f"Music Preferences: {', '.join(profile.music_preferences)}"
    elif isinstance(profile, dict) and "music_preferences" in profile:
        return f"Music Preferences: {', '.join(profile['music_preferences'])}"
    return ""


def load_memory(state: MultiAgentState, store: BaseStore):
    user_id = str(state["customer_id"])
    namespace = ("memory_profile", user_id)
    existing_memory = store.get(namespace, "user_memory")
    formatted_memory = ""
    if existing_memory and existing_memory.value:
        formatted_memory = format_user_memory(existing_memory.value)
    return {"loaded_memory": formatted_memory}


create_memory_prompt = """你维持一位专家分析师，正在观察客户与客户服务助理之间进行的对话。该客户服务助理在一家数字音乐商店工作，并利用了一支多 Agent 团队来回答客户的请求。
你的任务是分析客户与客户服务助理之间发生的对话，并更新与该客户关联的记忆画像。
你特别关注保存客户在对话中分享的任何音乐兴趣，尤其是他们的音乐偏好到其记忆画像中。

请严格以 JSON 格式输出以下结构：
{{
  "customer_id": "{user_id}",
  "music_preferences": ["偏好1", "偏好2", ...]
}}

重要提示：请只返回合法的 JSON 格式数据，不要使用 markdown 标记（例如 ```json），不要返回任何额外的文字。

<conversation>
{conversation}
</conversation>

<existing_memory>
{memory_profile}
</existing_memory>
"""


def create_memory(state: MultiAgentState, store: BaseStore):
    user_id = str(state["customer_id"])
    namespace = ("memory_profile", user_id)
    formatted_memory = state.get("loaded_memory", "")

    conversation_text = ""
    for m in state["messages"]:
        role = "User" if m.type == "human" else "Assistant"
        conversation_text += f"{role}: {message_content_to_text(m.content)}\n"

    prompt = create_memory_prompt.format(
        user_id=user_id,
        conversation=conversation_text,
        memory_profile=formatted_memory
    )

    try:
        response = model.invoke([SystemMessage(content=prompt)])
        content = message_content_to_text(response.content).strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        data = json.loads(content)
        store.put(namespace, "user_memory", {"memory": data})
        print(f"[MEMORY] Successfully updated memory for customer {user_id}: {data}")
    except Exception as e:
        print(f"[MEMORY] Error saving memory: {e}")


def supervisor_node(state: MultiAgentState):
    try:
        return supervisor_agent.invoke(state)
    except Exception as e:
        print(f"[MultiAgent] Supervisor node error: {e}")
        err_msg = AIMessage(content="【系统提示】多智能体监督协调服务暂时不可用或达到限额，请稍后再试。")
        return {"messages": [err_msg]}


# ============================================================
# 多智能体客服总图组装
# ============================================================
multi_agent_final = StateGraph(MultiAgentState, input_schema=MultiAgentInputState)
multi_agent_final.add_node("verify_info", verify_info)
multi_agent_final.add_node("human_input", human_input)
multi_agent_final.add_node("load_memory", load_memory)
multi_agent_final.add_node("supervisor", supervisor_node)
multi_agent_final.add_node("create_memory", create_memory)

multi_agent_final.add_edge(START, "verify_info")
multi_agent_final.add_conditional_edges(
    "verify_info",
    should_interrupt,
    {"continue": "load_memory", "interrupt": "human_input"},
)
multi_agent_final.add_edge("human_input", "verify_info")
multi_agent_final.add_edge("load_memory", "supervisor")
multi_agent_final.add_edge("supervisor", "create_memory")
multi_agent_final.add_edge("create_memory", END)

multi_agent_memory = MemorySaver()
multi_agent_graph = multi_agent_final.compile(
    checkpointer=multi_agent_memory,
    store=in_memory_store,
    name="multi_agent_graph"
)
