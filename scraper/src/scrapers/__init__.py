import pkgutil
import importlib
from pathlib import Path

# 현재 패키지 내의 모든 모듈을 순회하며 자동 import
package_dir = Path(__file__).resolve().parent
for _, module_name, _ in pkgutil.iter_modules([str(package_dir)]):
    if module_name != "base":
        importlib.import_module(f".{module_name}", package=__name__)