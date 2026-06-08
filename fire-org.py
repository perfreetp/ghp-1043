#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""消防资料整理器入口脚本"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fire_organizer.cli import main

if __name__ == "__main__":
    main()
