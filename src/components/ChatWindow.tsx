import React, { useState, useRef, useEffect } from "react";
import type { ChatMessage, Assistant } from "../services/langgraph";
import { Send, User, Bot, HelpCircle } from "lucide-react";
import Prism from "prismjs";
import "prismjs/components/prism-javascript";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-python";
import "prismjs/components/prism-java"; // required by write_code tool output
import "prismjs/components/prism-jsx"; // required by prism-tsx
import "prismjs/components/prism-tsx";
import "prismjs/components/prism-css";
import "prismjs/components/prism-markup"; // HTML/XML support

interface ChatWindowProps {
  messages: ChatMessage[];
  activeAssistant: Assistant | null;
  activeThreadId: string | null;
  onSendMessage: (text: string) => void;
  isStreaming: boolean;
  streamingReply: string;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({
  messages,
  activeAssistant,
  activeThreadId,
  onSendMessage,
  isStreaming,
  streamingReply,
}) => {
  const [inputText, setInputText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到最新消息
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
    Prism.highlightAll();
  }, [messages, streamingReply, isStreaming]);

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || isStreaming || !activeThreadId || !activeAssistant) return;
    onSendMessage(inputText);
    setInputText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend(e);
    }
  };

  const renderMessageContent = (content: string) => {
    // 简单的代码块和粗体处理，以提供流畅清晰的排版体验
    const parts = content.split(/(```[\s\S]*?```|\*\*.*?\*\*)/g);
    return parts.map((part, index) => {
      if (part.startsWith("```") && part.endsWith("```")) {
        // 匹配第一行提取语言名称，默认为 javascript
        const match = /```([a-zA-Z0-9#+-]+)\n/.exec(part);
        const lang = match ? match[1].toLowerCase() : "javascript";
        
        // 切除反引号和第一行的语言声明
        const code = part.slice(3, -3).replace(/^[a-zA-Z0-9#+-]+\n/, "");
        
        return (
          <pre key={index} className="bg-slate-950 p-4 rounded-lg my-2 font-mono text-xs overflow-x-auto border border-slate-800">
            <code className={`language-${lang}`}>{code}</code>
          </pre>
        );
      } else if (part.startsWith("**") && part.endsWith("**")) {
        return (
          <strong key={index} className="text-white font-bold">
            {part.slice(2, -2)}
          </strong>
        );
      }
      return <span key={index} className="whitespace-pre-wrap">{part}</span>;
    });
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#0a0b0d] text-slate-100 relative">
      {/* 顶部 Agent 描述栏 */}
      <div className="h-16 border-b border-slate-800/80 bg-[#0d0e12]/60 backdrop-blur-md px-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-indigo-950/50 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <h2 className="font-bold text-sm text-white">
              {activeAssistant ? activeAssistant.name : "请先选择 Agent"}
            </h2>
            <p className="text-xxs text-slate-500 font-mono mt-0.5">
              Thread: {activeThreadId || "未开启"}
            </p>
          </div>
        </div>
        {!activeThreadId && (
          <div className="text-xs text-amber-500/80 bg-amber-950/20 border border-amber-500/20 px-3 py-1 rounded-full font-semibold animate-pulse">
            ⚠️ 请先在侧栏创建或选择会话线程
          </div>
        )}
      </div>

      {/* 聊天消息区 */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
        {messages.length === 0 && !isStreaming ? (
          <div className="h-full flex flex-col items-center justify-center text-center text-slate-600 max-w-md mx-auto space-y-3">
            <HelpCircle className="w-12 h-12 text-slate-800" />
            <div className="font-bold text-slate-400">准备就绪！</div>
            <p className="text-xs text-slate-500 leading-relaxed">
              在下方输入框中发送你的问题。你可以查询天气、检索电影，或运行深度研究。智能体将自动在右侧面板展示其内部图节点的执行流程。
            </p>
            {activeAssistant?.assistant_id === "101 Weather Agent" && (
              <div className="text-left w-full bg-slate-950/40 border border-slate-800 p-3 rounded-lg text-xxs font-mono space-y-1">
                <div>💡 **试一试输入：**</div>
                <div className="text-slate-400">“今天旧金山的天气怎么样 (37.77° N, 122.42° W)，还有什么好看的科幻电影推荐？”</div>
              </div>
            )}
          </div>
        ) : (
          <>
            {messages.map((msg) => {
              const isUser = msg.role === "user";
              return (
                <div key={msg.id} className={`flex gap-4 ${isUser ? "justify-end" : "justify-start"}`}>
                  {!isUser && (
                    <div className="w-8 h-8 rounded-lg bg-indigo-950 border border-indigo-500/20 flex items-center justify-center text-indigo-400 shrink-0 shadow-md">
                      <Bot className="w-4 h-4" />
                    </div>
                  )}
                  <div className={`max-w-[70%] p-4 rounded-2xl text-sm leading-relaxed ${
                    isUser
                      ? "bg-gradient-to-br from-indigo-600 to-indigo-700 text-white rounded-tr-none shadow-lg shadow-indigo-500/10 border border-indigo-500/20"
                      : "bg-[#13151a]/95 text-slate-300 rounded-tl-none border border-slate-800/80 shadow-md"
                  }`}>
                    {renderMessageContent(msg.content)}
                  </div>
                  {isUser && (
                    <div className="w-8 h-8 rounded-lg bg-slate-800 flex items-center justify-center text-slate-300 shrink-0 shadow-md border border-slate-700">
                      <User className="w-4 h-4" />
                    </div>
                  )}
                </div>
              );
            })}

            {/* 流式生成中的消息气泡 */}
            {isStreaming && (
              <div className="flex gap-4 justify-start">
                <div className="w-8 h-8 rounded-lg bg-indigo-950 border border-indigo-500/20 flex items-center justify-center text-indigo-400 shrink-0 shadow-md animate-pulse">
                  <Bot className="w-4 h-4" />
                </div>
                <div className="max-w-[70%] p-4 rounded-2xl text-sm leading-relaxed bg-[#13151a]/95 text-slate-300 rounded-tl-none border border-slate-800/80 shadow-md">
                  {streamingReply ? (
                    renderMessageContent(streamingReply)
                  ) : (
                    <div className="flex items-center gap-1.5 py-1">
                      <div className="w-2.5 h-2.5 bg-indigo-500 rounded-full animate-bounce" />
                      <div className="w-2.5 h-2.5 bg-indigo-500 rounded-full animate-bounce [animation-delay:0.2s]" />
                      <div className="w-2.5 h-2.5 bg-indigo-500 rounded-full animate-bounce [animation-delay:0.4s]" />
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 底部输入区 */}
      <div className="p-5 border-t border-slate-800/80 bg-[#0d0e12]/40 backdrop-blur-md">
        <form onSubmit={handleSend} className="max-w-4xl mx-auto flex items-end gap-3 bg-[#13151a] border border-slate-800 rounded-2xl p-2 focus-within:border-indigo-500/50 focus-within:ring-1 focus-within:ring-indigo-500/20 transition-all">
          <textarea
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              !activeAssistant
                ? "请先在侧栏选择一个 Agent..."
                : !activeThreadId
                ? "请点击侧栏“新建会话”..."
                : `向 ${activeAssistant.name} 发送消息... (Enter 发送，Shift+Enter 换行)`
            }
            disabled={isStreaming || !activeThreadId || !activeAssistant}
            className="flex-1 max-h-32 min-h-[44px] h-[44px] bg-transparent text-sm text-slate-200 placeholder-slate-600 resize-none py-3 px-3 outline-none disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!inputText.trim() || isStreaming || !activeThreadId || !activeAssistant}
            className="w-10 h-10 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white flex items-center justify-center transition-all active:scale-95 disabled:opacity-30 disabled:hover:bg-indigo-600 disabled:scale-100"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
};
