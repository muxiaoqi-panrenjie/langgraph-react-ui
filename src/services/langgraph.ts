const BASE_URL = "http://localhost:8000";

/**
 * 助手接口定义
 */
export interface Assistant {
  assistant_id: string;
  name: string;
  graph_id: string;
  config?: any;
  metadata?: { [key: string]: any };
}

/**
 * 会话线程接口定义
 */
export interface Thread {
  thread_id: string;
  created_at: string;
  metadata?: any;
}

/**
 * 聊天消息接口定义
 */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  name?: string;
  tool_calls?: any[];
}

/**
 * 流式步骤接口定义
 */
export interface StreamStep {
  node: string;
  timestamp: number;
  status: "thinking" | "completed" | "calling_tool" | "interrupted";
  toolName?: string;
}

/**
 * 中断信息接口 —— 对应 LangGraph interrupt() 返回的数据结构
 */
export interface InterruptData {
  type: "tool_approval";
  tool_name: string;
  args: Record<string, any>;
  message: string;
  severity: "medium" | "high";
  reason?: string;
}

/**
 * 文档管理接口定义
 */
export interface RagDocument {
  source: string;
  chunk_count: number;
}

/**
 * 文档切片接口定义
 */
export interface RagChunk {
  chunk_id: string;
  text: string;
}

/**
 * 上传文档响应
 */
export interface RagUploadResponse {
  chunk_count: number;
  source: string;
}

/**
 * 审批决策
 */
export interface ApprovalDecision {
  action: "approve" | "reject" | "edit";
  [key: string]: any;
}

/**
 * LangGraph 服务类
 */
class LangGraphService {
  /** 获取助手列表 */
  async listAssistants(): Promise<Assistant[]> {
    try {
      const response = await fetch(`${BASE_URL}/api/assistants`);
      if (response.ok) {
        return await response.json();
      }
      return this.getFallbackAssistants();
    } catch (error) {
      console.warn("无法连接到后端，使用 fallback：", error);
      return this.getFallbackAssistants();
    }
  }

  private getFallbackAssistants(): Assistant[] {
    return [
      { assistant_id: "101 Weather Agent", name: "101 天气查询助手", graph_id: "regular" },
      { assistant_id: "Email Agent", name: "邮件审批助手", graph_id: "hitl" },
      { assistant_id: "Research Agent", name: "文献研究助手", graph_id: "regular" },
      { assistant_id: "Deep Agent", name: "深度推理助手", graph_id: "regular" },
      { assistant_id: "Code Agent", name: "代码开发助手", graph_id: "regular" },
      { assistant_id: "HITL Demo Agent", name: "人工审批演示", graph_id: "hitl" },
      { assistant_id: "Multi-Agent Assistant", name: "多智能体客服系统", graph_id: "hitl" },
      { assistant_id: "RAG Assistant", name: "知识库问答助手", graph_id: "rag" },
      { assistant_id: "AI Customer Service", name: "AI 客服自动回复", graph_id: "hitl" },
      { assistant_id: "Resume Screener AI", name: "简历筛选 AI", graph_id: "hitl" },
    ];
  }

