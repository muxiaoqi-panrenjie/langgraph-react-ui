import React from "react";
import type { Assistant, Thread } from "../services/langgraph";
import { Bot, MessageSquare, Plus, RefreshCw, Trash2, Cpu } from "lucide-react";

interface AgentSelectorProps {
  assistants: Assistant[];
  activeAssistant: Assistant | null;
  onSelectAssistant: (assistant: Assistant) => void;
  threads: Thread[];
  activeThreadId: string | null;
  onSelectThread: (threadId: string) => void;
  onCreateThread: () => void;
  onDeleteThread: (threadId: string) => void;
  loadingAssistants: boolean;
  onRefreshAssistants: () => void;
}

export const AgentSelector: React.FC<AgentSelectorProps> = ({
  assistants,
  activeAssistant,
  onSelectAssistant,
  threads,
  activeThreadId,
  onSelectThread,
  onCreateThread,
  onDeleteThread,
  loadingAssistants,
  onRefreshAssistants,
}) => {
  return (
    <div className="w-80 border-r border-slate-800 bg-[#0d0e12]/80 backdrop-blur-xl flex flex-col h-full text-slate-200">
      {/* 顶部标题区 */}
      <div className="p-5 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Cpu className="w-5 h-5 text-white animate-pulse" />
          </div>
          <div>
            <h1 className="font-bold text-lg bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
              LangGraph Studio
            </h1>
            <p className="text-xs text-slate-500 font-mono">localhost:2024</p>
          </div>
        </div>
        <button
          onClick={onRefreshAssistants}
          disabled={loadingAssistants}
          className="p-1.5 rounded-lg border border-slate-800 hover:border-slate-700 bg-slate-900/50 hover:bg-slate-900 text-slate-400 hover:text-slate-200 transition-all active:scale-95 disabled:opacity-50"
          title="刷新 Agent 列表"
        >
          <RefreshCw className={`w-4 h-4 ${loadingAssistants ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* 1. 选择 Agent 列表 */}
      <div className="p-4 flex-1 overflow-y-auto space-y-4 custom-scrollbar">
        <div>
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2 font-mono">
            选择 Agent 节点
          </h2>
          <div className="space-y-1.5">
            {loadingAssistants ? (
              <div className="text-center py-4 text-xs text-slate-500">
                加载 Agent 列表中...
              </div>
            ) : (
              assistants.map((assistant) => {
                const isActive = activeAssistant?.assistant_id === assistant.assistant_id;
                return (
                  <button
                    key={assistant.assistant_id}
                    onClick={() => onSelectAssistant(assistant)}
                    className={`w-full text-left p-3 rounded-xl border flex items-center gap-3 transition-all duration-300 relative group overflow-hidden ${
                      isActive
                        ? "border-indigo-500/30 bg-gradient-to-r from-indigo-950/40 to-slate-900/40 text-white shadow-md shadow-indigo-500/5"
                        : "border-slate-800/40 bg-slate-950/20 text-slate-400 hover:text-slate-200 hover:border-slate-700 hover:bg-slate-900/30"
                    }`}
                  >
                    {isActive && (
                      <div className="absolute left-0 top-0 bottom-0 w-1 bg-indigo-500 rounded-r-md" />
                    )}
                    <div
                      className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors ${
                        isActive ? "bg-indigo-600/20 text-indigo-400" : "bg-slate-900 text-slate-500 group-hover:text-slate-400"
                      }`}
                    >
                      <Bot className="w-5 h-5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-sm truncate">{assistant.name}</div>
                      <div className="text-xxs text-slate-500 truncate font-mono mt-0.5">
                        {assistant.graph_id || "graph"}
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* 2. 会话线程历史 (Threads) */}
        <div className="pt-4 border-t border-slate-800/60">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider font-mono">
              会话历史 (Threads)
            </h2>
            <button
              onClick={onCreateThread}
              className="flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 transition-colors font-semibold"
            >
              <Plus className="w-3.5 h-3.5" />
              新建会话
            </button>
          </div>

          <div className="space-y-1 max-h-64 overflow-y-auto pr-1 custom-scrollbar">
            {threads.length === 0 ? (
              <div className="text-center py-6 border border-dashed border-slate-800/60 rounded-xl text-xs text-slate-600">
                暂无历史会话记录
              </div>
            ) : (
              threads.map((thread) => {
                const isSelected = activeThreadId === thread.thread_id;
                const formattedDate = new Date(thread.created_at).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                });
                return (
                  <div
                    key={thread.thread_id}
                    className={`group w-full flex items-center justify-between p-2.5 rounded-lg transition-all ${
                      isSelected
                        ? "bg-slate-900 text-white font-semibold"
                        : "text-slate-400 hover:bg-slate-900/40 hover:text-slate-300"
                    }`}
                  >
                    <button
                      onClick={() => onSelectThread(thread.thread_id)}
                      className="flex-1 text-left flex items-center gap-2 min-w-0"
                    >
                      <MessageSquare className="w-4 h-4 shrink-0 text-slate-500" />
                      <div className="flex-1 min-w-0">
                        <div className="text-xs truncate font-mono">{thread.thread_id}</div>
                        <div className="text-xxs text-slate-600 font-mono">{formattedDate}</div>
                      </div>
                    </button>
                    <button
                      onClick={() => onDeleteThread(thread.thread_id)}
                      className="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-rose-950/40 text-slate-500 hover:text-rose-400 transition-all active:scale-90"
                      title="删除此会话"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* 底部信息区 */}
      <div className="p-4 border-t border-slate-800/80 bg-slate-950/20 text-xxs text-slate-600 font-mono text-center">
        Powered by LangGraph & Tailwind v4
      </div>
    </div>
  );
};
