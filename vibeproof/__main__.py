"""支持通过 ``python -m vibeproof`` 启动命令行程序。

该文件不承载业务逻辑，只把模块执行入口转交给 ``vibeproof.cli.main`` 并返回对应的退出码。
"""

from vibeproof.cli import main

raise SystemExit(main())
