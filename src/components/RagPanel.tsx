import React, { useState, useRef, useEffect } from "react";
import type { RagDocument, RagChunk } from "../services/langgraph";
import { langGraphService } from "../services/langgraph";
import { 
  FileText, Search, Trash2, Upload, FileUp, X, Eye, Sparkles, Loader2, Trash
} from "lucide-react";

interface RagPanelProps {
  documents: RagDocument[];
  onUpload: (content: string, source: string) => void;
  onDelete: (source: string) => void;
  onClearAll?: () => void;
  isUploading: boolean;
}

/**
 * RAG 知识库管理面板
 * 采用现代磨砂玻璃质感和沉浸式微动效，支持本地文本拖拽直传与切片明细可视化预览
 */
export const RagPanel: React.FC<RagPanelProps> = ({ 
  documents, 
  onUpload, 
  onDelete, 
  onClearAll,
  isUploading 
}) => {
  const [showForm, setShowForm] = useState(false);
  const [docName, setDocName] = useState("");
  const [docContent, setDocContent] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  
  // 拖拽与直传文件状态
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 切片明细预览状态
  const [selectedDoc, setSelectedDoc] = useState<string | null>(null);
  const [chunks, setChunks] = useState<RagChunk[]>([]);
  const [loadingChunks, setLoadingChunks] = useState(false);

  // 当预览某个文档时，载入切片数据
  useEffect(() => {
    if (selectedDoc) {
      const loadChunks = async () => {
        setLoadingChunks(true);
        try {
          const res = await langGraphService.getDocumentChunks(selectedDoc);
          setChunks(res);
        } catch (e) {
          console.error("加载切片数据失败:", e);
        } finally {
          setLoadingChunks(false);
        }
      };
      loadChunks();
    } else {
      setChunks([]);
    }
  }, [selectedDoc]);

  // 阻断拖拽默认行为并高亮
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setIsDragActive(true);
    } else if (e.type === "dragleave") {
      setIsDragActive(false);
    }
  };

  // 释放文件后读取内容
  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      await handleFileRead(file);
    }
  };

  // 点击按钮触发隐藏的文件输入框
  const handleButtonClick = () => {
    fileInputRef.current?.click();
  };

  // 处理文件上传选择
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      await handleFileRead(file);
    }
  };

  // 读取文件内容为字符串文本
  const handleFileRead = (file: File): Promise<void> => {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (event) => {
        const text = event.target?.result;
        if (typeof text === "string") {
          setDocName(file.name);
          setDocContent(text);
          setShowForm(true);
        }
        resolve();
      };
      reader.onerror = () => {
        alert("读取文件失败，请确保其为 UTF-8 编码的纯文本文件（.txt, .md, .json, .py 等）");
        resolve();
      };
      reader.readAsText(file);
    });
  };

  const handleSubmit = () => {
    if (!docName.trim() || !docContent.trim()) return;
    onUpload(docContent, docName.trim());
    setDocName("");
    setDocContent("");
    setShowForm(false);
  };

  // 实时搜索过滤
  const filteredDocuments = documents.filter(doc => 
    doc.source.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div 
      className={`relative border-b border-slate-900 bg-gradient-to-b from-[#0a0c10] to-[#0d0f14] px-5 py-4 transition-all duration-300 ${
        isDragActive ? "ring-2 ring-indigo-500/40 ring-inset" : ""
      }`}
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
    >
      {/* 拖拽上传覆盖层 */}
      {isDragActive && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-indigo-950/45 backdrop-blur-[3px] border-2 border-dashed border-indigo-500/80 m-1.5 rounded-xl transition-all duration-300 animate-pulse pointer-events-none">
          <FileUp className="w-10 h-10 text-indigo-400 mb-2" />
          <span className="text-sm font-semibold text-indigo-200">拖放文本文件至此</span>
          <span className="text-xs text-indigo-400 mt-1">自动提取名称与内容</span>
        </div>
      )}

      {/* 顶部标题与功能操作区 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400">
            <FileText className="w-4.5 h-4.5" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-bold text-slate-100">知识库管理中心</span>
              <span className="px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-xxs font-mono text-indigo-400 font-semibold">
                RAG DB
              </span>
            </div>
            <p className="text-xxs text-slate-500 mt-0.5">上传参考文档，赋能智能体检索生成</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {documents.length > 0 && onClearAll && (
            <button
              onClick={onClearAll}
              className="text-xs px-3 py-1.5 rounded-lg border border-slate-800 hover:border-rose-950 bg-slate-950/20 hover:bg-rose-950/10 text-slate-400 hover:text-rose-400 flex items-center gap-1.5 transition-all cursor-pointer"
              title="清空知识库"
            >
              <Trash className="w-3.5 h-3.5" />
              清空全部
            </button>
          )}
          <button
            onClick={() => setShowForm(!showForm)}
            className="text-xs px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold flex items-center gap-1.5 transition-all shadow-md shadow-indigo-600/10 hover:shadow-indigo-600/20 active:scale-95 cursor-pointer"
          >
            <Sparkles className="w-3.5 h-3.5" />
            {showForm ? "收起表单" : "新建文档"}
          </button>
        </div>
      </div>

      {/* 文档上传/粘贴表单 */}
      {showForm && (
        <div className="mb-4 p-4 rounded-xl bg-[#11131a] border border-slate-800/80 shadow-xl space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-400 flex items-center gap-1.5">
              <Upload className="w-3.5 h-3.5 text-indigo-400" />
              添加文档资料
            </span>
            <button
              onClick={handleButtonClick}
              className="text-xxs px-2.5 py-1 rounded border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-all cursor-pointer"
            >
              直接导入本地文件
            </button>
            <input 
              type="file" 
              ref={fileInputRef} 
              onChange={handleFileSelect} 
              accept=".txt,.md,.json,.js,.py,.ts,.html,.css" 
              className="hidden" 
            />
          </div>

          <div className="space-y-2.5">
            <input
              type="text"
              placeholder="请输入文档名称（如 常见问题手册.md）"
              value={docName}
              onChange={e => setDocName(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg bg-[#07090d] border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/30 transition-all font-mono"
            />
            <textarea
              placeholder="请在此粘贴文档内容，或者通过上方按钮直接导入本地文本文件..."
              value={docContent}
              onChange={e => setDocContent(e.target.value)}
              rows={5}
              className="w-full px-3 py-2 text-sm rounded-lg bg-[#07090d] border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/30 transition-all resize-none font-mono custom-scrollbar"
            />
          </div>

          <div className="flex justify-end gap-2 pt-1">
            <button
              onClick={() => {
                setShowForm(false);
                setDocName("");
                setDocContent("");
              }}
              className="text-xs px-3.5 py-1.5 rounded-lg border border-slate-800 bg-slate-900/40 hover:bg-slate-900 text-slate-400 hover:text-slate-200 transition-all cursor-pointer"
            >
              取消
            </button>
            <button
              onClick={handleSubmit}
              disabled={isUploading || !docName.trim() || !docContent.trim()}
              className="text-xs px-4 py-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-all font-semibold flex items-center gap-1.5 cursor-pointer"
            >
              {isUploading && <Loader2 className="w-3 h-3 animate-spin" />}
              {isUploading ? "正在解析向量入库..." : "确认上传"}
            </button>
          </div>
        </div>
      )}

      {/* 搜索与过滤栏 */}
      {documents.length > 0 && (
        <div className="mb-3 relative group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 group-focus-within:text-indigo-400 transition-colors" />
          <input
            type="text"
            placeholder="搜索库中已有文档名称..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-1.5 text-xs rounded-lg bg-[#11131a]/60 border border-slate-800 text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/20 transition-all"
          />
          {searchQuery && (
            <button 
              onClick={() => setSearchQuery("")} 
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      )}

      {/* 文档卡片展示列表 */}
      {filteredDocuments.length === 0 ? (
        <div className="text-center py-6 border border-dashed border-slate-800/40 rounded-xl bg-slate-950/10">
          <p className="text-xs text-slate-600">
            {searchQuery ? "未搜索到匹配的文档" : "当前知识库暂无文档资料"}
          </p>
          {!showForm && !searchQuery && (
            <p className="text-xxs text-slate-700 mt-1">
              可拖放任意文本文件至此，或点击右上角「新建文档」
            </p>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-48 overflow-y-auto pr-1 custom-scrollbar">
          {filteredDocuments.map(doc => (
            <div
              key={doc.source}
              className="group flex items-center justify-between px-3.5 py-2.5 rounded-lg border border-slate-800/40 bg-[#11131a]/40 hover:bg-[#151821]/80 hover:border-indigo-500/25 transition-all duration-300 cursor-pointer"
              onClick={() => setSelectedDoc(doc.source)}
              title="点击查看切片预览"
            >
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-8 h-8 rounded-lg bg-indigo-500/5 flex items-center justify-center border border-slate-800/60 flex-shrink-0 group-hover:bg-indigo-500/10 group-hover:border-indigo-500/15 transition-colors">
                  <FileText className="w-4 h-4 text-indigo-400" />
                </div>
                <div className="min-w-0">
                  <span className="text-xs font-semibold text-slate-300 truncate block group-hover:text-slate-100 transition-colors">
                    {doc.source}
                  </span>
                  <span className="text-xxs text-slate-500 mt-0.5 block font-mono">
                    包含切片：<span className="text-indigo-400 font-semibold">{doc.chunk_count}</span> 段
                  </span>
                </div>
              </div>
              
              {/* 卡片浮动操作按钮组 */}
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={e => e.stopPropagation()}>
                <button
                  onClick={() => setSelectedDoc(doc.source)}
                  className="p-1.5 rounded hover:bg-indigo-500/10 text-indigo-400 hover:text-indigo-300 transition-all cursor-pointer"
                  title="查看切片明细"
                >
                  <Eye className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => onDelete(doc.source)}
                  className="p-1.5 rounded hover:bg-rose-500/10 text-slate-500 hover:text-rose-400 transition-all cursor-pointer"
                  title="删除文档"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 切片明细预览模态框 (Chunk Preview Modal) */}
      {selectedDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in">
          <div className="relative flex flex-col w-full max-w-2xl max-h-[80vh] rounded-2xl border border-slate-800 bg-[#0f1118] shadow-2xl overflow-hidden">
            
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800/80 bg-[#12151e]">
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-indigo-400" />
                <div>
                  <h3 className="text-sm font-bold text-slate-200 truncate max-w-md">
                    {selectedDoc}
                  </h3>
                  <p className="text-xxs text-slate-500 mt-0.5">
                    已被切分为 <span className="text-indigo-400 font-bold font-mono">{chunks.length}</span> 个向量切片段落
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedDoc(null)}
                className="p-1.5 rounded-lg border border-slate-800 hover:border-slate-700 bg-slate-900/50 text-slate-400 hover:text-slate-200 transition-all cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar bg-[#090a0f]">
              {loadingChunks ? (
                <div className="flex flex-col items-center justify-center py-20">
                  <Loader2 className="w-8 h-8 text-indigo-500 animate-spin mb-3" />
                  <span className="text-xs text-slate-500">正在从向量数据库拉取切片明细...</span>
                </div>
              ) : chunks.length === 0 ? (
                <div className="text-center py-20 text-xs text-slate-600">
                  该文件未提取到任何切片，请确认文档内容是否有效。
                </div>
              ) : (
                chunks.map((chunk, index) => (
                  <div 
                    key={chunk.chunk_id}
                    className="p-4 rounded-xl border border-slate-800 bg-[#11131b]/60 hover:bg-[#131622] hover:border-slate-700/60 transition-all duration-200"
                  >
                    <div className="flex items-center justify-between mb-2 pb-1.5 border-b border-slate-800/40">
                      <span className="px-2.5 py-0.5 rounded-md bg-indigo-500/10 text-indigo-400 text-xxs font-bold font-mono">
                        Chunk #{index + 1}
                      </span>
                      <span className="text-xxs text-slate-500 font-mono">
                        字符长度: <span className="text-slate-400">{chunk.text.length}</span> 字
                      </span>
                    </div>
                    <p className="text-xs text-slate-300 font-mono leading-relaxed whitespace-pre-wrap selection:bg-indigo-500/30">
                      {chunk.text}
                    </p>
                  </div>
                ))
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex justify-end px-6 py-3.5 border-t border-slate-800/80 bg-[#12151e]">
              <button
                onClick={() => setSelectedDoc(null)}
                className="text-xs px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition-all shadow-md active:scale-95 cursor-pointer"
              >
                关闭预览
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
