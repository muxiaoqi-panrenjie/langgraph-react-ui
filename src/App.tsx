import React, { useState, useEffect } from "react";
import { AgentSelector } from "./components/AgentSelector";
import { ChatWindow } from "./components/ChatWindow";
import { StepTracker } from "./components/StepTracker";
import { ApprovalModal } from "./components/ApprovalModal";
import { RagPanel } from "./components/RagPanel";
import {
  langGraphService,
  type Assistant,
  type Thread,
  type ChatMessage,
  type StreamStep,
  type InterruptData,
  type ApprovalDecision,
  type RagDocument,
} from "./services/langgraph";

/**
 * 应用程序根组件
 * 采用三栏式布局，集中管理智能体、会话、聊天历史及流式运行的全局状态
 */
export const App: React.FC = () => {
  // --- 状态定义 ---
  
  // 智能体（Agent/Assistant）相关状态
  const [assistants, setAssistants] = useState<Assistant[]>([]); // 智能体配置列表
  const [activeAssistant, setActiveAssistant] = useState<Assistant | null>(null); // 当前选中的活动智能体
  const [loadingAssistants, setLoadingAssistants] = useState(false); // 加载智能体列表时的加载状态

  // 会话线程（Thread）相关状态
  const [threads, setThreads] = useState<Thread[]>([]); // 所有的历史会话线程列表
  const [activeThreadId, setActiveThreadId] = useState<string | null>(null); // 当前正在对话的活动会话 ID

  // 消息与运行图（Graph Run）轨迹状态
  const [messages, setMessages] = useState<ChatMessage[]>([]); // 当前会话的聊天消息历史列表
  const [steps, setSteps] = useState<StreamStep[]>([]); // 当前对话运行中的 Graph 节点流式流转步骤记录

  // 流式交互（Streaming Response）控制状态
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingReply, setStreamingReply] = useState("");

  // HITL 中断审批状态
  const [pendingInterrupt, setPendingInterrupt] = useState<InterruptData | null>(null);

  // RAG 文档管理状态
  const [ragDocuments, setRagDocuments] = useState<RagDocument[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  // --- RAG 文档管理 ---

  /** 刷新文档列表 */
  const fetchRagDocuments = async () => {
    try {
      const docs = await langGraphService.listDocuments();
      setRagDocuments(docs);
    } catch (error) {
      console.error("获取 RAG 文档列表失败:", error);
    }
  };

  /** 上传文档 */
  const handleUploadDocument = async (content: string, source: string) => {
    if (!content.trim() || !source.trim()) return;
    setIsUploading(true);
    try {
      await langGraphService.uploadDocument(content, source);
      await fetchRagDocuments();
    } catch (error) {
      console.error("上传文档失败:", error);
      alert("上传失败，请重试");
    } finally {
      setIsUploading(false);
    }
  };

  /** 删除文档 */
  const handleDeleteDocument = async (source: string) => {
    try {
      await langGraphService.deleteDocument(source);
      await fetchRagDocuments();
    } catch (error) {
      console.error("删除文档失败:", error);
      alert("删除失败，请重试");
    }
  };

  /** 清空所有文档 */
  const handleClearAllDocuments = async () => {
    if (!window.confirm("确定要清空知识库中的所有文档吗？此操作不可恢复。")) return;
    try {
      await langGraphService.clearAllDocuments();
      await fetchRagDocuments();
    } catch (error) {
      console.error("清空所有文档失败:", error);
      alert("清空失败，请重试");
    }
  };

  // 当切换到 RAG Assistant 时加载文档列表
  useEffect(() => {
    if (activeAssistant?.assistant_id === "RAG Assistant") {
      fetchRagDocuments();
    }
  }, [activeAssistant?.assistant_id]);

  // --- 副作用与初始化逻辑 ---

  /**
   * 异步拉取智能体列表
   * 若后端服务不可用，底层服务会自动降级为本地 Mock 数据
   */
  const fetchAssistants = async () => {
    setLoadingAssistants(true);
    try {
      const list = await langGraphService.listAssistants();
      setAssistants(list);
      // 默认选中拉取到的第一个智能体
      if (list.length > 0 && !activeAssistant) {
        setActiveAssistant(list[0]);
      }
    } catch (error) {
      console.error("加载 Agents 失败:", error);
    } finally {
      setLoadingAssistants(false);
    }
  };

  // 页面挂载时：初始化拉取 Agent 列表，并从本地缓存加载历史会话列表
  useEffect(() => {
    fetchAssistants();
    
    // 从浏览器的 localStorage 加载历史 Thread 列表以实现持久化
    const savedThreads = localStorage.getItem("langgraph_threads");
    if (savedThreads) {
      try {
        const parsed = JSON.parse(savedThreads) as Thread[];
        setThreads(parsed);
        // 如果有历史会话，默认选中第一个
        if (parsed.length > 0) {
          setActiveThreadId(parsed[0].thread_id);
        }
      } catch (e) {
        console.error("解析本地 Threads 历史失败:", e);
      }
    }
  }, []);

  // 监听活动会话 ID 的切换，负责清空状态并重新加载对应会话的历史记录
  useEffect(() => {
    // 如果没有活动会话，重置聊天与步骤面板
    if (!activeThreadId) {
      setMessages([]);
      setSteps([]);
      return;
    }

    setSteps([]); // 清除图的流转痕迹，等待下一次运行
    setMessages([]); // 关键修复：切换/新建 Thread 时，先清空当前消息，防止残留上一个会话的内容

    /**
     * 载入当前 Thread 的历史消息
     */
    const loadMessages = async () => {
      // 1. 优先从本地 localStorage 缓存中读取，实现页面无缝瞬间载入
      const localCacheKey = `langgraph_messages_${activeThreadId}`;
      const cached = localStorage.getItem(localCacheKey);
      if (cached) {
        try {
          setMessages(JSON.parse(cached));
        } catch (e) {
          console.error("解析缓存消息失败", e);
        }
      }

      // 2. 如果不是本地自建的虚拟会话（即真实的后端会话），去后端 API 拉取最新的消息记录进行同步
      if (!activeThreadId.startsWith("local_")) {
        const remoteMsgs = await langGraphService.getThreadMessages(activeThreadId);
        if (remoteMsgs.length > 0) {
          setMessages(remoteMsgs);
          // 同步更新本地缓存
          localStorage.setItem(localCacheKey, JSON.stringify(remoteMsgs));
        }
      }
    };

    loadMessages();
  }, [activeThreadId]);

  // --- 会话管理相关函数 ---

  /**
   * 创建一个全新的会话线程 (Thread)
   */
  const handleCreateThread = async () => {
    // 调用后端接口创建 Thread（若失败会自动降级为 local_ 前缀 of 本地 Thread）
    const newThread = await langGraphService.createThread();
    const updatedThreads = [newThread, ...threads];
    setThreads(updatedThreads);
    // 持久化更新会话列表缓存
    localStorage.setItem("langgraph_threads", JSON.stringify(updatedThreads));
    // 切换至新创建的会话
    setActiveThreadId(newThread.thread_id);
  };

  /**
   * 删除指定的会话线程 (Thread)
   * @param threadId 待删除的会话 ID
   */
  const handleDeleteThread = (threadId: string) => {
    // 从列表中移除
    const updated = threads.filter(t => t.thread_id !== threadId);
    setThreads(updated);
    localStorage.setItem("langgraph_threads", JSON.stringify(updated));
    // 清除该会话在本地缓存的历史对话内容
    localStorage.removeItem(`langgraph_messages_${threadId}`);

    // 如果删除的是当前处于活动状态的会话，需要自动切换活动指针
    if (activeThreadId === threadId) {
      if (updated.length > 0) {
        setActiveThreadId(updated[0].thread_id);
      } else {
        setActiveThreadId(null);
      }
    }
  };

  // --- 消息发送与流式运行处理 ---

  /**
   * 发送用户消息并触发智能体图的运行（流式响应）
   */
  const handleSendMessage = async (text: string) => {
    if (!activeThreadId || !activeAssistant || isStreaming) return;

    const userMsg: ChatMessage = {
      id: `msg_user_${Date.now()}`,
      role: "user",
      content: text,
    };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    localStorage.setItem(`langgraph_messages_${activeThreadId}`, JSON.stringify(newMessages));

    setIsStreaming(true);
    setStreamingReply("");
    setSteps([]);
    setPendingInterrupt(null); // 清除之前的中断

    try {
      const finalReplyMsg = await langGraphService.streamRun(
        activeThreadId,
        activeAssistant.assistant_id,
        text,
        // 1. 步骤状态更新回调
        (newStep) => {
          setSteps(prev => {
            const existingIdx = prev.findIndex(s => s.node === newStep.node);
            if (existingIdx !== -1) {
              const updated = [...prev];
              updated[existingIdx] = {
                ...updated[existingIdx],
                status: newStep.status,
                toolName: newStep.toolName || updated[existingIdx].toolName,
                timestamp: newStep.timestamp,
              };
              return updated;
            }
            return [...prev, newStep];
          });
        },
        // 2. 文本 Token 流式回调
        (token) => {
          setStreamingReply(prev => prev + token);
        },
        // 3. 中断回调（触发审批弹窗）
        (interrupt: InterruptData) => {
          setPendingInterrupt(interrupt);
          setIsStreaming(false); // 停止流式状态，等待用户审批
        }
      );

      // 如果有中断，finalReplyMsg 可能为空，不追加消息
      if (finalReplyMsg.content) {
        setMessages(prev => {
          const finalMsgs = [...prev, finalReplyMsg];
          localStorage.setItem(`langgraph_messages_${activeThreadId}`, JSON.stringify(finalMsgs));
          return finalMsgs;
        });
      }
    } catch (e) {
      console.error("对话执行失败:", e);
    } finally {
      setIsStreaming(false);
      setStreamingReply("");
    }
  };

  /**
   * 处理中断审批决策（approve / reject / edit）
   * 调用后端 resume API 恢复图执行
   */
  const handleApprovalDecision = async (decision: ApprovalDecision) => {
    if (!activeThreadId || !activeAssistant || !pendingInterrupt) return;

    setPendingInterrupt(null); // 关闭弹窗
    setStreamingReply("");

    try {
      // 通过 API 恢复执行
      const result = await langGraphService.resumeExecution(
        activeThreadId,
        activeAssistant.assistant_id,
        decision
      );

      // 更新执行步骤状态为已完成
      setSteps(prev =>
        prev.map(s =>
          s.status === "interrupted"
            ? { ...s, status: "completed" as const, timestamp: Date.now() }
            : s
        )
      );

      // 将恢复后的结果追加到消息列表
      if (result.content) {
        const replyMsg: ChatMessage = {
          id: `msg_resume_${Date.now()}`,
          role: "assistant",
          content: result.content,
        };
        setMessages(prev => {
          const msgs = [...prev, replyMsg];
          localStorage.setItem(`langgraph_messages_${activeThreadId}`, JSON.stringify(msgs));
          return msgs;
        });
      }

      // 从后端重新加载完整消息历史（确保一致性）
      const remoteMsgs = await langGraphService.getThreadMessages(activeThreadId);
      if (remoteMsgs.length > 0) {
        setMessages(remoteMsgs);
        localStorage.setItem(`langgraph_messages_${activeThreadId}`, JSON.stringify(remoteMsgs));
      }
    } catch (e) {
      console.error("恢复执行失败:", e);
    }
  };

  // --- UI 渲染布局 (三栏式设计) ---
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#07080a] font-sans antialiased text-slate-300">

      {/* 1. 左侧面板：Agent 智能体切换与会话列表管理区域 */}
      <AgentSelector
        assistants={assistants}
        activeAssistant={activeAssistant}
        onSelectAssistant={setActiveAssistant}
        threads={threads}
        activeThreadId={activeThreadId}
        onSelectThread={setActiveThreadId}
        onCreateThread={handleCreateThread}
        onDeleteThread={handleDeleteThread}
        loadingAssistants={loadingAssistants}
        onRefreshAssistants={fetchAssistants}
      />

      {/* 2. 中间面板：主聊天视窗与用户消息输入区域 */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* RAG 文档管理面板（仅在选中 RAG Assistant 时显示） */}
        {activeAssistant?.assistant_id === "RAG Assistant" && (
          <RagPanel
            documents={ragDocuments}
            onUpload={handleUploadDocument}
            onDelete={handleDeleteDocument}
            onClearAll={handleClearAllDocuments}
            isUploading={isUploading}
          />
        )}
        <ChatWindow
          messages={messages}
          activeAssistant={activeAssistant}
          activeThreadId={activeThreadId}
          onSendMessage={handleSendMessage}
          isStreaming={isStreaming}
          streamingReply={streamingReply}
        />
      </div>

      {/* 3. 右侧面板：当前运行图节点与工具链流转动态追踪面板 */}
      <StepTracker steps={steps} isStreaming={isStreaming} />

      {/* 4. HITL 中断审批弹窗 */}
      {pendingInterrupt && (
        <ApprovalModal
          interrupt={pendingInterrupt}
          assistant={activeAssistant}
          onApprove={handleApprovalDecision}
          onReject={handleApprovalDecision}
          onEdit={handleApprovalDecision}
        />
      )}
    </div>
  );
};

export default App;
