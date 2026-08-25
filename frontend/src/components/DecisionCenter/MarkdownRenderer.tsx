import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

/**
 * Preprocess raw LLM markdown text to fix common LaTeX/formatting artifacts.
 */
function cleanMarkdownText(raw: string): string {
  if (!raw) return '';
  return raw
    .replace(/\\\$/g, '$')
    .replace(/\$\\rightarrow\$/g, '→')
    .replace(/\\rightarrow/g, '→')
    .replace(/\$\\leftarrow\$/g, '←')
    .replace(/\\leftarrow/g, '←')
    .replace(/\$\\approx\$/g, '≈')
    .replace(/\\approx/g, '≈')
    .replace(/\$\\ge\$/g, '≥')
    .replace(/\$\\le\$/g, '≤')
    .replace(/\$\\times\$/g, '×')
    .replace(/\\times/g, '×');
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content, className = '' }) => {
  const cleaned = cleanMarkdownText(content);

  return (
    <div className={`ai-markdown-content text-xs leading-relaxed text-slate-200 ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-sm sm:text-base font-bold text-amber-300 mt-2 mb-1.5 pb-1 border-b border-amber-500/20 flex items-center gap-1.5">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-xs sm:text-sm font-bold text-slate-100 mt-2.5 mb-1.5 flex items-center gap-1.5 text-amber-400/90">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-[12px] sm:text-xs font-semibold text-cyan-300 mt-2 mb-1 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 inline-block shrink-0" />
              <span>{children}</span>
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-[11px] font-semibold text-slate-300 mt-1.5 mb-0.5">
              {children}
            </h4>
          ),
          p: ({ children }) => (
            <p className="mb-2 last:mb-0 leading-relaxed text-slate-200">
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul className="space-y-1 my-1.5 pl-4 list-disc marker:text-amber-400 text-slate-200">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="space-y-1 my-1.5 pl-4 list-decimal marker:text-amber-400 font-mono text-slate-200">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="pl-0.5 leading-relaxed">
              {children}
            </li>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-amber-200/90 font-sans">
              {children}
            </strong>
          ),
          em: ({ children }) => (
            <em className="italic text-slate-400 font-sans">
              {children}
            </em>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-amber-500/70 bg-amber-500/5 px-2.5 py-1.5 my-2 rounded-r-md text-slate-300 italic text-[11px]">
              {children}
            </blockquote>
          ),
          code: ({ inline, className: codeClass, children, ...props }: any) => {
            if (inline) {
              return (
                <code
                  className="px-1.5 py-0.5 mx-0.5 rounded bg-slate-800 border border-slate-700 text-amber-300 font-mono text-[11px]"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <div className="my-2 rounded-lg bg-slate-950 border border-slate-800 p-2.5 overflow-x-auto shadow-inner">
                <code className="text-[11px] font-mono text-slate-200 block leading-relaxed" {...props}>
                  {children}
                </code>
              </div>
            );
          },
          table: ({ children }) => (
            <div className="my-2.5 overflow-x-auto rounded-lg border border-slate-800 shadow-md">
              <table className="min-w-full divide-y divide-slate-800 text-[11px] text-left">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-slate-800/90 text-amber-300 font-semibold uppercase font-mono text-[10px] tracking-wider">
              {children}
            </thead>
          ),
          tbody: ({ children }) => (
            <tbody className="divide-y divide-slate-800/60 bg-slate-900/60 font-mono">
              {children}
            </tbody>
          ),
          tr: ({ children }) => (
            <tr className="hover:bg-slate-800/40 transition-colors">
              {children}
            </tr>
          ),
          th: ({ children }) => (
            <th className="px-3 py-2 text-left font-bold text-amber-300 border-b border-slate-700/80">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-1.5 text-slate-300 whitespace-nowrap">
              {children}
            </td>
          ),
          hr: () => <hr className="my-2.5 border-slate-800/80" />,
        }}
      >
        {cleaned}
      </ReactMarkdown>
    </div>
  );
};
export default MarkdownRenderer;
