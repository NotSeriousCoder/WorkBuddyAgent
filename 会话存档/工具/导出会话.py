# -*- coding: utf-8 -*-
"""
WorkBuddy 会话记录导出工具
================================================================

作用：把某个工作空间的 WorkBuddy 会话记录，导出成「原始存档 + 可读全文 Markdown」。

WorkBuddy 会把每个工作空间的会话记录保存在：
    ~/.workbuddy/projects/<工作空间路径编码>/<会话ID>.jsonl

其中 <工作空间路径编码> 的规则为：绝对路径的 ":" 与 "\\" 都替换为 "-"，盘符转小写。
例：G:\\项目\\WorkBuddy项目\\东风日产组织分析  ->  g-项目-WorkBuddy项目-东风日产组织分析

用法：
    python 导出会话.py --workspace "G:\\项目\\WorkBuddy项目\\东风日产组织分析" --out "输出目录"

参数：
    --workspace  工作空间绝对路径（必填）
    --out        输出目录（必填）
    --home       .workbuddy 目录，默认 ~/.workbuddy
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sys

RAW_SUFFIXES = ('.jsonl', '.meta.json', '.file-rollback.ndjson')

RE_REMINDER = re.compile(r'<system-reminder[\s\S]*?</system-reminder>')
RE_USERQUERY = re.compile(r'<user_query>\s*([\s\S]*?)\s*</user_query>')


def encode_workspace(path):
    """把工作空间路径编码成 ~/.workbuddy/projects 下的目录名。"""
    p = os.path.abspath(path).replace('\\', '/')
    p = p.replace(':/', '-').replace('/', '-')
    if len(p) > 1:
        p = p[0].lower() + p[1:]
    return p


def fmt_time(ms):
    if not ms:
        return ''
    try:
        dt = datetime.datetime.fromtimestamp(ms / 1000.0)
    except Exception:
        return str(ms)
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def strify(v):
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, ensure_ascii=False, indent=2)
    except Exception:
        return str(v)


def text_of(content):
    """从 message / reasoning 的 content 字段抽取纯文本。"""
    if content is None:
        return ''
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return strify(content)
    parts = []
    for it in content:
        if isinstance(it, str):
            parts.append(it)
        elif isinstance(it, dict):
            if isinstance(it.get('text'), str):
                parts.append(it['text'])
            elif it.get('type') in ('image', 'image_url'):
                parts.append('[图片内容：请见原始会话文件]')
            else:
                parts.append(strify(it))
    return '\n\n'.join(x for x in parts if x.strip())


def details(summary, body):
    body = (body or '').strip()
    if not body:
        return ''
    # 避免正文里的 ``` 破坏折叠块，统一用 4 个反引号包裹代码
    return '<details>\n<summary>%s</summary>\n\n%s\n\n</details>\n' % (summary, body)


def render_session(lines, markdown_path):
    """把一份 .jsonl 的解析结果渲染成可读 Markdown。"""
    entries = [l for l in lines]
    title = next((l.get('aiTitle') for l in entries if l.get('type') == 'ai-title'), '') or '(无标题)'
    sid = next((l.get('sessionId') for l in entries if l.get('sessionId')), '')
    cwd = next((l.get('cwd') for l in entries if l.get('cwd')), '')
    stamps = [l.get('timestamp') for l in entries if l.get('timestamp')]

    n_tool = sum(1 for l in entries if l.get('type') == 'function_call')
    n_reason = sum(1 for l in entries if l.get('type') == 'reasoning')
    n_msg = sum(1 for l in entries if l.get('type') == 'message')
    tools = []
    for l in entries:
        if l.get('type') == 'function_call' and l.get('name') not in tools:
            tools.append(l.get('name'))

    out = []
    out.append('# 会话记录：%s\n' % title)
    out.append('> 本文件由《导出会话.py》自动生成，内容取自 WorkBuddy 原始会话文件，')
    out.append('> 对话与工具调用内容均为原样呈现（未改写、未摘要）。\n')
    out.append('## 一、会话基本信息\n')
    out.append('| 项目 | 内容 |')
    out.append('| --- | --- |')
    out.append('| 会话标题 | %s |' % title)
    out.append('| 会话 ID | `%s` |' % sid)
    out.append('| 工作空间 | `%s` |' % cwd)
    out.append('| 记录条数 | %d 条（其中消息 %d、模型思考 %d、工具调用 %d） |' % (len(entries), n_msg, n_reason, n_tool))
    out.append('| 会话开始 | %s |' % fmt_time(min(stamps) if stamps else None))
    out.append('| 会话结束 | %s |' % fmt_time(max(stamps) if stamps else None))
    out.append('| 导出时间 | %s |' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    out.append('| 使用过的工具 | %s |' % ('、'.join('`%s`' % t for t in tools) if tools else '无'))
    out.append('')
    out.append('---\n')
    out.append('## 二、对话时间轴\n')

    step = 0
    for l in entries:
        t = l.get('type')
        ts = fmt_time(l.get('timestamp'))
        if t == 'ai-title':
            continue
        if t == 'message':
            step += 1
            role = l.get('role')
            who = {'user': '👤 用户', 'assistant': '🤖 助手'}.get(role, role or '?')
            body = text_of(l.get('content'))
            if not body.strip():
                continue
            out.append('### %d. %s · %s\n' % (step, who, ts))
            if role == 'user':
                # 用户消息里混有平台注入的 <system-reminder> 上下文，
                # 单独折叠，正文只保留用户真正输入的内容，保证可读。
                queries = [q.strip() for q in RE_USERQUERY.findall(body) if q.strip()]
                reminders = RE_REMINDER.findall(body)
                residue = RE_USERQUERY.sub('', RE_REMINDER.sub('', body)).strip()
                shown = '\n\n'.join(queries) if queries else residue
                out.append(shown + '\n')
                if reminders:
                    out.append(details(
                        '📎 平台注入的上下文（%d 段，点击展开）' % len(reminders),
                        '\n\n'.join('```text\n%s\n```' % r for r in reminders)))
            else:
                out.append(body + '\n')
        elif t == 'reasoning':
            body = text_of(l.get('content')) or strify(l.get('rawContent'))
            blk = details('💭 模型思考 · %s' % ts, body)
            if blk:
                out.append(blk)
        elif t == 'function_call':
            step += 1
            name = l.get('name') or '?'
            args = strify(l.get('arguments'))
            out.append('### %d. 🔧 调用工具 `%s` · %s\n' % (step, name, ts))
            out.append(details('参数', '```json\n%s\n```' % args))
            out.append('')
        elif t == 'function_call_result':
            step += 1
            name = l.get('name') or '?'
            status = l.get('status')
            output = strify(l.get('output'))
            out.append('### %d. 📤 工具返回 `%s` · %s %s\n' % (
                step, name, ts, ('(%s)' % status) if status else ''))
            out.append(details('返回内容', '```\n%s\n```' % output))
            out.append('')
        elif t == 'file-history-snapshot':
            snap = l.get('snapshot') or {}
            files = snap.get('files') if isinstance(snap, dict) else None
            if isinstance(files, dict):
                lst = '、'.join('`%s`' % k for k in list(files.keys())[:20])
                desc = '文件快照：%d 个文件（%s）' % (len(files), lst)
            else:
                desc = '文件快照（完整数据见原始会话文件）'
            out.append('> 📁 %s · %s\n' % (ts, desc))
        else:
            out.append('> ⏺ `%s` · %s\n' % (t, ts))

    with open(markdown_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out))


def main():
    ap = argparse.ArgumentParser(description='导出 WorkBuddy 工作空间会话记录')
    ap.add_argument('--workspace', required=True, help='工作空间绝对路径')
    ap.add_argument('--out', required=True, help='输出目录')
    ap.add_argument('--home', default=os.path.join(os.path.expanduser('~'), '.workbuddy'),
                    help='.workbuddy 目录，默认 ~/.workbuddy')
    a = ap.parse_args()

    ws = os.path.abspath(a.workspace)
    enc = encode_workspace(ws)
    proj = os.path.join(a.home, 'projects', enc)
    out = os.path.abspath(a.out)

    print('工作空间      : %s' % ws)
    print('编码目录      : %s' % enc)
    print('会话来源      : %s' % proj)
    print('输出目录      : %s' % out)

    if not os.path.isdir(proj):
        print('错误：未找到该工作空间的会话目录。')
        return 1

    raw_dir = os.path.join(out, '会话原始文件')
    os.makedirs(raw_dir, exist_ok=True)

    sessions = sorted(f for f in os.listdir(proj) if f.endswith('.jsonl'))
    if not sessions:
        print('错误：该工作空间下没有 .jsonl 会话文件。')
        return 1

    for fn in sorted(os.listdir(proj)):
        if fn.endswith(RAW_SUFFIXES):
            shutil.copy2(os.path.join(proj, fn), os.path.join(raw_dir, fn))
            print('  已复制原始文件：%s' % fn)

    md_paths = []
    for fn in sessions:
        with open(os.path.join(proj, fn), encoding='utf-8') as f:
            lines = [json.loads(x) for x in f if x.strip()]
        base = fn[:-len('.jsonl')]
        title = ''
        for l in lines:
            if l.get('type') == 'ai-title' and l.get('aiTitle'):
                title = l['aiTitle']
                break
        md_name = '%s.md' % (title or base)
        md_path = os.path.join(out, md_name)
        render_session(lines, md_path)
        md_paths.append(md_path)
        print('  已生成可读全文：%s（%d 条记录）' % (md_name, len(lines)))

    # 工作空间自带的 .workbuddy（记忆 / 产物等）
    ws_wb = os.path.join(ws, '.workbuddy')
    if os.path.isdir(ws_wb):
        dst = os.path.join(out, '工作空间存档', '.workbuddy')
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        shutil.copytree(ws_wb, dst)
        print('  已复制工作空间 .workbuddy -> 工作空间存档/.workbuddy')

    print('\n导出完成，共 %d 份会话。' % len(sessions))
    return 0


if __name__ == '__main__':
    sys.exit(main())
