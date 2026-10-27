#!/usr/bin/env python3
"""
加载 .env 文件中的环境变量。

查找策略：
1. 当前目录（脚本所在位置）是否有 .env → 有则读取
2. 否则向上遍历父目录查找 .env → 有则读取
3. 都没有则保持 os.environ 不变（脚本内已设置默认值）

Stdio bootstrap：在控制台代码页非 UTF-8 的系统（如中文 Windows GBK/cp936）上，
reconfigure stdout/stderr 为 UTF-8（errors="replace"），
使 CJK + emoji 输出不会导致脚本报错。
"""

import os
import re
import sys

# ---------------------------------------------------------------- stdio fix
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass  # 不可 reconfigure 的流（pythonw / 被捕获的管道等）


def load_env():
    """
    加载 .env 文件到环境变量。
    从脚本所在目录开始，向上遍历最多 5 级查找 .env 文件。
    
    Returns:
        bool: 是否成功加载了 .env 文件
    """
    current = os.path.dirname(os.path.abspath(__file__))
    
    for _ in range(5):
        env_path = os.path.join(current, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
                    if match:
                        key, value = match.groups()
                        value = value.strip().strip('"').strip("'")
                        if key not in os.environ:
                            os.environ[key] = value
            return True
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    
    return False


if __name__ == "__main__":
    loaded = load_env()
    key = os.environ.get("AGNESAI_API_KEY", "(未设置)")
    print(f"AGNESAI_API_KEY: {key[:20] if key != '(未设置)' else key}...")
    print(f"加载状态: {'成功' if loaded else '未找到 .env 文件'}")