  /** 创建新会话线程 */
  async createThread(): Promise<Thread> {
    try {
      const response = await fetch(`${BASE_URL}/api/threads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (response.ok) return await response.json();
      throw new Error("后端接口返回错误");
    } catch (error) {
      console.warn("无法创建 Thread，使用本地虚拟 Thread", error);
      return {
        thread_id: "local_" + Math.random().toString(36).substring(2, 15),
        created_at: new Date().toISOString(),
      };
    }
  }

  /** 获取指定线程的历史消息 */
  async getThreadMessages(threadId: string): Promise<ChatMessage[]> {
    if (threadId.startsWith("local_")) return [];
    try {
      const response = await fetch(`${BASE_URL}/api/threads/${threadId}/messages`);
      if (response.ok) return await response.json();
      return [];
    } catch (error) {
      console.error("获取会话历史失败:", error);
      return [];
    }
  }

  /**
   * 检查线程是否有待处理的中断
   */
  async checkInterrupt(threadId: string): Promise<InterruptData | null> {
    try {
      const response = await fetch(`${BASE_URL}/api/interrupt/${threadId}`);
      if (response.ok) {
        const data = await response.json();
        return data.interrupt || null;
      }
    } catch (error) {
      console.error("检查中断失败:", error);
    }
    return null;
  }

  /**
   * 恢复被中断的线程执行（发送审批决策）
   */
  async resumeExecution(
    threadId: string,
    assistantId: string,
    decision: ApprovalDecision
  ): Promise<{ content: string; thread_id: string }> {
    const response = await fetch(`${BASE_URL}/api/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        thread_id: threadId,
        assistant_id: assistantId,
        resume_data: decision,
      }),
    });
    if (!response.ok) throw new Error(`恢复执行失败: ${response.status}`);
    return await response.json();
  }

  /**
   * 流式交互
   */
  async streamRun(
    threadId: string,
    assistantId: string,
    message: string,
    onStepUpdate: (step: StreamStep) => void,
    onTokenUpdate: (token: string) => void,
    onInterrupt: (interrupt: InterruptData) => void
  ): Promise<ChatMessage> {
    if (threadId.startsWith("local_")) {
      return this.mockStreamRun(message, onStepUpdate, onTokenUpdate, onInterrupt);
    }

    try {
      const response = await fetch(`${BASE_URL}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          thread_id: threadId,
          assistant_id: assistantId,
          message: message,
        }),
      });

      if (!response.ok) throw new Error(`HTTP 异常: ${response.status}`);
      if (!response.body) throw new Error("响应主体为空");

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let finalReply = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;
          const jsonStr = trimmed.substring(6).trim();
          if (!jsonStr) continue;

          try {
            const payload = JSON.parse(jsonStr);

            if (payload.type === "step") {
              onStepUpdate({
                node: payload.node,
                timestamp: Date.now(),
                status: payload.status,
                toolName: payload.toolName || undefined,
              });
            } else if (payload.type === "token") {
              finalReply += payload.text;
              onTokenUpdate(payload.text);
            } else if (payload.type === "interrupt") {
              // 触发中断回调
              onInterrupt(payload.interrupt);
              onStepUpdate({
                node: "assistant",
                timestamp: Date.now(),
                status: "interrupted",
                toolName: payload.interrupt.tool_name,
              });
            }
          } catch (e) {
            console.warn("解析 SSE 数据包失败", e, trimmed);
          }
        }
      }

      return {
        id: `msg_res_${Date.now()}`,
        role: "assistant",
        content: finalReply,
      };
    } catch (error) {
      console.error("流式交互出错，转为 Mock 模式:", error);
      return this.mockStreamRun(message, onStepUpdate, onTokenUpdate);
    }
  }

  /** 模拟流式图执行（Mock 兜底） */
  private async mockStreamRun(
    message: string,
    onStepUpdate: (step: StreamStep) => void,
    onTokenUpdate: (token: string) => void,
    _onInterrupt?: (interrupt: InterruptData) => void
  ): Promise<ChatMessage> {
    onStepUpdate({ node: "assistant", timestamp: Date.now(), status: "thinking" });
    await new Promise(resolve => setTimeout(resolve, 1200));
    onStepUpdate({ node: "assistant", timestamp: Date.now(), status: "completed" });

    const lowerMsg = message.toLowerCase();

    if (lowerMsg.includes("weather") || lowerMsg.includes("天气") || lowerMsg.includes("旧金山")) {
      onStepUpdate({ node: "tool_node", timestamp: Date.now(), status: "calling_tool", toolName: "get_weather" });
      await new Promise(resolve => setTimeout(resolve, 1500));
      onStepUpdate({ node: "tool_node", timestamp: Date.now(), status: "completed" });
      onStepUpdate({ node: "assistant", timestamp: Date.now(), status: "thinking" });
      await new Promise(resolve => setTimeout(resolve, 800));
    }

    const mockReply = `【模拟本地回复】你好！我接收到了你的消息："${message}"。`;
    let currentText = "";
    for (const char of mockReply.split("")) {
      currentText += char;
      onTokenUpdate(char);
      await new Promise(resolve => setTimeout(resolve, 30));
    }

    onStepUpdate({ node: "assistant", timestamp: Date.now(), status: "completed" });

    return {
      id: `msg_res_${Date.now()}`,
      role: "assistant",
      content: mockReply,
    };
  }

  // --- RAG 文档管理 ---

  /** 上传文档到 RAG 向量库 */
  async uploadDocument(content: string, source: string): Promise<RagUploadResponse> {
    const response = await fetch(`${BASE_URL}/api/rag/upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, source }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || "上传失败");
    }
    return await response.json();
  }

  /** 列出已上传的文档 */
  async listDocuments(): Promise<RagDocument[]> {
    try {
      const response = await fetch(`${BASE_URL}/api/rag/documents`);
      if (response.ok) return await response.json();
      return [];
    } catch (error) {
      console.error("获取文档列表失败:", error);
      return [];
    }
  }

  /** 删除指定文档 */
  async deleteDocument(source: string): Promise<void> {
    const encodedSource = encodeURIComponent(source);
    const response = await fetch(`${BASE_URL}/api/rag/documents/${encodedSource}`, {
      method: "DELETE",
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || "删除失败");
    }
  }

  /** 清空所有文档 */
  async clearAllDocuments(): Promise<void> {
    const response = await fetch(`${BASE_URL}/api/rag/documents`, {
      method: "DELETE",
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || "清空失败");
    }
  }

  /** 获取指定文档的所有切片 */
  async getDocumentChunks(source: string): Promise<RagChunk[]> {
    const encodedSource = encodeURIComponent(source);
    try {
      const response = await fetch(`${BASE_URL}/api/rag/documents/${encodedSource}/chunks`);
      if (response.ok) return await response.json();
      return [];
    } catch (error) {
      console.error("获取文档切片失败:", error);
      return [];
    }
  }
}

export const langGraphService = new LangGraphService();
