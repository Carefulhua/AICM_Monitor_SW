"""切换 MES 上传地址：本机桩（127.0.0.1） <-> 工厂 MES（192.168.20.100）。

同时改源码配置 `config/mes.json` 和发布包内 `dist/*/_internal/config/mes.json`，
避免改了源码却忘了打包内的那份。

用法：
    python tools/mes_url_switch.py               # 只显示当前地址
    python tools/mes_url_switch.py --local       # 指向本机桩 http://127.0.0.1:8090/...
    python tools/mes_url_switch.py --factory     # 指向工厂 MES http://192.168.20.100:8090/...
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH_SUFFIX = "WebService/MesATEApi.asmx/ATECommandCode"
URLS = {
    "local": f"http://127.0.0.1:8090/{PATH_SUFFIX}",
    "factory": f"http://192.168.20.100:8090/{PATH_SUFFIX}",
}


def mes_configs() -> list[Path]:
    """源码配置 + 所有发布包内的配置。"""
    paths = [ROOT / "config" / "mes.json"]
    paths += sorted((ROOT / "dist").glob("*/_internal/config/mes.json"))
    return [p for p in paths if p.exists()]


def main() -> int:
    ap = argparse.ArgumentParser(description="切换 MES 上传地址")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--local", action="store_true", help="指向本机 MES 桩")
    group.add_argument("--factory", action="store_true", help="指向工厂 MES")
    args = ap.parse_args()

    if not args.local and not args.factory:
        for path in mes_configs():
            cfg = json.loads(path.read_text(encoding="utf-8"))
            print(f"{path.relative_to(ROOT)}: {cfg.get('url')}")
        return 0

    target = URLS["local" if args.local else "factory"]
    for path in mes_configs():
        cfg = json.loads(path.read_text(encoding="utf-8"))
        cfg["url"] = target
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print(f"已改为 {target}\n  -> {path.relative_to(ROOT)}")
    if args.local:
        print("\n注意：这是本机验证用的地址，发布给工厂前请执行 "
              "python tools/mes_url_switch.py --factory")
    print("\n重启界面程序后生效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
