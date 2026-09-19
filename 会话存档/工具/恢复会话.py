# -*- coding: utf-8 -*-
"""
WorkBuddy 会话恢复工具
================================================================

作用：把《会话存档》里的原始会话文件，还原到本机 WorkBuddy 的会话存储位置，
      使会话能在这台电脑的 WorkBuddy 里被识别、打开并继续对话。

WorkBuddy 的会话存储位置：
    ~/.workbuddy/projects/<工作空间路径编码>/<会话ID>.jsonl
    <工作空间路径编码> = 工作空间绝对路径中 ":" 与 "\\" 均替换为 "-"，盘符转小写。

用法：
    python 恢复会话.py --archive "会话存档\\东风日产组织分析" \
                       --workspace "G:\\项目\\WorkBuddy项目\\东风日产组织分析"

参数：
    --archive    会话存档目录（即含「会话原始文件」的那个目录）
    --workspace  本机上要绑定的工作空间绝对路径（若与原路径一致，最省事）
    --home       .workbuddy 目录，默认 ~/.workbuddy
    --force      目标已存在同名会话时是否覆盖，默认不覆盖
"""

import argparse
import os
import shutil
import sys


def encode_workspace(path):
    """把工作空间路径编码成 ~/.workbuddy/projects 下的目录名。"""
    p = os.path.abspath(path).replace('\\', '/')
    p = p.replace(':/', '-').replace('/', '-')
    if len(p) > 1:
        p = p[0].lower() + p[1:]
    return p


def main():
    ap = argparse.ArgumentParser(description='恢复 WorkBuddy 会话记录')
    ap.add_argument('--archive', required=True, help='会话存档目录')
    ap.add_argument('--workspace', required=True, help='本机工作空间绝对路径')
    ap.add_argument('--home', default=os.path.join(os.path.expanduser('~'), '.workbuddy'),
                    help='.workbuddy 目录，默认 ~/.workbuddy')
    ap.add_argument('--force', action='store_true', help='覆盖已存在的同名会话')
    a = ap.parse_args()

    archive = os.path.abspath(a.archive)
    raw_dir = os.path.join(archive, '会话原始文件')
    ws = os.path.abspath(a.workspace)
    enc = encode_workspace(ws)
    dst_dir = os.path.join(a.home, 'projects', enc)

    print('存档目录        : %s' % archive)
    print('目标工作空间    : %s' % ws)
    print('编码目录        : %s' % enc)
    print('恢复目标        : %s' % dst_dir)
    print('')

    if not os.path.isdir(raw_dir):
        print('错误：找不到「会话原始文件」目录。')
        return 1

    os.makedirs(dst_dir, exist_ok=True)

    copied = 0
    for fn in sorted(os.listdir(raw_dir)):
        src = os.path.join(raw_dir, fn)
        dst = os.path.join(dst_dir, fn)
        if os.path.exists(dst) and not a.force:
            print('  跳过（已存在）：%s' % fn)
            continue
        shutil.copy2(src, dst)
        print('  已恢复：%s' % fn)
        copied += 1

    # 工作空间自带的 .workbuddy（记忆文件等）
    src_wb = os.path.join(archive, '工作空间存档', '.workbuddy')
    if os.path.isdir(src_wb):
        dst_wb = os.path.join(ws, '.workbuddy')
        os.makedirs(ws, exist_ok=True)
        if os.path.isdir(dst_wb) and not a.force:
            print('  跳过工作空间 .workbuddy（已存在）：%s' % dst_wb)
        else:
            if os.path.isdir(dst_wb):
                shutil.rmtree(dst_wb)
            shutil.copytree(src_wb, dst_wb)
            print('  已恢复工作空间 .workbuddy -> %s' % dst_wb)

    print('\n完成，共恢复 %d 个会话文件。' % copied)
    print('请重启 WorkBuddy（或重新打开该工作空间），即可在会话列表中找到这条会话。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
